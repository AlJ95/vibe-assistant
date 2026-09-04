"""Desktop-Screenshot (portabel: Linux → scrot, sonst → PIL ImageGrab)."""
import io
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import config


def capture_png() -> bytes:
    """Nimmt einen Screenshot auf und gibt PNG-Bytes zurück (max. Breite begrenzt)."""
    if os.name == "posix" and shutil.which("scrot"):
        data = _capture_scrot()
    else:
        data = _capture_pil()
    return _downscale(data)


def _capture_scrot() -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
    try:
        subprocess.run(["scrot", "-o", path], check=True, capture_output=True)
        return Path(path).read_bytes()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _capture_pil() -> bytes:
    from PIL import ImageGrab

    img = ImageGrab.grab()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _downscale(data: bytes) -> bytes:
    """Skaliert sehr breite Screenshots herunter, um Payload/Latenz zu begrenzen."""
    max_w = config.SCREENSHOT_MAX_WIDTH
    if max_w <= 0:
        return data
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        if img.width > max_w:
            h = int(img.height * max_w / img.width)
            img = img.resize((max_w, h), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
    except Exception:
        pass
    return data
