# Computer-Use / OS-World Benchmarks (Stand: 4. Sep 2026)

Quellen: CodeSOTA (OSWorld klassisch), BenchLM.ai (OSWorld 2.0), OpenRouter-Modellliste.
Preise in USD pro 1M Tokens (Prompt / Completion) auf OpenRouter.

## OSWorld 2.0 — 108 Long-Horizon-Computer-Use-Workflows

| # | Modell | Anbieter | Offen? | Score | Auf OpenRouter? | Preis ($/M) |
|---|--------|----------|--------|-------|-----------------|-------------|
| 1 | GPT-6 Astra | OpenAI | Closed | 72.6% | nein | — |
| 2 | Claude Opus 5 | Anthropic | Closed | 70.6% | ja | 5.00 / 25.00 |
| 3 | Muse Spark 1.3 | Meta | Closed | 66.9% | ja | 1.25 / 4.25 |
| 4 | GPT-5.6 Sol | OpenAI | Closed | 62.6% | nein | — |
| 5 | Gemini 3.8 Flash | Google | Closed | 59.0% | ja | 0.75 / 3.75 |
| 6 | GPT-5.6 Terra | OpenAI | Closed | 50.2% | nein | — |
| 7 | Gemini 3.7 Flash | Google | Closed | 47.9% | ja | 0.75 / 3.75 |
| 8 | GPT-5.6 Luna | OpenAI | Closed | 45.6% | nein | — |
| 9 | Claude Fable 5.1 | Anthropic | Closed | 41.7% | — | — |
| 10 | Claude Opus 4.8 | Anthropic | Closed | 20.6% | ja | 5.00 / 25.00 |
| 11 | Qwen3.8 Max | Alibaba | Open weight | 19.4% | — | — |
| 12 | Qwen3.8-Flash-Next | Alibaba | Open weight | 19.4% | — | — |
| 13 | Claude Opus 4.7 (Adaptive) | Anthropic | Closed | 18.2% | — | — |
| 14 | Muse Spark 1.1 | Meta | Closed | 14.2% | ja | 1.25 / 4.25 |
| 15 | Claude Opus 4.7 | Anthropic | Closed | 13.9% | — | — |
| 16 | GPT-5.5 | OpenAI | Closed | 13.0% | — | — |
| 17 | Claude Sonnet 4.6 | Anthropic | Closed | 8.3% | — | — |
| 18 | MiniMax M3 | MiniMax | Open weight | 4.6% | — | — |
| 19 | Kimi K2.6 | Moonshot AI | Open weight | 4.6% | — | — |
| 20 | Qwen3.7 Plus | Alibaba | Closed | 2.8% | — | — |

## OSWorld (klassisch) — die wichtigsten Einträge

| Score | Modell |
|-------|--------|
| 63.5% | Agent S3 w/ bBoN |
| 62.3% | GLM-5V-Turbo |
| 60.8% | CoAct-1 |
| 51.0% | JEDI-7B with o3 planner |
| 47.5% | UI-TARS-2 |
| 45.2% | GTA1 (7B) |
| 42.5% | UI-TARS-1.5 |
| 41.4% | Agent S2 (Gemini 2.5) |
| 38.1% | OpenAI CUA (o1) |
| 34.5% | Agent S2 (Claude 3.7) |
| 28.0% | Claude 3.7 Sonnet |
| 24.6% | UI-TARS-72B |
| 22.0% | Claude Computer Use |
| 20.6% | Agent S w/ GPT-4o |
| 6.5% | GPT-4 Turbo (2024) |

## Aktuelle Modell-Wahl im Desktop-Assistant

| Rolle | Modell | OSWorld 2.0 | Preis ($/M) | Tool-Calling | Modalitäten |
|-------|--------|-------------|-------------|--------------|-------------|
| Action (aktuell) | deepseek/deepseek-v4-flash-vision-exp | nicht gelistet | 0.22 / 0.66 | ja | text+image |
| ASR (aktuell) | meta/muse-spark-1.3 | 66.9% (#3) | 1.25 / 4.25 | ja | audio+text+image+video+file |
| Kandidat | anthropic/claude-opus-5 | 70.6% (#2) | 5.00 / 25.00 | ja | text+image |
| Kandidat | google/gemini-3.8-flash | 59.0% (#5) | 0.75 / 3.75 | ja | audio+text+image |

## Kernaussage

1. DeepSeek V4 Flash Vision Exp (aktuelles Action-Modell) ist auf OSWorld 2.0
   GAR NICHT gelistet → erklärbar schwaches Computer-Use-Verhalten (das Flattern
   im Dry-Run: alt+tab, wmctrl, fehlendes Enter nach URL).
2. Muse Spark 1.3 ist bereits unser ASR-Modell, ist omni-modal (Audio+Vision+Text),
   unterstützt Tool-Calling und liegt auf Platz 3 (66.9%). → Ein Modell für alles.
3. Claude Opus 5 ist das beste auf OpenRouter verfügbare (70.6%), aber 4x teurer
   als Muse und nur +3.7 Punkte.
4. Gemini 3.8 Flash ist günstiger als Muse (0.75/3.75), aber -7.9 Punkte.

Empfehlung: Action-Engine von DeepSeek Vision auf Muse Spark 1.3 umstellen
(ein Modell, omni-modal, top-3 Computer Use). Claude Opus 5 als teure
Qualitätsspitze im Hinterkopf behalten.
