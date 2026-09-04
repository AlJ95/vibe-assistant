# Vibe Assistant

Voice → Desktop-Action Agent für Ubuntu (X11). Python-Paket: `desktop_assistant`. Dauerläufer mit Tray-Icon: nimmt 24/7 auf,
erkennt per Silero-VAD Sprache, transkribiert über OpenRouter (Omni-Modell) und führt
Desktop-Aktionen via DeepSeek V4 Vision (Tool-Calling) + xdotool aus.

## Datenfluss

    Mikrofon → Capture (sounddevice) → VAD (Silero v5) → ASR (OpenRouter Omni)
        → Screenshot + Action-Engine (DeepSeek V4 Vision) → Executor (xdotool) → Desktop

- VAD läuft lokal (Silero ONNX, CPU < 1 %).
- Bei erkannter Sprache: WAV-Segment → ASR (`input_audio`, Rekonstruktions-Prompt) → Text.
- Bei JEDEM VLM-Call wird ein frischer Desktop-Screenshot mitgegeben (multimodal: Bild + Text).
- Action-Engine antwortet als Tool-Call → Executor führt via xdotool aus.

## Voraussetzungen (System-Pakete)

    sudo apt-get install -y python3-gi gir1.2-ayatanaappindicator3-0.1 libportaudio2 xdotool scrot

## Setup

    uv venv --system-site-packages --python 3.12
    source .venv/bin/activate
    uv pip install -r requirements.txt
    cp .env.dist .env        # OPENROUTER_API_KEY eintragen

Silero-VAD-Modell (einmalig):

    mkdir -p models
    curl -sL -o models/silero_vad.onnx \
      https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx

## Start

    python -m desktop_assistant

Tray-Menü: **Aktiviert** (Checkbox, Default an) / **Beenden**. Icon-Farbe = Zustand
(grün = aktiv, grau = deaktiviert).

## Feedback (Töne + Toast)

Genau zwei akustische Signale, sonst keine:

- **Task-Start** (VAD hat Sprache erkannt, Aufgabe beginnt) → kurzer Ton (660 Hz)
- **Task-Ende** (Aufgabe fertig) → höherer Ton (990 Hz) + Desktop-Toast „Task successful"

## Konfiguration (.env)

| Variable | Default | Zweck |
|---|---|---|
| `OPENROUTER_API_KEY` | — | API-Key |
| `ASR_MODEL` | `meta/muse-spark-1.3` | Omni-Modell für Transkription |
| `ACTION_MODEL` | `deepseek/deepseek-v4-flash-vision-exp` | Vision-Modell für Tool-Calling |
| `AUDIO_DEVICE` | leer (System-Default) | Aufnahmequelle (Index oder Name) |
| `VAD_THRESHOLD` | `0.5` | Sprach-Schwelle |
| `VAD_MIN_SILENCE_MS` | `600` | Ende-der-Äußerung-Hangover |
| `VAD_MAX_SPEECH_S` | `30` | Max. Äußerungslänge |
| `SCREENSHOT_MAX_WIDTH` | `1920` | Downscale-Grenze für Screenshot |
| `ALLOWED_COMMANDS` | leer | Whitelist-Präfixe für `run_command` (leer = blockiert) |

## Wichtige Hinweise

- **ASR-Modell:** `meta/muse-spark-1.3` (Nicht-Contributor). Die `-contributor`-Variante ist
  durch die OpenRouter-Privacy-Einstellung („paid model training") blockiert — aktivierbar unter
  openrouter.ai/settings/privacy, dann `ASR_MODEL` entsprechend setzen.
- **Client:** OpenRouter wird direkt per `requests` angesprochen (nicht openai-SDK). Das SDK
  (3.8.0) mappt `content` bei Metas Muse-Modellen (reasoning.encrypted) fälschlich auf `None`.
- **Sicherheit:** `run_command` ist standardmäßig blockiert (leere Whitelist). `open_app`/`click`
  etc. wirken direkt auf deinen Desktop.
- **Portabilität:** Aufnahmegerät wird automatisch erkannt (System-Default-Mic); `AUDIO_DEVICE`
  erlaubt Override. Screenshot: Linux `scrot`, sonst PIL `ImageGrab`.

## Struktur

    desktop_assistant/
      __main__.py        Einstieg (Audio-Thread + Worker + Tray)
      config.py          .env + alle Einstellungen
      audio.py           sounddevice + Silero-VAD (stateful v5)
      asr.py             OpenRouter Omni → Text
      screenshot.py      scrot / PIL
      action_engine.py   DeepSeek V4 Vision + Tool-Calling
      executor.py        xdotool
      openrouter.py      requests-basierter Client (Retry)
      feedback.py        Töne (Task-Start/Ende) + Toast (notify-send)
      tray.py            pystray
