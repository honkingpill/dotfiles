#!/usr/bin/env python3
"""
Typing sound monitor for Niri. Configured via sounds-daemon.sh.
See ~/typing-sounds-README.txt for customization guide.

Key groups
----------
  typing   — a–z, 0–9, punctuation
  action   — Enter, Backspace, Space, Tab
  modifier — Shift, Ctrl, Alt, Super, CapsLock  (silent by default)
  function — F1–F12, Escape                     (silent by default)
  nav      — Arrows, Home/End/PgUp/PgDn         (silent by default)

Each group picks a random sound from its list, never repeating the same
file twice in a row. Volume scales automatically at night and with Caps Lock.
"""
from __future__ import annotations

import struct, sys, subprocess, threading, time, random, argparse
from pathlib import Path
from datetime import datetime

# ── Linux input constants ──────────────────────────────────────────
EV_KEY    = 1
EV_LED    = 17
KEY_DOWN   = 1
KEY_REPEAT = 2
LED_CAPSL = 1   # bit index of Caps Lock in EV_LED events

EVENT_FMT       = "qqHHi"
EVENT_SIZE      = struct.calcsize(EVENT_FMT)
DEBOUNCE        = 0.03  # seconds — per-key debounce for KEY_DOWN
                        #   prevents duplicate events from multiple /dev/input nodes
                        #   for the same physical key (duplicates arrive within ~5 ms)
DEBOUNCE_REPEAT = 0.04  # seconds — per-key debounce for KEY_REPEAT (held key)

# Per-key timestamps, shared across device threads via lock.
_play_lock    = threading.Lock()
_last_down:   dict[int, float] = {}   # code → time of last KEY_DOWN sound
_last_repeat: dict[int, float] = {}   # code → time of last KEY_REPEAT sound

# ── Key code → group ───────────────────────────────────────────────
_GROUPS: dict[str, set[int]] = {
    "typing": (
        set(range(2,  14))   # 1 2 3 4 5 6 7 8 9 0 - =
      | set(range(16, 28))   # q w e r t y u i o p [ ]
      | {41}                 # ` (grave / backtick)
      | set(range(30, 42))   # a s d f g h j k l ; '
      | {43}                 # backslash  \
      | set(range(44, 54))   # z x c v b n m , . /
    ),
    "action":   {14, 15, 28, 57},                              # Backspace Tab Enter Space
    "modifier": {29, 42, 54, 56, 58, 97, 100, 125, 126, 127}, # Ctrl Shift Alt Super CapsLock Compose
    "function": {1} | set(range(59, 69)) | {87, 88},           # Esc F1–F12
    "nav":      {102, 103, 104, 105, 106, 107, 108, 109, 110, 111}, # Home↑PgUp ←→ End↓PgDn Ins Del
}

CODE_TO_GROUP: dict[int, str] = {
    code: group
    for group, codes in _GROUPS.items()
    for code in codes
}

ALL_GROUP_NAMES = list(_GROUPS)


# ── Argument parsing ───────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Niri typing sound monitor")
    p.add_argument("focused_app_file",
                   help="File updated by sounds-daemon with the focused app_id")
    p.add_argument("--app", nargs="+", default=[], metavar="APP_ID",
                   help="Whitelist of app IDs (omit = all apps)")
    p.add_argument("--volume",       type=float, default=1.0,  metavar="F",
                   help="Base volume 0.0–1.0 (default 1.0)")
    p.add_argument("--night-start",  type=int,   default=22,   metavar="H",
                   help="Hour when night mode starts (default 22)")
    p.add_argument("--night-end",    type=int,   default=7,    metavar="H",
                   help="Hour when night mode ends   (default 7)")
    p.add_argument("--night-volume", type=float, default=0.3,  metavar="F",
                   help="Volume fraction during night (default 0.3 = 30%%)")
    p.add_argument("--caps-volume",  type=float, default=1.0,  metavar="F",
                   help="Extra volume multiplier when Caps Lock is on (default 1.0)")
    p.add_argument("--typing",   nargs="+", default=[], metavar="FILE",
                   help="Sounds for letters / numbers / punctuation")
    p.add_argument("--action",   nargs="+", default=[], metavar="FILE",
                   help="Sounds for Enter, Backspace, Space, Tab")
    p.add_argument("--modifier", nargs="+", default=[], metavar="FILE",
                   help="Sounds for Shift, Ctrl, Alt, Super, CapsLock")
    p.add_argument("--function", nargs="+", default=[], metavar="FILE",
                   help="Sounds for Esc, F1–F12")
    p.add_argument("--nav",      nargs="+", default=[], metavar="FILE",
                   help="Sounds for arrow keys, Home/End/PgUp/PgDn")
    p.add_argument("--typing-vol",   type=float, default=1.0, metavar="F",
                   help="Volume multiplier for typing group (default 1.0)")
    p.add_argument("--action-vol",   type=float, default=1.0, metavar="F",
                   help="Volume multiplier for action group (default 1.0)")
    p.add_argument("--modifier-vol", type=float, default=1.0, metavar="F",
                   help="Volume multiplier for modifier group (default 1.0)")
    p.add_argument("--function-vol", type=float, default=1.0, metavar="F",
                   help="Volume multiplier for function group (default 1.0)")
    p.add_argument("--nav-vol",      type=float, default=1.0, metavar="F",
                   help="Volume multiplier for nav group (default 1.0)")
    return p.parse_args()


# ── Helpers ────────────────────────────────────────────────────────
def is_night(start: int, end: int) -> bool:
    h = datetime.now().hour
    return (h >= start or h < end) if start > end else (start <= h < end)


