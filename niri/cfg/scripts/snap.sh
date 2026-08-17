#!/usr/bin/env bash
set -euo pipefail

pos="$1"          # left | right | up | down | center | nw | ne | sw | se
margin="${2:-16}"

# Запас под border/shadow: они рисуются за пределами geometry окна и не
# видны в tile_pos_in_workspace_view/window_size, поэтому без запаса
# скруглённый угол реально уходит под панель или за физический край
# монитора (проверено скриншотом).
DECOR_BUFFER=6

win=$(niri msg --json windows | jq '.[] | select(.is_focused)')
[ -z "$win" ] && exit 0

is_floating=$(echo "$win" | jq -r '.is_floating')

# --- TILING: обычное поведение, углы/центр для тайлов смысла не имеют ---
if [ "$is_floating" != "true" ]; then
    case "$pos" in
        left)  niri msg action move-column-left ;;
        right) niri msg action move-column-right ;;
        up)    niri msg action move-window-up ;;
        down)  niri msg action move-window-down ;;
    esac
    exit 0
fi

# --- FLOATING: снап по 9 позициям (сетка 3x3, как нумпад) ---
id=$(echo "$win" | jq '.id')
width=$(echo "$win" | jq '.layout.window_size[0]')
height=$(echo "$win" | jq '.layout.window_size[1]')
x=$(echo "$win" | jq '.layout.tile_pos_in_workspace_view[0]')
y=$(echo "$win" | jq '.layout.tile_pos_in_workspace_view[1]')
# niri отдаёт позицию как float ("782.0") — обрезаем дробную часть для bash-арифметики
x=${x%.*}
y=${y%.*}

output=$(niri msg --json workspaces | jq -r '.[] | select(.is_focused) | .output')
screen_width=$(niri msg --json outputs | jq ".[\"$output\"].logical.width")
screen_height=$(niri msg --json outputs | jq ".[\"$output\"].logical.height")
screen_width=${screen_width%.*}
screen_height=${screen_height%.*}

case "$pos" in
    left)   new_x=$margin;                               new_y=$y ;;
    right)  new_x=$(( screen_width - width - margin ));   new_y=$y ;;
    up)     new_x=$x;                                     new_y=$margin ;;
    down)   new_x=$x;                                     new_y=$(( screen_height - height - margin )) ;;
    center) new_x=$(( (screen_width - width) / 2 ));       new_y=$(( (screen_height - height) / 2 )) ;;
    nw)     new_x=$margin;                                 new_y=$margin ;;
    ne)     new_x=$(( screen_width - width - margin ));    new_y=$margin ;;
    sw)     new_x=$margin;                                 new_y=$(( screen_height - height - margin )) ;;
    se)     new_x=$(( screen_width - width - margin ));    new_y=$(( screen_height - height - margin )) ;;
    *) exit 0 ;;
esac

# clamp: не даём окну (вместе с запасом под декор) уехать за пределы монитора
clamp() {
    local val=$1 max=$2
    (( max < 0 )) && max=0
    (( val < 0 )) && val=0
    (( val > max )) && val=$max
    echo "$val"
}
new_x=$(clamp "$new_x" $(( screen_width - width - DECOR_BUFFER )))
new_y=$(clamp "$new_y" $(( screen_height - height - DECOR_BUFFER )))

# niri применяет -x/-y не буквально: реальная tile_pos_in_workspace_view
# получается со стабильным аддитивным сдвигом (gaps/резерв под панель),
# из-за чего окно "доезжало" дальше расчёта и вылезало за край монитора.
# Калибруем сдвиг по факту первого хода и сразу компенсируем вторым —
# без хардкода констант, переживёт смену gaps/темы.
niri msg action move-floating-window --id "$id" -x "$new_x" -y "$new_y"
sleep 0.05

actual=$(niri msg --json windows | jq --argjson id "$id" '.[] | select(.id == $id)')
actual_x=$(echo "$actual" | jq '.layout.tile_pos_in_workspace_view[0]')
actual_y=$(echo "$actual" | jq '.layout.tile_pos_in_workspace_view[1]')
actual_x=${actual_x%.*}
actual_y=${actual_y%.*}

offset_x=$(( actual_x - new_x ))
offset_y=$(( actual_y - new_y ))

if [ "$offset_x" -ne 0 ] || [ "$offset_y" -ne 0 ]; then
    # new_x/new_y — желаemая финальная (визуальная) позиция, уже с запасом
    # под декор. offset живёт в другом пространстве координат (то, что мы
    # передаём в -x/-y), поэтому его НЕ клампим повторно к границам экрана —
    # но floor на DECOR_BUFFER нужен: отрицательный запрос (когда offset
    # больше margin) niri обрабатывает непредсказуемо.
    corrected_x=$(( new_x - offset_x )); (( corrected_x < DECOR_BUFFER )) && corrected_x=$DECOR_BUFFER
    corrected_y=$(( new_y - offset_y )); (( corrected_y < DECOR_BUFFER )) && corrected_y=$DECOR_BUFFER
    niri msg action move-floating-window --id "$id" -x "$corrected_x" -y "$corrected_y"
fi
