#!/usr/bin/env bash
# Niri sounds daemon
# Plays sounds for window, workspace, typing, and media events.
# Change SND_* paths to your own samples at any time.

SOUNDS_DIR=/home/art/.config/niri/sounds

SND_WINDOW_OPEN=$SOUNDS_DIR/service-login.oga
SND_WINDOW_CLOSE=$SOUNDS_DIR/service-logout.oga
SND_WORKSPACE=$SOUNDS_DIR/deck_ui_tab_transition_01.wav
SND_OVERVIEW=$SOUNDS_DIR/message-new-instant.oga
SND_MEDIA_START=$SOUNDS_DIR/deck_ui_launch_game.wav

# App IDs that trigger typing sounds. Empty = all apps.
TYPING_APPS=(kitty org.gnome.Nautilus)

FOCUSED_APP_FILE=/tmp/niri-focused-app

# ── Typing sound settings ─────────────────────────────────────────
TYPING_VOLUME=1.0    # base volume 0.0–1.0
NIGHT_START=22       # night mode start (hour, 24h)
NIGHT_END=7          # night mode end (hour, 24h)
NIGHT_VOLUME=0.3     # volume fraction during night (0.3 = 30%)
CAPS_VOLUME=1.0      # extra multiplier when Caps Lock is on (1.0 = no change)

# Per-group sound files. List multiple files for random selection (no consecutive repeat).
# Empty array = silent for that group.
SND_TYPING_TYPING=( "$SOUNDS_DIR/deck_ui_typing.wav" )   # a–z, 0–9, punctuation
SND_TYPING_ACTION=( "$SOUNDS_DIR/deck_ui_typing.wav" )   # Enter, Backspace, Space, Tab
SND_TYPING_MODIFIER=()                 # Shift, Ctrl, Alt, Super, CapsLock — silent
SND_TYPING_FUNCTION=()                 # F1–F12, Escape — silent
SND_TYPING_NAV=()                      # Arrow keys, Home/End/PgUp/PgDn — silent

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
                    if (( now - last_stop >= 30 )); then
                        in_seq=true
                        playerctl --ignore-player=discord pause 2>/dev/null
                        paplay "$SND_MEDIA_START"
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
                        paplay "$SND_WINDOW_OPEN" &
                    fi
                fi

            # ── Window closed ─────────────────────────────────────────
            elif [[ "$line" == "Window closed:"* ]]; then
                id=""
                [[ "$line" =~ Window\ closed:\ ([0-9]+) ]] && id="${BASH_REMATCH[1]}"
                if [[ -n "$id" ]]; then
                    unset "win_apps[$id]"
                    paplay "$SND_WINDOW_CLOSE" &
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
                paplay "$SND_WORKSPACE" &

            # ── Overview ──────────────────────────────────────────────
            elif [[ "$line" == "Overview toggled: true" ]]; then
                paplay "$SND_OVERVIEW" &
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

# Supervisor: restart typing-monitor if it exits for any reason
typing_supervisor() {
    while true; do
        python3 /home/art/.config/niri/typing-monitor.py "$FOCUSED_APP_FILE" "${_tm_args[@]}"
        sleep 2
    done
}
typing_supervisor &

niri_monitor
