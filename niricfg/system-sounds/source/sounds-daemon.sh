#!/usr/bin/env bash
# Niri sounds daemon
# Change PROFILE to switch sound sets. Profiles live in profiles/<name>.sh

NIRI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE=steam

source "$NIRI_DIR/profiles/$PROFILE.sh"

FOCUSED_APP_FILE=/tmp/niri-focused-app

# Returns 0 (true) if current hour is within the night window.
_is_night() {
    local hour; hour=$(date +%-H)
    if (( NIGHT_START > NIGHT_END )); then
        (( hour >= NIGHT_START || hour < NIGHT_END ))
    else
        (( hour >= NIGHT_START && hour < NIGHT_END ))
    fi
}

# Play a sound file with a 0.0–1.0 volume (converts to paplay's 0–65536 scale).
# Applies NIGHT_VOLUME multiplier automatically when in night window.
_play() {
    local file="$1" vol="${2:-1.0}"
    [[ -z "$file" ]] && return
    if _is_night; then
        vol=$(awk "BEGIN{printf \"%.6f\", $vol * ${NIGHT_VOLUME:-1.0}}")
    fi
    local pa_vol
    pa_vol=$(awk "BEGIN{printf \"%d\", $vol * 65536}")
    paplay --volume="$pa_vol" "$file"
}

# ── Media monitor ─────────────────────────────────────────────────
media_monitor() {
    local prev="" in_seq=false last_stop=0

    while IFS= read -r s; do
        if $in_seq; then
            [[ "$s" == Playing ]] && in_seq=false
            continue
        fi

        case "$s" in
            Playing)
                if [[ "$prev" != Playing ]]; then
                    local now; now=$(date +%s)
                    if (( now - last_stop >= 30 )) && [[ -n "${SND_MEDIA_START:-}" ]]; then
                        in_seq=true
                        playerctl --ignore-player=discord pause 2>/dev/null
                        _play "$SND_MEDIA_START" "${SND_MEDIA_START_VOL:-1.0}"
                        playerctl --ignore-player=discord play 2>/dev/null
                    fi
                fi
                ;;
            Paused|Stopped)
                [[ "$prev" == Playing ]] && last_stop=$(date +%s)
                ;;
        esac
        prev=$s
    done < <(playerctl --ignore-player=discord --follow status 2>/dev/null)
}

