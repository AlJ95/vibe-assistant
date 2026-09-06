#!/usr/bin/env python3
"""Latency-Benchmark für den Vibe-Assistant-Pipeline (Screenshot + Audio).

Misst die End-to-End-Latenz von OpenAI-kompatiblen Chat-Completion-APIs mit
unterschiedlichen Medien-Payloads — genau das, was die Action-Engine/ASR im
Echtbetrieb sendet:

    Modi (pro Provider konfigurierbar):
      text          → nur Prompt (Basislinie)
      image         → Prompt + Desktop-Screenshot (JPEG, wie die Action-Engine)
      audio         → Prompt + Audio-Clip (WAV 16 kHz, wie die ASR)
      image+audio   → Prompt + Screenshot + Audio (Omni-Modelle)

    Gemessen pro Request:
      TTFT      Time to first (content) token  — Latenz bis die Antwort beginnt
      Total     Zeit bis Request abgeschlossen
      Tokens    Output-Tokens (usage, falls gemeldet)

Provider-agnostisch: Jeder Eintrag definiert base_url + api_key_env + model.
Damit funktioniert das Tool gegen OpenRouter, OpenAI direkt, DeepSeek, xAI,
Groq, Together … sowie jeden OpenAI-kompatiblen Endpunkt (auch lokal, z. B. vLLM).

Nutzung:
    uv run python benchmarks/latency_bench.py --config benchmarks/providers.example.json
    uv run python benchmarks/latency_bench.py --config ... --runs 5 --only openrouter
    uv run python benchmarks/latency_bench.py --config ... --json /tmp/lat.json

Keine Zusatz-Abhängigkeiten über das Projekt-venv hinaus (requests, numpy, Pillow).
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import requests

# --------------------------------------------------------------------------- #
# Assets: Screenshot + Audio                                                  #
# --------------------------------------------------------------------------- #

def capture_screenshot(max_width: int = 1280, quality: int = 80) -> bytes:
    """Echter Desktop-Screenshot als JPEG (wie screenshot.py in der App)."""
    from PIL import Image

    if os.name == "posix" and shutil.which("scrot"):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            subprocess.run(["scrot", "-o", path], check=True, capture_output=True)
            raw = Path(path).read_bytes()
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
    else:
        from PIL import ImageGrab

        buf = io.BytesIO()
        ImageGrab.grab().save(buf, format="PNG")
        raw = buf.getvalue()

    img = Image.open(io.BytesIO(raw)).convert("RGB")
    if img.width > max_width:
        h = int(img.height * max_width / img.width)
        img = img.resize((max_width, h), Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def make_audio(duration: float = 1.0, freq: float = 440.0, sr: int = 16000) -> bytes:
    """Erzeugt einen kurzen Sinus-Ton als WAV (repräsentativer Audio-Payload)."""
    import numpy as np

    t = np.linspace(0.0, duration, int(sr * duration), endpoint=False)
    tone = 0.3 * np.sin(2 * np.pi * freq * t)
    # kurze Pausen + zweiter Ton → kein "reiner" Einzelton, ASR-freundlicher
    tone = np.concatenate([tone[: int(sr * 0.4)],
                           np.zeros(int(sr * 0.2)),
                           tone[int(sr * 0.4):]])
    pcm = (np.clip(tone, -1, 1) * 32767).astype(np.int16)
    buf = io.BytesIO()
    import wave

    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def load_wav(path: str) -> bytes:
    """Lädt eine echte WAV-Datei als Payload (optional, --audio)."""
    return Path(path).read_bytes()


# --------------------------------------------------------------------------- #
# Requests                                                                     #
# --------------------------------------------------------------------------- #

def _media_parts(mode: str, image: bytes | None, audio: bytes | None,
                 audio_data_uri: bool) -> list[dict]:
    parts: list[dict] = []
    if "image" in mode and image:
        parts.append({
            "type": "image_url",
            "image_url": {
                "url": "data:image/jpeg;base64," + base64.b64encode(image).decode(),
            },
        })
    if "audio" in mode and audio:
        b64 = base64.b64encode(audio).decode()
        data = ("data:audio/wav;base64," + b64) if audio_data_uri else b64
        parts.append({"type": "input_audio", "input_audio": {"data": data, "format": "wav"}})
    return parts


def _measure(provider: dict, prompt: str, mode: str, image: bytes | None,
             audio: bytes | None, timeout: int) -> dict:
    """Ein einzelner gemessener Request (streaming). Gibt Metriken oder Fehler."""
    base_url = provider["base_url"].rstrip("/")
    api_key = os.getenv(provider.get("api_key_env", ""), "")
    body: dict = {
        "model": provider["model"],
        "messages": [{
            "role": "user",
            "content": (
                [{"type": "text", "text": prompt}]
                + _media_parts(mode, image, audio, provider.get("audio_data_uri", False))
            ),
        }],
        "max_tokens": provider.get("max_tokens", 16),
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    body.update(provider.get("extra", {}) or {})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    session = requests.Session()
    t0 = time.perf_counter()
    ttft = None          # Zeit bis erstes content/tool_delta
    content_chars = 0
    usage_tokens = None
    error = None
    status = None
    try:
        with session.post(base_url + "/chat/completions", headers=headers,
                          json=body, timeout=timeout, stream=True) as resp:
            status = resp.status_code
            if resp.status_code != 200:
                snippet = resp.text[:300] if resp.text else ""
                error = f"HTTP {resp.status_code}: {snippet}"
            else:
                for raw in resp.iter_lines(decode_unicode=True):
                    line = raw if isinstance(raw, str) else raw.decode(errors="ignore")
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[len("data:"):].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if ttft is None:
                        try:
                            delta = chunk["choices"][0]["delta"] or {}
                        except (KeyError, IndexError):
                            delta = {}
                        if delta.get("content") or delta.get("tool_calls") \
                                or delta.get("reasoning") or delta.get("reasoning_content"):
                            ttft = time.perf_counter() - t0
                    # Content sammeln für Token-Schätzung
                    try:
                        d = chunk["choices"][0].get("delta") or {}
                        content_chars += len(d.get("content") or "")
                    except (KeyError, IndexError):
                        pass
                    usage = chunk.get("usage")
                    if usage:
                        usage_tokens = usage.get("completion_tokens")
    except requests.RequestException as e:
        error = f"Netzwerkfehler: {e}"
    total = time.perf_counter() - t0

    return {
        "ok": error is None,
        "ttft": ttft,
        "total": total,
        "tokens": usage_tokens if usage_tokens is not None
                  else (content_chars / 4 if content_chars else None),
        "status": status,
        "error": error,
    }


# --------------------------------------------------------------------------- #
# Ablauf + Report                                                              #
# --------------------------------------------------------------------------- #

def _fmt(x, unit="s"):
    return "—" if x is None else f"{x:.2f}{unit}"


def _stat(vals):
    return statistics.mean(vals) if vals else None


def run_benchmark(cfg: dict, only: str | None, runs: int, timeout: int,
                  audio_path: str | None) -> list[dict]:
    prompt = cfg.get("prompt", "Antworte mit genau einem Wort: OK")
    runs = runs or int(cfg.get("runs", 3))
    image = capture_screenshot(
        max_width=int(cfg.get("screenshot_max_width", 1280)),
        quality=int(cfg.get("screenshot_quality", 80)),
    )
    audio = load_wav(audio_path) if audio_path else make_audio(
        duration=float(cfg.get("audio_seconds", 1.0)))

    results = []
    for p in cfg.get("providers", []):
        name = p.get("name") or p["model"]
        if only and only not in name:
            continue
        if not os.getenv(p.get("api_key_env", ""), ""):
            print(f"[skip] {name}: env {p.get('api_key_env')} nicht gesetzt")
            continue
        modes = p.get("modes") or ["text"]
        for mode in modes:
            row = {"provider": name, "mode": mode,
                   "base_url": p["base_url"], "model": p["model"]}
            ttfts, totals = [], []
            errs = []
            for i in range(runs):
                r = _measure(p, prompt, mode, image, audio, timeout)
                if r["ok"]:
                    ttfts.append(r["ttft"])
                    totals.append(r["total"])
                    row.setdefault("tokens", r["tokens"])
                else:
                    errs.append(r["error"])
            row["runs"] = runs
            row["ok"] = len(ttfts)
            row["ttft_avg"] = _stat(ttfts)
            row["ttft_min"] = min(ttfts) if ttfts else None
            row["ttft_max"] = max(ttfts) if ttfts else None
            row["total_avg"] = _stat(totals)
            row["total_min"] = min(totals) if totals else None
            row["total_max"] = max(totals) if totals else None
            row["errors"] = errs[:3]
            results.append(row)
    return results


def print_report(results: list[dict]):
    print(f"Latency-Benchmark — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Modus pro Provider laut Config; Runs je Modus; Einheiten: Sekunden\n")
    last = None
    for r in results:
        if r["provider"] != last:
            print(f"\n{r['provider']}  ({r['model']})")
            print("  Modus        Runs  OK   TTFT avg   TTFT min/max   Total avg   Total min/max")
            last = r["provider"]
        err = f"  FEHLER: {r['errors'][0][:80]}" if r["errors"] else ""
        print(f"  {r['mode']:<12} {r['runs']:<5} {r['ok']:<4} "
              f"{_fmt(r['ttft_avg']):<10} {_fmt(r['ttft_min'])}/{_fmt(r['ttft_max']):<10} "
              f"{_fmt(r['total_avg']):<11} {_fmt(r['total_min'])}/{_fmt(r['total_max'])}{err}")


def _load_dotenv():
    """Lädt optional eine .env (Projekt- oder CWD), falls python-dotenv vorhanden."""
    try:
        from dotenv import load_dotenv

        project_env = Path(__file__).resolve().parent.parent / ".env"
        if project_env.exists():
            load_dotenv(project_env)
        load_dotenv()  # CWD/.env
    except ImportError:
        pass  # ohne dotenv: Keys müssen in der Umgebung stehen


def main():
    _load_dotenv()
    ap = argparse.ArgumentParser(description="Latency-Benchmark (Screenshot+Audio) für OpenAI-kompatible APIs")
    ap.add_argument("--config", default="benchmarks/providers.example.json",
                    help="JSON-Config mit Providern (siehe benchmarks/README.md)")
    ap.add_argument("--runs", type=int, default=0, help="Requests je Modus (überschreibt Config)")
    ap.add_argument("--only", default=None, help="Nur Provider, dessen Name diesen String enthält")
    ap.add_argument("--timeout", type=int, default=120, help="HTTP-Timeout je Request (s)")
    ap.add_argument("--audio", default=None, help="Echte WAV-Datei als Audio-Payload statt Sinus-Ton")
    ap.add_argument("--json", dest="json_out", default=None, help="Ergebnisse als JSON exportieren")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        sys.exit(f"Config nicht gefunden: {cfg_path}")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    results = run_benchmark(cfg, args.only, args.runs, args.timeout, args.audio)
    print_report(results)
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nJSON: {args.json_out}")


if __name__ == "__main__":
    main()