def compute_volume(base: float, args: argparse.Namespace, caps_on: bool) -> float:
    v = base
    if is_night(args.night_start, args.night_end):
        v *= args.night_volume
    if caps_on:
        v *= args.caps_volume
    return v


def focused_app(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def pick(sounds: list[str], last: str | None) -> str:
    """Random choice, never repeating the previous file."""
    pool = [s for s in sounds if s != last] or sounds
    return random.choice(pool)


def play(sound: str, volume: float) -> None:
    # paplay --volume takes 0–65536 (65536 = 100%). Values above are valid
    # on PipeWire and allow a soft boost (e.g. caps-volume > 1.0).
    pa_vol = max(0, min(131072, round(volume * 65536)))
    subprocess.Popen(
        ["paplay", f"--volume={pa_vol}", sound],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def find_keyboards() -> list[str]:
    """Return /dev/input/eventN paths for devices with EV_KEY + EV_REP."""
    devices: list[str] = []
    try:
        content = Path("/proc/bus/input/devices").read_text()
        for block in content.split("\n\n"):
            lines = block.splitlines()
            ev_line = next((l for l in lines if "EV=" in l), "")
            if not ev_line:
                continue
            try:
                ev = int(ev_line.split("EV=")[1].split()[0], 16)
            except (IndexError, ValueError):
                continue
            # Must have EV_KEY (bit 1) and EV_REP (bit 20)
            if not (ev & 0x2 and ev & 0x100000):
                continue
            handlers = next((l for l in lines if l.startswith("H: Handlers=")), "")
            for token in handlers.split():
                if token.startswith("event"):
                    devices.append(f"/dev/input/{token}")
    except OSError as e:
        print(f"Cannot read /proc/bus/input/devices: {e}", file=sys.stderr)
    return devices


# ── Device reader ──────────────────────────────────────────────────
def read_device(
    path: str,
    args: argparse.Namespace,
    sounds_by_group: dict[str, list[str]],
    vol_by_group: dict[str, float],
    focused_path: Path,
    allowed_apps: set[str],
    last_sound: dict[str, str | None],
) -> None:
    caps_on = False

    try:
        with open(path, "rb") as f:
            while True:
                data = f.read(EVENT_SIZE)
                if len(data) < EVENT_SIZE:
                    break
                _, _, type_, code, value = struct.unpack(EVENT_FMT, data)

                # Track Caps Lock state via hardware LED events
                if type_ == EV_LED and code == LED_CAPSL:
                    caps_on = bool(value)
                    continue

                if type_ != EV_KEY or value not in (KEY_DOWN, KEY_REPEAT):
                    continue

                group = CODE_TO_GROUP.get(code)
                if group is None:
                    continue

                sounds = sounds_by_group.get(group) or []
                if not sounds:
                    continue

                if allowed_apps and focused_app(focused_path) not in allowed_apps:
                    continue

                now = time.monotonic()

                with _play_lock:
                    if value == KEY_DOWN:
                        if now - _last_down.get(code, 0) < DEBOUNCE:
                            continue
                        _last_down[code]   = now
                        _last_repeat[code] = now  # reset repeat timer on fresh press
                    else:  # KEY_REPEAT
                        if now - _last_repeat.get(code, 0) < DEBOUNCE_REPEAT:
                            continue
                        _last_repeat[code] = now

                    sound = pick(sounds, last_sound[group])
                    last_sound[group] = sound

                play(sound, compute_volume(args.volume * vol_by_group.get(group, 1.0), args, caps_on))

    except PermissionError:
        print(f"Permission denied: {path} (add user to 'input' group)", file=sys.stderr)
    except OSError as e:
        print(f"Error reading {path}: {e}", file=sys.stderr)
    print(f"Device closed: {path} — thread exiting", file=sys.stderr)


# ── Entry point ────────────────────────────────────────────────────
def main() -> None:
    args = parse_args()
    focused_path = Path(args.focused_app_file)
    allowed_apps = set(args.app)

    sounds_by_group: dict[str, list[str]] = {
        "typing":   args.typing,
        "action":   args.action,
        "modifier": args.modifier,
        "function": args.function,
        "nav":      args.nav,
    }

    for group, files in sounds_by_group.items():
        missing = [f for f in files if not Path(f).exists()]
        for f in missing:
            print(f"WARNING: sound file not found, skipping: {f}", file=sys.stderr)
        sounds_by_group[group] = [f for f in files if Path(f).exists()]

    vol_by_group: dict[str, float] = {
        "typing":   args.typing_vol,
        "action":   args.action_vol,
        "modifier": args.modifier_vol,
        "function": args.function_vol,
        "nav":      args.nav_vol,
    }

    keyboards = find_keyboards()
    if not keyboards:
        print("No keyboard devices found — typing sounds disabled", file=sys.stderr)
        sys.exit(1)

    active = [g for g, s in sounds_by_group.items() if s]
    print(
        f"Typing monitor: {len(keyboards)} device(s), "
        f"apps={allowed_apps or '{all}'}, "
        f"groups={active}",
        file=sys.stderr,
    )

    # Shared across threads: no-consecutive-repeat state per group
    last_sound: dict[str, str | None] = dict.fromkeys(ALL_GROUP_NAMES, None)

    threads = [
        threading.Thread(
            target=read_device,
            args=(kb, args, sounds_by_group, vol_by_group, focused_path, allowed_apps, last_sound),
            daemon=True,
        )
        for kb in keyboards
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