# ── Niri monitor ──────────────────────────────────────────────────
niri_monitor() {
    declare -A win_apps   # key = window ID, value = app_id
    local initialized=false id app line chunk

    while true; do
        while IFS= read -r line; do

            # ── Init: populate win_apps from initial snapshot ──
            if ! $initialized; then
                if [[ "$line" == Windows\ changed:* ]]; then
                    while IFS= read -r chunk; do
                        [[ -z "$chunk" ]] && continue
                        id="" app=""
                        [[ "$chunk" =~ id:\ ([0-9]+) ]] && id="${BASH_REMATCH[1]}"
                        [[ "$chunk" =~ app_id:\ Some\(\"([^\"]+)\"\) ]] && app="${BASH_REMATCH[1]}"
                        [[ -n "$id" ]] && win_apps[$id]=$app
                    done < <(printf '%s' "$line" | sed 's/Window { /\n/g' | tail -n +2)
                fi
                if [[ "$line" == Config\ loaded* ]]; then
                    initialized=true
                fi
                continue
            fi

            # ── Window opened (new ID) or title/app_id changed ────────
            if [[ "$line" == "Window opened or changed:"* ]]; then
                id="" app=""
                [[ "$line" =~ id:\ ([0-9]+) ]] && id="${BASH_REMATCH[1]}"
                [[ "$line" =~ app_id:\ Some\(\"([^\"]+)\"\) ]] && app="${BASH_REMATCH[1]}"
                if [[ -n "$id" ]]; then
                    if [[ "${win_apps[$id]+_}" ]]; then
                        win_apps[$id]=$app
                    else
                        win_apps[$id]=$app
                        [[ -n "${SND_WINDOW_OPEN:-}" ]] && _play "$SND_WINDOW_OPEN" "${SND_WINDOW_OPEN_VOL:-1.0}" &
                    fi
                fi

            # ── Window closed ─────────────────────────────────────────
            elif [[ "$line" == "Window closed:"* ]]; then
                id=""
                [[ "$line" =~ Window\ closed:\ ([0-9]+) ]] && id="${BASH_REMATCH[1]}"
                if [[ -n "$id" ]]; then
                    unset "win_apps[$id]"
                    [[ -n "${SND_WINDOW_CLOSE:-}" ]] && _play "$SND_WINDOW_CLOSE" "${SND_WINDOW_CLOSE_VOL:-1.0}" &
                fi

            # ── Focus changed — update the file typing-monitor reads ──
            elif [[ "$line" == "Window focus changed:"* ]]; then
                id=""
                [[ "$line" =~ Some\(([0-9]+)\) ]] && id="${BASH_REMATCH[1]}"
                if [[ -n "$id" ]] && [[ "${win_apps[$id]+_}" ]]; then
                    echo "${win_apps[$id]}" > "$FOCUSED_APP_FILE"
                else
                    > "$FOCUSED_APP_FILE"
                fi

            # ── Workspace switch ──────────────────────────────────────
            elif [[ "$line" == "Workspace focused:"* ]]; then
                [[ -n "${SND_WORKSPACE:-}" ]] && _play "$SND_WORKSPACE" "${SND_WORKSPACE_VOL:-1.0}" &

            # ── Overview ──────────────────────────────────────────────
            elif [[ "$line" == "Overview toggled: true" ]]; then
                [[ -n "${SND_OVERVIEW:-}" ]] && _play "$SND_OVERVIEW" "${SND_OVERVIEW_VOL:-1.0}" &
            fi

        done < <(niri msg event-stream 2>/dev/null)

        # Reconnect after socket drop / niri restart
        initialized=false
        unset win_apps
        declare -A win_apps
        sleep 2
    done
}

# ── Entry point ───────────────────────────────────────────────────
> "$FOCUSED_APP_FILE"

if command -v playerctl &>/dev/null; then
    media_monitor &
fi

# Build typing-monitor argument list from the variables above
_tm_args=(
    --volume       "$TYPING_VOLUME"
    --night-start  "$NIGHT_START"
    --night-end    "$NIGHT_END"
    --night-volume "$NIGHT_VOLUME"
    --caps-volume  "$CAPS_VOLUME"
)
[[ ${#TYPING_APPS[@]}         -gt 0 ]] && _tm_args+=(--app      "${TYPING_APPS[@]}")
[[ ${#SND_TYPING_TYPING[@]}   -gt 0 ]] && _tm_args+=(--typing   "${SND_TYPING_TYPING[@]}")
[[ ${#SND_TYPING_ACTION[@]}   -gt 0 ]] && _tm_args+=(--action   "${SND_TYPING_ACTION[@]}")
[[ ${#SND_TYPING_MODIFIER[@]} -gt 0 ]] && _tm_args+=(--modifier "${SND_TYPING_MODIFIER[@]}")
[[ ${#SND_TYPING_FUNCTION[@]} -gt 0 ]] && _tm_args+=(--function "${SND_TYPING_FUNCTION[@]}")
[[ ${#SND_TYPING_NAV[@]}      -gt 0 ]] && _tm_args+=(--nav      "${SND_TYPING_NAV[@]}")
_tm_args+=(
    --typing-vol   "${SND_TYPING_TYPING_VOL:-1.0}"
    --action-vol   "${SND_TYPING_ACTION_VOL:-1.0}"
    --modifier-vol "${SND_TYPING_MODIFIER_VOL:-1.0}"
    --function-vol "${SND_TYPING_FUNCTION_VOL:-1.0}"
    --nav-vol      "${SND_TYPING_NAV_VOL:-1.0}"
)

# Supervisor: restart typing-monitor if it exits for any reason
typing_supervisor() {
    while true; do
        python3 "$NIRI_DIR/source/typing-monitor.py" "$FOCUSED_APP_FILE" "${_tm_args[@]}"
        sleep 2
    done
}
typing_supervisor &

niri_monitor
