"""Führt Desktop-Aktionen aus (X11 → xdotool)."""
import shlex
import shutil
import subprocess
import time

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


# Skalierung Bild-Koordinaten → Bildschirm-Koordinaten (wird von der Action-Engine
# nach jedem Screenshot gesetzt; Default 1:1, falls nichts skaliert wurde).
_click_scale = (1.0, 1.0)


def set_click_scale(sx: float, sy: float):
    """Setzt die aktuelle Bild→Bildschirm-Skalierung für Klicks."""
    global _click_scale
    _click_scale = (float(sx), float(sy))


def type_text(text: str):
    """Tippt Text in das fokussierte Fenster."""
    _run(["xdotool", "type", "--clearmodifiers", "--delay", "20", "--", text])


def press_keys(keys):
    """Drückt eine Tastenkombination (Liste von Tastennamen)."""
    normalized = [_KEY_ALIASES.get(str(k).lower(), str(k).lower()) for k in keys]
    _run(["xdotool", "key", "--clearmodifiers", "+".join(normalized)])


def click(x: int, y: int, button: str = "left"):
    """Klickt an Bildschirmkoordinaten (Bild-Koordinaten werden skaliert)."""
    btn = {"left": "1", "middle": "2", "right": "3"}.get(str(button).lower(), "1")
    sx, sy = _click_scale
    _run(["xdotool", "mousemove", str(int(round(x * sx))), str(int(round(y * sy)))])
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
            print(f"[executor] gtk-launch {name!r} OK")
            return
        print(f"[executor] gtk-launch {name!r} fehlgeschlagen (rc={r.returncode}, "
              f"stderr={r.stderr.decode(errors='ignore')[:100]})")
    if shutil.which(name):
        subprocess.Popen(
            [name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print(f"[executor] {name!r} als Befehl gestartet")
        return
    raise FileNotFoundError(
        f"Anwendung {name!r} nicht gefunden (weder Desktop-Eintrag via gtk-launch "
        f"noch Befehl im PATH)"
    )


def wait_for(name: str, timeout: int = 15):
    """Wartet, bis 'name' als Fenster (wmctrl) oder Prozess (pgrep) erscheint.

    Wird nach open_app aufgerufen, wenn eine App Zeit zum Laden braucht.
    Pollt alle 0,5 s. Sobald der Prozess läuft, wartet sie noch kurz auf ein
    sichtbares Fenster; kommt keins, meldet sie den Prozess-Status zurück.
    """
    name = (name or "").strip()
    if not name:
        return "wait_for: kein Name angegeben."
    try:
        timeout = max(1, min(int(timeout), 30))
    except (TypeError, ValueError):
        timeout = 15
    deadline = time.monotonic() + timeout
    started = time.monotonic()
    proc_seen_at = None

    def _window_seen():
        try:
            out = subprocess.run(["wmctrl", "-l"], capture_output=True,
                                 text=True, timeout=3).stdout
            return any(name.lower() in ln.lower() for ln in out.splitlines())
        except Exception:
            return False

    def _proc_running():
        try:
            r = subprocess.run(["pgrep", "-if", name], capture_output=True,
                               text=True, timeout=3)
            return r.returncode == 0 and r.stdout.strip() != ""
        except Exception:
            return False

    while time.monotonic() < deadline:
        if _window_seen():
            return (f"Fenster '{name}' erschienen nach "
                    f"{time.monotonic() - started:.1f}s — bereit.")
        if _proc_running():
            if proc_seen_at is None:
                proc_seen_at = time.monotonic()
            # Prozess läuft: noch bis zu 2,5 s aufs Fenster warten
            if time.monotonic() - proc_seen_at >= 2.5:
                return (f"Prozess '{name}' läuft seit "
                        f"{time.monotonic() - started:.1f}s (Fenster noch nicht "
                        f"sichtbar — Screenshot prüfen, ggf. erneut wait_for).")
        time.sleep(0.5)
    if proc_seen_at is not None:
        return (f"Timeout nach {timeout}s: Prozess '{name}' läuft, aber kein "
                f"Fenster erschienen — Screenshot prüfen.")
    return (f"Timeout nach {timeout}s: '{name}' weder als Fenster noch als "
            f"Prozess gefunden.")


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
    "wait_for": lambda a: wait_for(a.get("name", ""), a.get("timeout", 15)),
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
