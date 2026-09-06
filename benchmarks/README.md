# Benchmarks

Zwei Tools:

1. **`e2e_bench.py`** — der maßgebliche Benchmark. Misst eine komplette
   Agent-Runde End-to-End mit den ECHTEN App-Komponenten (echte Tool-Schemas +
   System-Prompt der Action-Engine, echter Screenshot, echte Sprachdatei,
   lokale Whisper-ASR). → siehe unten „End-to-End-Latenz".
2. **`latency_bench.py`** — Low-Level-Sonde. Misst isolierte Medien-Payloads
   (text/image/audio/image+audio) gegen beliebige OpenAI-kompatible Endpunkte,
   um Komponenten-Overhead zu isolieren (z. B. „was kostet das Bild im Prefill?").
   Für die echte Projektentscheidung ist **e2e_bench** maßgeblich.

---

## End-to-End-Latenz (`e2e_bench.py`)

Misst eine KOMPLETTE Runde, vom Task-Start bis zur ersten Antwort/Tool-Call des
Action-Modells — genau die Pipeline des Projekts:

    Variante A (2 Calls): VAD-Capture → ASR (lokal whisper.cpp) → Action-Modell (Text+Image)
    Variante B (1 Call):   Omni-Modell verarbeitet Audio+Image+Text direkt → Tool-Call

Keine künstlichen Modi. Nur Modelle, die die Modalität können (Vision+Tools für
Action; Audio+Vision+Tools für Omni).

    uv run python benchmarks/e2e_bench.py --config benchmarks/e2e.example.json --runs 3
    uv run python benchmarks/e2e_bench.py --config ... --only astra --json /tmp/e2e.json

Voraussetzung für Variante A: whisper-server läuft (`ASR_BACKEND=local`).

Gemessene Metriken je Runde:
| Metrik    | Bedeutung                                                        |
|-----------|------------------------------------------------------------------|
| asr_time  | Zeit der lokalen Transkription (nur Variante A)                  |
| e2e_ttft  | Task-Start → erste Action-Antwort (Tool-Call/Content) — **die relevante Zahl** |
| e2e_total | Task-Start → Antwort abgeschlossen                               |

Config (`e2e.example.json`): Liste von `pipelines`. Jede hat entweder `action`
(lokale ASR + Action-Modell) oder `omni` (Ein-Call). Provider-Felder wie bei
`latency_bench`: `base_url`, `api_key_env`, `model`, `extra`, `audio_data_uri`.

---

## Low-Level-Sonde (`latency_bench.py`)

Misst TTFT/Total einzelner Medien-Payloads (OpenAI-kompatibel):

## Was gemessen wird

Je Provider und Modus werden mehrere Requests gesendet (streaming) und gemessen:

| Metrik  | Bedeutung                                                        |
|---------|------------------------------------------------------------------|
| TTFT    | Time-to-first-token: Zeit bis die Antwort (content/tool/reasoning) beginnt. Dominiert durch Netz + Bild-Prefill + Reasoning. |
| Total   | Zeit bis der Stream abgeschlossen ist.                            |
| Tokens  | Output-Tokens laut `usage` (falls vom Provider gemeldet).         |

Medien-Modi (pro Provider konfigurierbar):

| Modus       | Payload                                                            |
|-------------|--------------------------------------------------------------------|
| `text`      | Nur Prompt → Basislinie (Netz + TTFT des Modells ohne Medien).     |
| `image`     | Prompt + Screenshot (wie die Action-Engine sie sendet).            |
| `audio`     | Prompt + WAV-Clip (wie die ASR sie senden würde).                  |
| `image+audio` | Prompt + Screenshot + Audio (Omni-Modelle).                      |

## Voraussetzungen

- Projekt-venv (enthält requests, numpy, Pillow).
- `scrot` für den Screenshot (Linux) — sonst PIL `ImageGrab`.
- API-Keys in der Umgebung (werden **nicht** in die Config geschrieben):
  `export OPENROUTER_API_KEY=...` bzw. `OPENAI_API_KEY=...`

## Nutzung

    cd ~/projects/personal/desktop-assistant

    # Standard: alle Provider der Beispiel-Config, je 3 Runs pro Modus
    uv run python benchmarks/latency_bench.py --config benchmarks/providers.example.json

    # Nur ein Provider, mehr Runs
    uv run python benchmarks/latency_bench.py --config ... --only astra --runs 5

    # Echte Sprachdatei als Audio-Payload statt Sinus-Ton
    uv run python benchmarks/latency_bench.py --config ... --audio /tmp/test_speech.wav

    # Ergebnisse als JSON (für CI/Verarbeitung)
    uv run python benchmarks/latency_bench.py --config ... --json /tmp/lat.json

## Config-Format (JSON)

    {
      "prompt": "Antworte mit genau einem Wort: OK",   // Proben-Prompt
      "runs": 3,                                       // Default-Runs je Modus
      "screenshot_max_width": 1280,                    // JPEG-Breite
      "screenshot_quality": 80,
      "audio_seconds": 1.0,                            // Länge des Sinus-Tons
      "providers": [
        {
          "name": "openrouter-astra-pro",              // nur für Reports/--only
          "base_url": "https://openrouter.ai/api/v1",  // OpenAI-kompatibler Endpunkt
          "api_key_env": "OPENROUTER_API_KEY",         // Key kommt aus der ENV
          "model": "openai/gpt-6-astra-pro",
          "modes": ["text", "image"],                  // welche Modi laufen
          "max_tokens": 16,
          "audio_data_uri": false,                     // true: data:audio/wav;base64,…
          "extra": {"reasoning_effort": "minimal"}     // wird in den Body gemerged
        }
      ]
    }

Provider ohne gesetzten `api_key_env` werden mit Hinweis übersprungen.

## Provider-Hinweise

- **OpenRouter** (`https://openrouter.ai/api/v1`): ein Endpunkt, viele Modelle.
  Audio via `input_audio` mit rohem Base64 (`audio_data_uri: false`) — so
  akzeptiert es z. B. `meta/muse-spark-1.3`.
- **OpenAI direkt** (`https://api.openai.com/v1`): Audio-`input_audio` erwartet
  je nach Modell ein `data:audio/wav;base64,…`-Präfix → `audio_data_uri: true`.
  Vision via `image_url` data-URI wie gehabt.
- **DeepSeek direkt** (`https://api.deepseek.com`): OpenAI-kompatibel, Text;
  Vision-Modelle je nach Angebot ergänzen.
- **Lokal (vLLM / llama.cpp)**: `base_url: http://127.0.0.1:8000/v1` ohne Key —
  dann `api_key_env` leer lassen und das Tool überspringt nicht (env = "" ist ok,
  Key-Header bleibt leer).

## Interpretation / Stolperfallen

- **Erster Request = kalt.** Prompt-/Bild-Caching (OpenAI: $1/M cached input,
  Anthropic: Prompt-Caching) greift erst ab dem 2. identischen Prefix. Mehrere
  Runs ansehen (min vs. avg) statt nur den ersten.
- **TTFT ≠ Total.** Reasoning-Modelle (z. B. GPT-6 Astra, Gemini Flash mit
  Thinking) haben hohe TTFT, aber Antwort ist dann oft kurz. Für „wie schnell
  merke ich was" zählt TTFT; für Durchsatz Total.
- **Bildgröße steuert Prefill.** 1280 px JPEG ≈ wenige hundert Tokens;
  größere Bilder erhöhen TTFT proportional.
- **Audio-Payload:** Der Sinus-Ton ist nur ein Transport-Benchmark (nicht für
  ASR-Genauigkeit). Mit `--audio datei.wav` echte Sprache verwenden.
- Die App selbst nutzt für ASR inzwischen lokal whisper.cpp → der `audio`-Modus
  hier adressiert Cloud-Omni-ASR (z. B. Muse Spark als Fallback).
