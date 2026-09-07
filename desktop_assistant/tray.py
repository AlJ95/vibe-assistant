"""Tray-Icon (pystray + AppIndicator): Aktiviert/Deaktiviert/Modell/Beenden."""
import os
import threading
import time

import pystray
from PIL import Image, ImageDraw

from . import config


def _model_label(slug: str) -> str:
    for s, label in config.ACTION_MODELS:
        if s == slug:
            return label
    return slug


class Tray:
    def __init__(self, audio, on_quit):
        self.audio = audio
        self.on_quit = on_quit
        self.active = True  # default: aktiviert
        self.icon = pystray.Icon(
            "desktop-assistant",
            icon=self._make_icon(self.active),
            title=self._title(),
            menu=self._build_menu(),
        )

    def _title(self) -> str:
        return f"Vibe Assistant — {_model_label(config.ACTION_MODEL)}"

    def _make_icon(self, active):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        color = (52, 211, 153, 255) if active else (100, 116, 139, 255)
        d.ellipse([6, 6, 58, 58], fill=color)
        d.ellipse([22, 22, 42, 42], fill=(2, 6, 23, 255))
        return img

    def _build_menu(self):
        model_items = [
            pystray.MenuItem(
                label,
                self._make_model_cb(slug),
                checked=lambda item, s=slug: config.ACTION_MODEL == s,
                radio=True,
            )
            for slug, label in config.ACTION_MODELS
        ]
        return pystray.Menu(
            pystray.MenuItem("Aktiviert", self._toggle_active,
                             checked=lambda item: self.active),
            pystray.MenuItem("Modell", pystray.Menu(*model_items)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Beenden", self._quit),
        )

    def _make_model_cb(self, slug):
        def cb(icon, item):
            config.ACTION_MODEL = slug
            icon.title = self._title()
            icon.update_menu()
            print(f"[tray] Action-Modell: {slug}")
        return cb

    def _toggle_active(self, icon, item):
        self.active = not self.active
        self.audio.set_active(self.active)
        icon.icon = self._make_icon(self.active)
        icon.update_menu()
        print(f"[tray] {'aktiviert' if self.active else 'deaktiviert'}")

    def _quit(self, icon, item):
        self.on_quit()
        # pystray/AppIndicator: icon.stop() aus dem Callback kann blockieren und
        # Threads (GTK/Executor) halten den Prozess → Sicherheitsnetz erzwingt Exit.
        threading.Thread(target=lambda: (time.sleep(1.5), os._exit(0)),
                         daemon=True).start()
        try:
            icon.stop()
        except Exception as e:
            print(f"[tray] stop-Fehler: {e}")

    def run(self):
        self.icon.run()
