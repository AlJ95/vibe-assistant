"""Führt Desktop-Aktionen aus (X11 → xdotool)."""
import shlex
import shutil
import subprocess

from . import config

# Alias-Normalisierung für Tastennamen (LLM → xdotool)
_KEY_ALIASES = {
    "control": "ctrl", "strg": "ctrl", "cmd": "super", "win": "super",
    "meta": "super", "return": "Return", "enter": "Return", "escape": "Escape",
    "esc": "Escape", "space": "space", "tab": "Tab", "backspace": "BackSpace",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "delete": "Delete", "del": "Delete", "home": "Home", "end": "End",
    "pageup": "Page_Up", "pagedown": "Page_Down",
}


def _run(args, check=True):
    subprocess.run(args, check=check, capture_output=True)


def type_text(text: str):
    """Tippt Text in das fokussierte Fenster."""
    _run(["xdotool", "type", "--clearmodifiers", "--delay", "20", "--", text])


def press_keys(keys):
    """Drückt eine Tastenkombination (Liste von Tastennamen)."""
    normalized = [_KEY_ALIASES.get(str(k).lower(), str(k).lower()) for k in keys]
    _run(["xdotool", "key", "--clearmodifiers", "+".join(normalized)])


def click(x: int, y: int, button: str = "left"):
    """Klickt an Bildschirmkoordinaten."""
    btn = {"left": "1", "middle": "2", "right": "3"}.get(str(button).lower(), "1")
    _run(["xdotool", "mousemove", str(int(x)), str(int(y))])
    _run(["xdotool", "click", btn])


def focus_window(name: str):
    """Sucht und fokussiert ein Fenster per Namensfragment."""
    res = subprocess.run(
        ["xdotool", "search", "--name", name], capture_output=True, text=True
    )
    ids = [ln for ln in res.stdout.splitlines() if ln.strip().isdigit()]
    if not ids:
        # Fallback: Suche nach Klasse
        res = subprocess.run(
            ["xdotool", "search", "--class", name], capture_output=True, text=True
        )
        ids = [ln for ln in res.stdout.splitlines() if ln.strip().isdigit()]
    if ids:
        _run(["xdotool", "windowactivate", "--sync", ids[0]])


def open_app(name: str):
    """Öffnet eine Anwendung (gtk-launch, Fallback: direkter Befehl)."""
    if shutil.which("gtk-launch"):
        r = subprocess.run(["gtk-launch", name], capture_output=True)
        if r.returncode == 0:
            return
    subprocess.Popen(
        [name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def run_command(command: str):
    """Führt ein Shell-Kommando aus (nur bei Whitelist-Treffer)."""
    prefix = command.strip().split()[0] if command.strip() else ""
    if not any(prefix.startswith(p) for p in config.ALLOWED_COMMAND_PREFIXES):
        print(f"[executor] run_command blockiert (nicht in Whitelist): {command!r}")
        return
    subprocess.Popen(
        shlex.split(command), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


_HANDLERS = {
    "type_text": lambda a: type_text(a["text"]),
    "press_keys": lambda a: press_keys(a["keys"]),
    "click": lambda a: click(a["x"], a["y"], a.get("button", "left")),
    "open_app": lambda a: open_app(a["name"]),
    "focus_window": lambda a: focus_window(a["name"]),
    "run_command": lambda a: run_command(a["command"]),
}


def execute(name: str, args: dict):
    """Führt einen Tool-Call aus (Name + Argumente)."""
    handler = _HANDLERS.get(name)
    if handler is None:
        print(f"[executor] Unbekanntes Tool: {name}")
        return
    print(f"[executor] {name}({args})")
    handler(args)
