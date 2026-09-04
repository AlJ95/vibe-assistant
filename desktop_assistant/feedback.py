"""Audio-Feedback (Töne) und Desktop-Toast (Benachrichtigung).

Nur zwei Ereignisse erzeugen Feedback:
  1. Task-Start  -> play_start()  (VAD erkannt, Aufgabe beginnt)
  2. Task-Ende   -> play_done() + notify("Task successful", ...)
"""
import shutil
import subprocess

import numpy as np
import sounddevice as sd

_SR = 44100  # Sample-Rate der erzeugten Töne


def _tone(freq: float, duration: float, volume: float = 0.35) -> np.ndarray:
    """Erzeugt einen kurzen Sinus-Ton mit Fade-Rampen gegen Knacksen."""
    t = np.linspace(0.0, duration, int(_SR * duration), endpoint=False)
    wave = np.sin(2.0 * np.pi * freq * t) * volume
    n = max(1, int(_SR * 0.008))  # 8 ms Fade
    if 2 * n < len(wave):
        env = np.ones_like(wave)
        env[:n] = np.linspace(0.0, 1.0, n)
        env[-n:] = np.linspace(1.0, 0.0, n)
        wave = wave * env
    return wave.astype(np.float32)


def _play(wave: np.ndarray):
    """Spielt einen Ton ab (nicht-blockierend, damit der Worker nicht hängt)."""
    try:
        sd.play(wave, _SR, blocking=False)
    except Exception as e:
        print(f"[feedback] Ton fehlgeschlagen: {e}")


def play_start():
    """Ton beim Task-Start (VAD erkannt, Aufgabe beginnt)."""
    _play(_tone(660.0, 0.10))


def play_done():
    """Ton beim Task-Ende (Aufgabe fertig)."""
    _play(_tone(990.0, 0.16))


def notify(title: str, message: str, icon=None):
    """Zeigt einen Desktop-Toast. Primär notify-send (GNOME), Fallback pystray."""
    if shutil.which("notify-send"):
        try:
            subprocess.run(
                ["notify-send", "-a", "Vibe Assistant", title, message],
                capture_output=True, timeout=5,
            )
            return
        except Exception as e:
            print(f"[feedback] notify-send fehlgeschlagen: {e}")
    if icon is not None:
        try:
            icon.notify(message, title)
        except Exception as e:
            print(f"[feedback] pystray-notify fehlgeschlagen: {e}")
