#!/usr/bin/env bash
set -euo pipefail

dir="$1"          # left | right | up | down
margin="${2:-16}"

win=$(niri msg --json windows | jq '.[] | select(.is_focused)')
[ -z "$win" ] && exit 0

is_floating=$(echo "$win" | jq -r '.is_floating')

# --- TILING: обычное поведение ---
if [ "$is_floating" != "true" ]; then
    case "$dir" in
        left)  niri msg action move-column-left ;;
        right) niri msg action move-column-right ;;
        up)    niri msg action move-window-up ;;
        down)  niri msg action move-window-down ;;
    esac
    exit 0
fi

# --- FLOATING: подвинуть по ОДНОЙ оси, вторую не трогать ---
id=$(echo "$win" | jq '.id')
width=$(echo "$win" | jq '.layout.window_size[0]')
height=$(echo "$win" | jq '.layout.window_size[1]')
x=$(echo "$win" | jq '.layout.tile_pos_in_workspace_view[0]')
y=$(echo "$win" | jq '.layout.tile_pos_in_workspace_view[1]')

output=$(niri msg --json workspaces | jq -r '.[] | select(.is_focused) | .output')
screen_width=$(niri msg --json outputs | jq ".[\"$output\"].logical.width")
screen_height=$(niri msg --json outputs | jq ".[\"$output\"].logical.height")

case "$dir" in
    left)  new_x=$margin;                              new_y=$y ;;
    right) new_x=$(( screen_width - width - margin ));  new_y=$y ;;
    up)    new_x=$x;                                    new_y=$margin ;;
    down)  new_x=$x;                                    new_y=$(( screen_height - height - margin )) ;;
esac

niri msg action move-floating-window --id "$id" -x "$new_x" -y "$new_y"
