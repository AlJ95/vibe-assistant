"""Desktop-Screenshot (Linux → scrot, sonst PIL). JPEG-kodiert für kleine Payloads.

Liefert zusätzlich die Skalierungsfaktoren Bild → Bildschirm, damit Klick-Koordinaten
des Vision-Modells (im herunterskalierten Bild) korrekt auf den echten Desktop
abgebildet werden können.
"""
import io
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from . import config

IMAGE_MIME = "image/jpeg"


def capture():
    """Voller Screenshot → JPEG-Bytes + (scale_x, scale_y).

    Rückgabe: (data, sx, sy) mit sx = orig_breite / bild_breite.
    """
    if os.name == "posix" and shutil.which("scrot"):
        raw = _capture_scrot()
    else:
        raw = _capture_pil()

    img = Image.open(io.BytesIO(raw)).convert("RGB")
    orig_w, orig_h = img.size

    max_w = config.SCREENSHOT_MAX_WIDTH
    if max_w > 0 and img.width > max_w:
        h = int(img.height * max_w / img.width)
        img = img.resize((max_w, h), Image.Resampling.BILINEAR)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=config.SCREENSHOT_QUALITY)
    data = buf.getvalue()

    sx = (orig_w / img.width) if img.width else 1.0
    sy = (orig_h / img.height) if img.height else 1.0
    return data, sx, sy


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
