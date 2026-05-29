#!/usr/bin/env python3
"""Niri Sounds TUI — profile editor for sounds-daemon.sh"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    from textual import on
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, ScrollableContainer, Vertical
    from textual.screen import ModalScreen
    from textual.widgets import (
        Button, Checkbox, Footer, Header, Input, Label,
        ListItem, ListView, Static, TabbedContent, TabPane, TextArea,
    )
except ImportError:
    sys.exit("textual не установлен.  Установи: sudo pacman -S python-textual")

NIRI_DIR     = Path(__file__).resolve().parent.parent  # source/ → project root
PROFILES_DIR = NIRI_DIR / "profiles"
SOUNDS_BASE  = NIRI_DIR / "sounds"
DAEMON       = NIRI_DIR / "source" / "sounds-daemon.sh"
AUTOSTART    = Path.home() / ".config/niri/cfg/autostart.kdl"

GLOBAL_SOUNDS = [
    ("snd_window_open",  "Window Open"),
    ("snd_window_close", "Window Close"),
    ("snd_workspace",    "Workspace"),
    ("snd_overview",     "Overview"),
    ("snd_media_start",  "Media Start"),
]
TYPING_GROUPS = [
    ("snd_typing_typing",   "Letters / digits / punctuation"),
    ("snd_typing_action",   "Enter / Backspace / Space / Tab"),
    ("snd_typing_modifier", "Shift / Ctrl / Alt / Super / CapsLock"),
    ("snd_typing_function", "F1–F12 / Escape"),
    ("snd_typing_nav",      "Arrows / Home / End / PgUp / PgDn"),
]


# ── Profile dataclass ──────────────────────────────────────────────
@dataclass
class Profile:
    name:                str       = ""
    snd_window_open:     str       = ""
    snd_window_close:    str       = ""
    snd_workspace:       str       = ""
    snd_overview:        str       = ""
    snd_media_start:     str       = ""
    typing_apps:         list[str] = field(default_factory=list)
    typing_volume:       float     = 1.0
    night_start:         int       = 22
    night_end:           int       = 7
    night_volume:        float     = 0.3
    caps_volume:         float     = 1.0
    snd_typing_typing:   list[str] = field(default_factory=list)
    snd_typing_action:   list[str] = field(default_factory=list)
    snd_typing_modifier: list[str] = field(default_factory=list)
    snd_typing_function: list[str] = field(default_factory=list)
    snd_typing_nav:      list[str] = field(default_factory=list)


# ── I/O ────────────────────────────────────────────────────────────
def _expand(v: str, sd: Path) -> str:
    return (v.replace("$SOUNDS_DIR", str(sd)).replace("${SOUNDS_DIR}", str(sd))
             .replace("$NIRI_DIR", str(NIRI_DIR)).replace("${NIRI_DIR}", str(NIRI_DIR)))

def _collapse(v: str, sd: Path) -> str:
    return v.replace(str(sd), "$SOUNDS_DIR") if v else ""

def _read_scalar(text: str, var: str, sd: Path, default: str = "") -> str:
    m = re.search(rf'^{re.escape(var)}=(.*)$', text, re.MULTILINE)
    if not m:
        return default
    return _expand(m.group(1).strip().strip('"').strip("'"), sd)

def _read_array(text: str, var: str, sd: Path) -> list[str]:
    m = re.search(rf'^{re.escape(var)}=(\(.*?\))', text, re.MULTILINE)
    if not m:
        return []
    inner = m.group(1)[1:-1].strip()
    if not inner:
        return []
    items = re.findall(r'"([^"]*)"', inner) or inner.split()
    return [_expand(i, sd) for i in items if i.strip()]

def _write_array(items: list[str], sd: Path) -> str:
    if not items:
        return "()"
    return "( " + " ".join(f'"{_collapse(i, sd)}"' for i in items if i) + " )"

def _safe_float(v: str, d: float) -> float:
    try: return float(v)
    except ValueError: return d

def _safe_int(v: str, d: int) -> int:
    try: return int(v)
    except ValueError: return d

def load_profile(name: str) -> Profile:
    text = (PROFILES_DIR / f"{name}.sh").read_text()
    sd   = SOUNDS_BASE / name
    s    = lambda v, d="": _read_scalar(text, v, sd, d)
    a    = lambda v:        _read_array(text, v, sd)
    return Profile(
        name=name,
        snd_window_open=s("SND_WINDOW_OPEN"),    snd_window_close=s("SND_WINDOW_CLOSE"),
        snd_workspace=s("SND_WORKSPACE"),          snd_overview=s("SND_OVERVIEW"),
        snd_media_start=s("SND_MEDIA_START"),
        typing_apps=a("TYPING_APPS"),
        typing_volume=_safe_float(s("TYPING_VOLUME", "1.0"), 1.0),
        night_start=_safe_int(s("NIGHT_START", "22"), 22),
        night_end=_safe_int(s("NIGHT_END", "7"), 7),
        night_volume=_safe_float(s("NIGHT_VOLUME", "0.3"), 0.3),
        caps_volume=_safe_float(s("CAPS_VOLUME", "1.0"), 1.0),
        snd_typing_typing=a("SND_TYPING_TYPING"),    snd_typing_action=a("SND_TYPING_ACTION"),
        snd_typing_modifier=a("SND_TYPING_MODIFIER"), snd_typing_function=a("SND_TYPING_FUNCTION"),
        snd_typing_nav=a("SND_TYPING_NAV"),
    )

def save_profile(p: Profile) -> None:
    sd = SOUNDS_BASE / p.name
    c  = lambda v: _collapse(v, sd)
    wa = lambda v: _write_array(v, sd)
    PROFILES_DIR.mkdir(exist_ok=True)
    (PROFILES_DIR / f"{p.name}.sh").write_text(
        f"SOUNDS_DIR=$NIRI_DIR/sounds/{p.name}\n\n"
        f"SND_WINDOW_OPEN={c(p.snd_window_open)}\n"
        f"SND_WINDOW_CLOSE={c(p.snd_window_close)}\n"
        f"SND_WORKSPACE={c(p.snd_workspace)}\n"
        f"SND_OVERVIEW={c(p.snd_overview)}\n"
        f"SND_MEDIA_START={c(p.snd_media_start)}\n\n"
        f"TYPING_APPS={wa(p.typing_apps)}\n\n"
        f"TYPING_VOLUME={p.typing_volume}\n"
        f"NIGHT_START={p.night_start}\n"
        f"NIGHT_END={p.night_end}\n"
        f"NIGHT_VOLUME={p.night_volume}\n"
        f"CAPS_VOLUME={p.caps_volume}\n\n"
        f"SND_TYPING_TYPING={wa(p.snd_typing_typing)}\n"
        f"SND_TYPING_ACTION={wa(p.snd_typing_action)}\n"
        f"SND_TYPING_MODIFIER={wa(p.snd_typing_modifier)}\n"
        f"SND_TYPING_FUNCTION={wa(p.snd_typing_function)}\n"
        f"SND_TYPING_NAV={wa(p.snd_typing_nav)}\n"
    )

def list_profiles() -> list[str]:
    if not PROFILES_DIR.exists(): return []
    return sorted(f.stem for f in PROFILES_DIR.glob("*.sh"))

def active_profile() -> str:
    if not DAEMON.exists(): return ""
    m = re.search(r'^PROFILE=(\S+)', DAEMON.read_text(), re.MULTILINE)
    return m.group(1) if m else ""

def set_default(name: str) -> None:
    text = DAEMON.read_text()
    DAEMON.write_text(re.sub(r'^PROFILE=\S+', f"PROFILE={name}", text, flags=re.MULTILINE))

def is_in_autostart() -> bool:
    if not AUTOSTART.exists():
        return False
    return str(DAEMON) in AUTOSTART.read_text()

def add_to_autostart() -> None:
    with open(AUTOSTART, "a") as f:
        f.write(f'    spawn-at-startup "bash" "{DAEMON}"\n')

def remove_from_autostart() -> None:
    text = AUTOSTART.read_text()
    AUTOSTART.write_text("".join(
        l for l in text.splitlines(keepends=True) if str(DAEMON) not in l
    ))

def is_daemon_running() -> bool:
    return subprocess.run(
        ["pgrep", "-f", "sounds-daemon.sh"], capture_output=True
    ).returncode == 0

def launch_daemon() -> None:
    subprocess.run(
        ["bash", "-c", f'nohup bash "{DAEMON}" >/tmp/sounds-daemon.log 2>&1 &'],
        check=False,
    )

def stop_daemon() -> None:
    # grep -vx $$ excludes the current bash subprocess's own PID from the kill list,
    # preventing pgrep -f from matching "sounds-daemon.sh" inside this very command string.
    subprocess.run(
        ["bash", "-c",
         'pgrep -f "sounds-daemon.sh|typing-monitor.py" | grep -vx $$ | xargs -r kill -9 2>/dev/null'],
        check=False,
    )

def restart_daemon() -> None:
    stop_daemon()
    launch_daemon()


# ── Name input modal ───────────────────────────────────────────────
class NameModal(ModalScreen[str | None]):
    DEFAULT_CSS = """
    NameModal { align: center middle; }
    #dialog {
        width: 52; height: auto;
        background: $surface; border: solid $primary;
        padding: 1 2;
    }
    #dialog-btns { height: auto; align: center middle; margin-top: 1; }
    """
    def __init__(self, prompt: str) -> None:
        super().__init__()
        self._prompt = prompt

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._prompt)
            yield Input(id="inp", placeholder="имя профиля")
            with Horizontal(id="dialog-btns"):
                yield Button("OK",     id="ok",     variant="primary")
                yield Button("Отмена", id="cancel", variant="default")

    @on(Button.Pressed, "#ok")
    @on(Input.Submitted)
    def _ok(self) -> None:
        val = self.query_one("#inp", Input).value.strip()
        self.dismiss(val or None)

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)


# ── Main app ───────────────────────────────────────────────────────
class SoundsApp(App):
    TITLE = "Niri Sounds — Profile Editor"
    CSS = """
