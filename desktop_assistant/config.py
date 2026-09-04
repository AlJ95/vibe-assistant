"""Zentrale Konfiguration (lädt .env, bündelt alle Einstellungen)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# --- OpenRouter ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# --- Modelle ---
# Hinweis: "muse-spark-1.3-contributor" ist durch die OpenRouter-Privacy-Einstellung
# ("paid model training") blockiert → Standard ist die Nicht-Contributor-Variante.
ASR_MODEL = os.getenv("ASR_MODEL", "meta/muse-spark-1.3")
ACTION_MODEL = os.getenv("ACTION_MODEL", "deepseek/deepseek-v4-flash-vision-exp")

# --- Audio (portabel: Device wird auto-detektiert, per AUDIO_DEVICE übersteuerbar) ---
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))
CHANNELS = 1
AUDIO_DEVICE = os.getenv("AUDIO_DEVICE", "") or None

# --- VAD (Silero v5) ---
VAD_THRESHOLD = float(os.getenv("VAD_THRESHOLD", "0.5"))
VAD_MIN_SILENCE_MS = int(os.getenv("VAD_MIN_SILENCE_MS", "600"))   # Hangover
VAD_SPEECH_PAD_MS = int(os.getenv("VAD_SPEECH_PAD_MS", "30"))      # Pre-/Post-Roll
VAD_MAX_SPEECH_S = int(os.getenv("VAD_MAX_SPEECH_S", "30"))        # Max. Äußerungslänge
VAD_WINDOW_SAMPLES = 512                                           # 32 ms @ 16 kHz

# --- Pfade ---
MODEL_DIR = BASE_DIR / "models"
VAD_MODEL_PATH = MODEL_DIR / "silero_vad.onnx"

# --- Screenshot ---
SCREENSHOT_MAX_WIDTH = int(os.getenv("SCREENSHOT_MAX_WIDTH", "1920"))

# --- Shell-Whitelist für run_command (kommagetrennte Präfixe; leer = alles blockiert) ---
ALLOWED_COMMAND_PREFIXES = [p for p in os.getenv("ALLOWED_COMMANDS", "").split(",") if p]
