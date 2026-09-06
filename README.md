# Vibe Assistant

Voice → Desktop-Action Agent für Ubuntu (X11). Python-Paket: `desktop_assistant`. Dauerläufer mit Tray-Icon: nimmt 24/7 auf,
erkennt per Silero-VAD Sprache, transkribiert LOKAL über whisper.cpp (CUDA) und führt
Desktop-Aktionen via Vision-Modell (Default: Gemma 4 31B, per Tray-Menü wählbar) + xdotool aus.

## Datenfluss

    Mikrofon → Capture (sounddevice) → VAD (Silero v5) → ASR (lokal: whisper.cpp CUDA)
        → Screenshot (JPEG, parallel zur ASR) + Action-Engine (Vision-Modell) → Executor (xdotool) → Desktop

- VAD läuft lokal (Silero ONNX, CPU < 1 %).
- Bei erkannter Sprache: WAV-Segment → ASR (lokal whisper.cpp; Fallback OpenRouter) → Text.
- Bei JEDEM VLM-Call wird ein frischer Desktop-Screenshot (JPEG) mitgegeben (multimodal: Bild + Text).
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

Whisper.cpp-Server für lokale ASR (einmalig bauen + Modell laden, siehe
speech-to-paste-README; danach pro Sitzung starten):

    ~/tools/whisper.cpp/build/bin/whisper-server \
      -m ~/tools/whisper.cpp/models/ggml-large-v3-turbo-q8_0.bin \
      --host 127.0.0.1 --port 8080

## Start

    # 1) Whisper-Server (falls nicht schon aktiv)
    ~/tools/whisper.cpp/build/bin/whisper-server \
      -m ~/tools/whisper.cpp/models/ggml-large-v3-turbo-q8_0.bin \
      --host 127.0.0.1 --port 8080 &

    # 2) Assistant
    python -m desktop_assistant

ASR-Fallback auf OpenRouter: `ASR_BACKEND=openrouter` in der .env setzen.

Tray-Menü: **Aktiviert** (Checkbox, Default an) / **Modell** (Action-Modell wählen) / **Beenden**.
Icon-Farbe = Zustand (grün = aktiv, grau = deaktiviert), Tooltip zeigt das aktive Modell.

## Feedback (Töne + Toast)

Genau zwei akustische Signale, sonst keine:

- **Task-Start** (VAD hat Sprache erkannt, Aufgabe beginnt) → kurzer Ton (660 Hz)
- **Task-Ende** (Aufgabe fertig) → höherer Ton (990 Hz) + Desktop-Toast „Task successful"

## Konfiguration (.env)

| Variable | Default | Zweck |
|---|---|---|
| `OPENROUTER_API_KEY` | — | API-Key (nur für Action-Engine/Fallback) |
| `ASR_BACKEND` | `local` | `local` = whisper.cpp-Server, `openrouter` = Cloud-Fallback |
| `WHISPER_SERVER_URL` | `http://127.0.0.1:8080` | Adresse des lokalen whisper.cpp-Servers |
| `ASR_LANGUAGE` | `de` | Erzwungene Whisper-Sprache (deterministisch, kein Auto-Detect) |
| `ASR_MODEL` | `meta/muse-spark-1.3` | nur openrouter-Backend (Audio-fähig) |
| `ACTION_MODEL` | `google/gemma-4-31b-it` | Action-Modell (per Tray-Menü „Modell" wählbar) |
| `AUDIO_DEVICE` | leer (System-Default) | Aufnahmequelle (Index oder Name) |
| `VAD_THRESHOLD` | `0.5` | Sprach-Schwelle |
| `VAD_MIN_SILENCE_MS` | `350` | Ende-der-Äußerung-Hangover |
| `VAD_MAX_SPEECH_S` | `30` | Max. Äußerungslänge |
| `SCREENSHOT_MAX_WIDTH` | `1280` | JPEG-Breite (klein = schneller Prefill) |
| `SCREENSHOT_QUALITY` | `80` | JPEG-Qualität |
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

## Benchmarks / Latenz

`benchmarks/` enthält ein Provider-agnostisches Latenz-Tool (Screenshot + Audio,
OpenAI-kompatible Endpunkte): `benchmarks/latency_bench.py` + `README.md`.

    uv run python benchmarks/latency_bench.py --config benchmarks/providers.example.json

## Struktur

    desktop_assistant/
      __main__.py        Einstieg (Audio-Thread + Worker + Tray)
      config.py          .env + alle Einstellungen
      audio.py           sounddevice + Silero-VAD (stateful v5)
      asr.py             lokal whisper.cpp-Server (Fallback: OpenRouter Omni)
      screenshot.py      scrot / PIL → JPEG + Klick-Skalierung
      action_engine.py   Vision-Modell + Tool-Calling (Mehrfach-Calls)
      executor.py        xdotool (Klick-Koordinaten werden skaliert)
      openrouter.py      requests-Session (keep-alive) + Retry
      feedback.py        Töne (Task-Start/Ende) + Toast (notify-send)
      tray.py            pystray
    benchmarks/
      latency_bench.py   Latenz-Messung (text/image/audio/image+audio)
      providers.example.json
      README.md