Screen { layout: vertical; }

/* ── Autostart banner ── */
#autostart-banner {
    height: 3;
    layout: horizontal;
    padding: 0 2;
    align: left middle;
}
#autostart-banner.ok   { background: $success; color: white; }
#autostart-banner.warn { background: $error;   color: white; }
#banner-label  { width: 1fr; content-align: left middle; }
#btn-autostart { min-width: 14; }

/* ── Main area ── */
#main { width: 1fr; height: 1fr; layout: horizontal; }

/* ── Left panel ── */
#left {
    width: 22; height: 1fr;
    layout: vertical;
    border: solid $primary;
    padding: 0 1;
}
#profile-list { height: 1fr; }
#left-btns { height: auto; padding: 0; }

/* ── Right panel ── */
#right { width: 1fr; height: 1fr; layout: vertical; border: solid $primary; }
#tabs  { height: 1fr; }
#bottom { height: 3; align: right middle; padding: 0 1; }

/* ── Global sounds tab ── */
.sound-row { height: 3; align: left middle; }
.sound-cb  { width: 26; }
.sound-inp { width: 1fr; }

/* ── Typing groups tab ── */
.group-cb   { width: 1fr; }
.group-body { padding-left: 4; height: auto; }
.group-hint { color: $text-muted; height: auto; }
TextArea    { height: 4; margin-bottom: 1; }

