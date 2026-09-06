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
# ASR läuft lokal (whisper.cpp, CUDA) = Default → minimale Latenz, kein Netz.
# Fallback "openrouter" nutzt ein Audio-fähiges Omni-Modell (ASR_MODEL).
ASR_BACKEND = os.getenv("ASR_BACKEND", "local")           # "local" | "openrouter"
WHISPER_SERVER_URL = os.getenv("WHISPER_SERVER_URL", "http://127.0.0.1:8080")
ASR_LANGUAGE = os.getenv("ASR_LANGUAGE", "de")            # deterministische Whisper-Sprache
ASR_MODEL = os.getenv("ASR_MODEL", "meta/muse-spark-1.3")  # nur openrouter-Backend
ACTION_MODEL = os.getenv("ACTION_MODEL", "google/gemma-4-31b-it")

# Auswahl der Action-Modelle im Tray-Menü (Slug, Anzeigename).
ACTION_MODELS = [
    ("google/gemma-4-31b-it", "Gemma 4 31B"),
    ("anthropic/claude-opus-5", "Claude Opus 5"),
    ("google/gemini-3.8-flash", "Gemini 3.8 Flash"),
    ("openai/gpt-6-astra-pro", "GPT-6 Astra Pro"),
    ("deepseek/deepseek-v4-flash-vision-exp", "DeepSeek V4 Flash Vision"),
]

# --- Audio (portabel: Device wird auto-detektiert, per AUDIO_DEVICE übersteuerbar) ---
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))
CHANNELS = 1
AUDIO_DEVICE = os.getenv("AUDIO_DEVICE", "") or None

# --- VAD (Silero v5) ---
VAD_THRESHOLD = float(os.getenv("VAD_THRESHOLD", "0.5"))
VAD_MIN_SILENCE_MS = int(os.getenv("VAD_MIN_SILENCE_MS", "350"))  # Hangover (Latenz!)
VAD_SPEECH_PAD_MS = int(os.getenv("VAD_SPEECH_PAD_MS", "30"))     # Pre-/Post-Roll
VAD_MAX_SPEECH_S = int(os.getenv("VAD_MAX_SPEECH_S", "30"))       # Max. Äußerungslänge
VAD_WINDOW_SAMPLES = 512                                          # 32 ms @ 16 kHz

# --- Pfade ---
MODEL_DIR = BASE_DIR / "models"
VAD_MODEL_PATH = MODEL_DIR / "silero_vad.onnx"

# --- Screenshot (JPEG für kleine Payloads = weniger Latenz) ---
SCREENSHOT_MAX_WIDTH = int(os.getenv("SCREENSHOT_MAX_WIDTH", "1280"))
SCREENSHOT_QUALITY = int(os.getenv("SCREENSHOT_QUALITY", "80"))

# --- Shell-Whitelist für run_command (kommagetrennte Präfixe; leer = alles blockiert) ---
ALLOWED_COMMAND_PREFIXES = [p for p in os.getenv("ALLOWED_COMMANDS", "").split(",") if p]
