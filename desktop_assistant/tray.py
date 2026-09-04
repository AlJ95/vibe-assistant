"""Tray-Icon (pystray + AppIndicator): Aktiviert/Deaktiviert/Beenden."""
import pystray
from PIL import Image, ImageDraw


class Tray:
    def __init__(self, audio, on_quit):
        self.audio = audio
        self.on_quit = on_quit
        self.active = True  # default: aktiviert
        self.icon = pystray.Icon(
            "desktop-assistant",
            icon=self._make_icon(self.active),
            title="Desktop Assistant",
            menu=self._build_menu(),
        )

    def _make_icon(self, active):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        color = (52, 211, 153, 255) if active else (100, 116, 139, 255)
        d.ellipse([6, 6, 58, 58], fill=color)
        d.ellipse([22, 22, 42, 42], fill=(2, 6, 23, 255))
        return img

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(
                "Aktiviert",
                self._toggle_active,
                checked=lambda item: self.active,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Beenden", self._quit),
        )

    def _toggle_active(self, icon, item):
        self.active = not self.active
        self.audio.set_active(self.active)
        icon.icon = self._make_icon(self.active)
        icon.update_menu()
        print(f"[tray] {'aktiviert' if self.active else 'deaktiviert'}")

    def _quit(self, icon, item):
        self.on_quit()
        icon.stop()

    def run(self):
        self.icon.run()