/* ── Volume/Night tab ── */
.vol-row   { height: 3; align: left middle; }
.vol-label { width: 32; padding: 0 1; }
.vol-inp   { width: 20; }

/* ── Apps tab ── */
.apps-hint { color: $text-muted; height: auto; margin-bottom: 1; }

"""
    BINDINGS = [
        ("ctrl+s", "save",     "Save"),
        ("ctrl+d", "default",  "Set as Default"),
        ("ctrl+r", "apply",    "Apply"),
        ("q",      "app.quit", "Quit"),
    ]

    _profile: Profile | None = None

    def _notify(self, message: str, severity: str = "information") -> None:
        if shutil.which("notify-send"):
            urgency = {"error": "critical", "warning": "normal"}.get(severity, "low")
            subprocess.Popen(
                ["notify-send", "-u", urgency, "Niri Sounds", message],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            self._notify(message, severity=severity, timeout=2)  # type: ignore[arg-type]

    # ── Layout ─────────────────────────────────────────────────────
    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal(id="autostart-banner"):
            yield Label("", id="banner-label")
            yield Button("", id="btn-autostart")

        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield Label("─ Profiles ─")
                yield ListView(id="profile-list")
                with Horizontal(id="left-btns"):
                    yield Button("New", id="btn-new", variant="default")
                    yield Button("Dup", id="btn-dup", variant="default")
                    yield Button("Del", id="btn-del", variant="error")

            with Vertical(id="right"):
                with TabbedContent(id="tabs"):

                    # ── Tab 1: Global Sounds ──────────────────────────
                    with TabPane("Global Sounds"):
                        with ScrollableContainer():
                            for fid, lbl in GLOBAL_SOUNDS:
                                with Horizontal(classes="sound-row"):
                                    yield Checkbox(lbl, id=f"cb-{fid}", classes="sound-cb")
                                    yield Input(id=f"f-{fid}", classes="sound-inp",
                                                placeholder="путь к файлу…")

                    # ── Tab 2: Typing Sounds ──────────────────────────
                    with TabPane("Typing Sounds"):
                        with ScrollableContainer():
                            for fid, lbl in TYPING_GROUPS:
                                yield Checkbox(lbl, id=f"cb-{fid}", classes="group-cb")
                                with Vertical(id=f"body-{fid}", classes="group-body"):
                                    yield Static("один путь на строку", classes="group-hint")
                                    yield TextArea(id=f"f-{fid}")

                    # ── Tab 3: Volume & Night ─────────────────────────
                    with TabPane("Volume & Night"):
                        with ScrollableContainer():
                            for fid, lbl in [
                                ("typing_volume", "Base volume  (0.0 – 1.0)"),
                                ("night_volume",  "Night volume  (доля 0.0 – 1.0)"),
                                ("caps_volume",   "Caps Lock multiplier"),
                                ("night_start",   "Night start  (час 0–23)"),
                                ("night_end",     "Night end    (час 0–23)"),
                            ]:
                                with Horizontal(classes="vol-row"):
                                    yield Label(lbl, classes="vol-label")
                                    yield Input(id=f"f-{fid}", classes="vol-inp")

                    # ── Tab 4: Apps ───────────────────────────────────
                    with TabPane("Apps"):
                        with ScrollableContainer():
                            yield Static(
                                "Whitelist app_id — один на строку.\n"
                                "Пусто = звуки во всех приложениях.\n"
                                "Узнать app_id:  niri msg focused-window | grep app_id",
                                classes="apps-hint",
                            )
                            yield TextArea(id="f-typing_apps")

                with Horizontal(id="bottom"):
                    yield Button("Save",            id="btn-save",    variant="primary")
                    yield Button("Set as Default",  id="btn-default", variant="default")
                    yield Button("Stop",            id="btn-stop",    variant="error")
                    yield Button("Apply & Restart", id="btn-apply",   variant="success")

        yield Footer()

    # ── Startup ────────────────────────────────────────────────────
    def on_mount(self) -> None:
        self._reload_list()
        self._refresh_status()

    def _refresh_status(self) -> None:
        in_as   = is_in_autostart()
        running = is_daemon_running()

        banner    = self.query_one("#autostart-banner")
        lbl       = self.query_one("#banner-label", Label)
        btn_as    = self.query_one("#btn-autostart", Button)
        btn_stop  = self.query_one("#btn-stop",  Button)
        btn_apply = self.query_one("#btn-apply", Button)

        if in_as:
            banner.remove_class("warn")
            banner.add_class("ok")
            lbl.update("✓ App is added to autostart. All good.")
            btn_as.label   = "Remove"
            btn_as.variant = "default"
        else:
            banner.remove_class("ok")
            banner.add_class("warn")
            lbl.update("✗ App is not added to autostart. Add? (recommended)")
            btn_as.label   = "Add"
            btn_as.variant = "success"

        if running:
            btn_stop.display  = True
            btn_apply.label   = "Apply & Restart"
            btn_apply.variant = "success"
        else:
            btn_stop.display  = False
            btn_apply.label   = "Launch"
            btn_apply.variant = "primary"

    def _reload_list(self, select: str | None = None) -> None:
        lv     = self.query_one("#profile-list", ListView)
        lv.clear()
        names  = list_profiles()
        cur    = active_profile()
        target = select or cur or (names[0] if names else None)
        for i, name in enumerate(names):
            marker = "▶ " if name == cur else "  "
            lv.append(ListItem(Label(f"{marker}{name}"), name=name))
            if name == target:
                lv.index = i
        if target:
            self._load(target)

    # ── Load profile into form ─────────────────────────────────────
    def _load(self, name: str) -> None:
        try:
            p = load_profile(name)
        except Exception as e:
            self._notify(f"Ошибка загрузки: {e}", severity="error")
            return
        self._profile = p
        self.sub_title = name

        for fid, _ in GLOBAL_SOUNDS:
            val = getattr(p, fid)
            enabled = bool(val)
            try: self.query_one(f"#cb-{fid}", Checkbox).value = enabled
            except Exception: pass
            try: self.query_one(f"#f-{fid}", Input).value = val
            except Exception: pass
            try: self.query_one(f"#f-{fid}").display = enabled
            except Exception: pass

        for fid, _ in TYPING_GROUPS:
            items   = getattr(p, fid)
            enabled = bool(items)
            try: self.query_one(f"#cb-{fid}", Checkbox).value = enabled
            except Exception: pass
            try: self.query_one(f"#f-{fid}", TextArea).load_text("\n".join(items))
            except Exception: pass
            try: self.query_one(f"#body-{fid}").display = enabled
            except Exception: pass

        for fid, val in [
            ("typing_volume", str(p.typing_volume)),
            ("night_volume",  str(p.night_volume)),
            ("caps_volume",   str(p.caps_volume)),
            ("night_start",   str(p.night_start)),
            ("night_end",     str(p.night_end)),
        ]:
            try: self.query_one(f"#f-{fid}", Input).value = val
            except Exception: pass

        try:
            self.query_one("#f-typing_apps", TextArea).load_text("\n".join(p.typing_apps))
        except Exception:
            pass

    # ── Collect form → Profile ─────────────────────────────────────
    def _collect(self) -> Profile | None:
        if self._profile is None:
            return None

        def gi(fid: str) -> str:
            try: return self.query_one(f"#f-{fid}", Input).value.strip()
            except Exception: return ""

        def gcb(fid: str) -> bool:
            try: return bool(self.query_one(f"#cb-{fid}", Checkbox).value)
            except Exception: return False

        def gta(fid: str) -> list[str]:
            try:
                return [ln.strip() for ln in
                        self.query_one(f"#f-{fid}", TextArea).text.splitlines()
                        if ln.strip()]
            except Exception: return []

        def flt(fid: str, d: float) -> float:
            try: return float(gi(fid))
            except ValueError: return d

        def intt(fid: str, d: int) -> int:
            try: return int(gi(fid))
            except ValueError: return d

        return Profile(
            name=self._profile.name,
            snd_window_open=  gi("snd_window_open")  if gcb("snd_window_open")  else "",
            snd_window_close= gi("snd_window_close") if gcb("snd_window_close") else "",
            snd_workspace=    gi("snd_workspace")    if gcb("snd_workspace")    else "",
            snd_overview=     gi("snd_overview")     if gcb("snd_overview")     else "",
            snd_media_start=  gi("snd_media_start")  if gcb("snd_media_start")  else "",
            typing_apps=gta("typing_apps"),
            typing_volume=flt("typing_volume", 1.0),
            night_start=intt("night_start", 22),
            night_end=intt("night_end", 7),
            night_volume=flt("night_volume", 0.3),
            caps_volume=flt("caps_volume", 1.0),
            snd_typing_typing=  gta("snd_typing_typing")   if gcb("snd_typing_typing")   else [],
            snd_typing_action=  gta("snd_typing_action")   if gcb("snd_typing_action")   else [],
            snd_typing_modifier=gta("snd_typing_modifier") if gcb("snd_typing_modifier") else [],
            snd_typing_function=gta("snd_typing_function") if gcb("snd_typing_function") else [],
            snd_typing_nav=     gta("snd_typing_nav")      if gcb("snd_typing_nav")      else [],
        )

    # ── Checkbox toggles (show/hide dependent fields) ──────────────
    @on(Checkbox.Changed)
    def _on_checkbox(self, event: Checkbox.Changed) -> None:
        cb_id = event.checkbox.id
        if not cb_id or not cb_id.startswith("cb-"):
            return
        fid = cb_id[3:]
        vis = event.value
        try: self.query_one(f"#f-{fid}", Input).display = vis
        except Exception: pass
        try: self.query_one(f"#body-{fid}").display = vis
        except Exception: pass

    # ── Autostart toggle ───────────────────────────────────────────
    @on(Button.Pressed, "#btn-autostart")
    def _on_autostart_toggle(self) -> None:
        if is_in_autostart():
            try:
                remove_from_autostart()
                self._notify("Removed from autostart")
            except Exception as e:
                self._notify(f"Error: {e}", severity="error")
        else:
            if not AUTOSTART.exists():
                self._notify("Autostart file not found", severity="warning")
                return
            try:
                add_to_autostart()
                self._notify("Added to autostart")
            except Exception as e:
                self._notify(f"Error: {e}", severity="error")
        self._refresh_status()

    # ── Stop daemon ────────────────────────────────────────────────
    @on(Button.Pressed, "#btn-stop")
    def _on_stop(self) -> None:
        stop_daemon()
        self._notify("Daemon stopped")
        self._refresh_status()

    # ── Profile list ───────────────────────────────────────────────
    @on(ListView.Selected)
    def _on_select(self, event: ListView.Selected) -> None:
        if event.item.name:
            self._load(event.item.name)

    @on(Button.Pressed, "#btn-new")
    def _on_new(self) -> None:
        def done(name: str | None) -> None:
            if not name:
                return
            if (PROFILES_DIR / f"{name}.sh").exists():
                self._notify(f"Профиль '{name}' уже существует", severity="warning")
                return
            (SOUNDS_BASE / name).mkdir(parents=True, exist_ok=True)
            save_profile(Profile(name=name))
            self._reload_list(select=name)
            self._notify(f"Создан профиль '{name}'")
        self.push_screen(NameModal("Имя нового профиля"), done)

    @on(Button.Pressed, "#btn-dup")
    def _on_dup(self) -> None:
        if not self._profile:
            return
        src = self._profile.name
        def done(name: str | None) -> None:
            if not name:
                return
            if (PROFILES_DIR / f"{name}.sh").exists():
                self._notify(f"'{name}' уже существует", severity="warning")
                return
            p      = load_profile(src)
            p.name = name
            (SOUNDS_BASE / name).mkdir(parents=True, exist_ok=True)
            src_sd = SOUNDS_BASE / src
            if src_sd.exists():
                shutil.copytree(src_sd, SOUNDS_BASE / name, dirs_exist_ok=True)
            save_profile(p)
            self._reload_list(select=name)
            self._notify(f"Дублирован '{src}' → '{name}'")
        self.push_screen(NameModal(f"Дублировать '{src}' как"), done)

    @on(Button.Pressed, "#btn-del")
    def _on_del(self) -> None:
        if not self._profile:
            return
        name = self._profile.name
        if len(list_profiles()) <= 1:
            self._notify("Нельзя удалить последний профиль", severity="warning")
            return
        (PROFILES_DIR / f"{name}.sh").unlink(missing_ok=True)
        self._profile = None
        self._reload_list()
        self._notify(f"Удалён профиль '{name}'")

    # ── Save / Default / Apply ─────────────────────────────────────
    @on(Button.Pressed, "#btn-save")
    def action_save(self) -> None:
        p = self._collect()
        if not p:
            return
        try:
            save_profile(p)
            self._profile = p
            self._notify(f"Сохранён '{p.name}'")
        except Exception as e:
            self._notify(f"Ошибка сохранения: {e}", severity="error")

    @on(Button.Pressed, "#btn-default")
    def action_default(self) -> None:
        p = self._collect()
        if not p:
            return
        try:
            save_profile(p)
            set_default(p.name)
            self._profile = p
            self._reload_list(select=p.name)
            self._notify(f"'{p.name}' установлен по умолчанию")
        except Exception as e:
            self._notify(f"Ошибка: {e}", severity="error")

    @on(Button.Pressed, "#btn-apply")
    def action_apply(self) -> None:
        p = self._collect()
        if not p:
            return
        try:
            save_profile(p)
            set_default(p.name)
            self._profile = p
            self._reload_list(select=p.name)
            if is_daemon_running():
                restart_daemon()
                self._notify(f"Applied '{p.name}' — daemon restarted")
            else:
                launch_daemon()
                self._notify(f"Applied '{p.name}' — daemon launched")
            self._refresh_status()
        except Exception as e:
            self._notify(f"Ошибка применения: {e}", severity="error")


if __name__ == "__main__":
    SoundsApp().run()
