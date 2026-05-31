# CLAUDE.md — Project Instructions

## Syntax Validation

**Always validate syntax before delivering any result.** For every file type edited or created:

- **Fish scripts** — `fish --no-execute <file>`
- **KDL (niri config)** — `niri validate` or `niri --config <file> --validate` if available
- **JSON** — `python3 -m json.tool <file> > /dev/null`
- **YAML** — `python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" <file>`

If a validator is not available for the file type, state that explicitly rather than skipping the check.

---

## Проект: System Sounds — v0.3 ✓ завершён

Самостоятельный пакет в `~/.config/system-sounds/`. Пришёл на смену `niri/sounds-daemon.sh`.

### Структура

```
system-sounds/
├── config                        # точка входа: autostart + dep check + запуск TUI
├── profiles/
│   └── steam.sh                  # активный профиль (звуки + переменные типинга)
├── sounds/
│   └── steam/                    # аудиофайлы профиля steam
└── source/
    ├── sounds-daemon.sh          # главный bash-демон
    ├── sounds-tui.py             # Textual TUI — редактор профилей
    └── typing-monitor.py         # Python — звуки клавиатуры (/dev/input/event*)
```

### Файлы

| Файл | Назначение |
|---|---|
| `system-sounds/config` | Точка входа: добавляет autostart в niri, проверяет зависимости, запускает TUI |
| `system-sounds/source/sounds-daemon.sh` | Bash-демон. Три компонента: `media_monitor`, `typing_supervisor`, `niri_monitor` |
| `system-sounds/source/typing-monitor.py` | Python-скрипт звуков клавиатуры. Читает `/dev/input/event*` напрямую |
| `system-sounds/source/sounds-tui.py` | Textual TUI: редактирование профилей, set default, apply & restart |
| `system-sounds/profiles/steam.sh` | Профиль: пути к звукам + параметры типинга |
| `niri/cfg/autostart.kdl` | `spawn-at-startup "bash" "/home/art/.config/system-sounds/source/sounds-daemon.sh"` |

### Профили

`sounds-daemon.sh` читает `PROFILE=<name>`, делает `source profiles/<name>.sh`.  
Профиль задаёт: `SND_WINDOW_OPEN/CLOSE`, `SND_WORKSPACE`, `SND_OVERVIEW`, `SND_MEDIA_START`, `TYPING_APPS`, `TYPING_VOLUME`, `NIGHT_*`, `CAPS_VOLUME`, `SND_TYPING_*`.

### Ключевые параметры typing-monitor.py

- `DEBOUNCE = 0.03` — per-key дебаунс KEY_DOWN (блокирует дубли от нескольких `/dev/input` нод)
- `DEBOUNCE_REPEAT = 0.04` — per-key дебаунс KEY_REPEAT (зажатие клавиши)
- 5 групп клавиш: `typing`, `action`, `modifier`, `function`, `nav`
- Shared `_play_lock`, `_last_down[code]`, `_last_repeat[code]` — один звук на физическое нажатие
- Night mode: 22:00–07:00, `NIGHT_VOLUME=0.3`

### Как перезапустить демон

```bash
pgrep -f "sounds-daemon.sh|typing-monitor.py" | xargs kill -9 2>/dev/null
nohup bash ~/.config/system-sounds/source/sounds-daemon.sh >/tmp/sounds-daemon.log 2>&1 &
```

**Важно:** Всегда использовать `nohup`, иначе процесс умирает при закрытии bash-сессии (SIGHUP).  
**Проверка:** `pgrep -f "sounds-daemon|typing-monitor"` (без backslash перед `|`).

---

## Work Log

### 2026-05-29 — Niri sounds daemon

**Задача:** Включить и проверить два скрипта из предыдущей сессии, конвертировать `.fish` → `.sh`.

**Файлы:**
- `niri/sounds-daemon.sh` — конвертирован из `sounds-daemon.fish`; fish-параллельные массивы заменены на bash `declare -A win_apps`; инициализация через событие `Config loaded successfully`; парсинг через bash regex и sed
- `niri/typing-monitor.py` — без изменений
- `niri/cfg/autostart.kdl` — запись обновлена: `"fish" "...daemon.fish"` → `"bash" "...daemon.sh"`

**Диагностика:** Скрипт корректен — инициализация работает, события обрабатываются правильно. Подтверждено через `bash -x` трассировку.

### 2026-05-29 — Расширение typing-monitor

**Задача:** Добавить группы клавиш, случайные звуки, ночной режим, caps lock, громкость.

**Изменения:**
- `niri/typing-monitor.py` — полная переработка: 5 групп клавиш (typing/action/modifier/function/nav) с разными наборами звуков; случайный выбор без повторов подряд; caps lock через EV_LED; ночной режим (NIGHT_START/NIGHT_END/NIGHT_VOLUME); громкость через `--volume`; argparse CLI
- `niri/sounds-daemon.sh` — добавлены переменные TYPING_VOLUME, NIGHT_*, CAPS_VOLUME, SND_TYPING_* на каждую группу; новый вызов python3 с построением аргументов через массив `_tm_args`
- `~/typing-sounds-README.txt` — инструкция по кастомизации (пути, группы, apps, ночной режим, caps lock, примеры)

### 2026-05-29 — Рефакторинг в system-sounds

**Задача:** Вынести daemon/TUI в `system-sounds/`, добавить TUI-редактор профилей, переместить скрипты в `source/`.

**Изменения:**
- `system-sounds/` — новый самостоятельный пакет
- `system-sounds/config` — точка входа (autostart prompt + dep check + запуск TUI)
- `system-sounds/source/sounds-daemon.sh` — перенесён из `niri/`, `NIRI_DIR` поднимается на уровень выше (`../`)
- `system-sounds/source/sounds-tui.py` — Textual TUI-редактор профилей
- `system-sounds/source/typing-monitor.py` — перенесён из `niri/`
- `system-sounds/profiles/steam.sh` — профиль с путями и параметрами типинга
