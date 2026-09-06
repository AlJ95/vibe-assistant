#!/usr/bin/env python3
"""End-to-End-Latenz-Benchmark — realistisch für den Vibe Assistant.

Misst eine KOMPLETTE Agent-Runde, vom Task-Start bis zur ersten Antwort/Tool-Call
des Action-Modells — mit den echten Komponenten der App:

    Variante A (2 Calls, Standard):  VAD-Capture → ASR (lokal whisper.cpp) → Action-Modell (Text+Image)
    Variante B (1 Call, Omni):       Modell verarbeitet Audio+Image+Text direkt → Tool-Call

Es gibt KEINE künstlichen Modi. Nur Modelle, die die nötige Modalität können:
  - Action-Modell: Vision (Text+Image) + Tool-Calling
  - Omni-Modell:   Audio + Vision + Tool-Calling in einem Call

Genutzt werden die ECHTEN Tool-Schemas + der ECHTE System-Prompt aus
desktop_assistant.action_engine, ein echter Desktop-Screenshot und eine echte
Sprachdatei (--audio). Metriken je Runde:

  asr_time    (nur Variante A) Zeit der lokalen Transkription
  ttft        Zeit bis zum ersten Tool-Call/Content-Delta des Action-Modells
  e2e_ttft    Task-Start → erste Action-Antwort   (DAS ist die relevante Zahl)
  e2e_total   Task-Start → Antwort abgeschlossen

Nutzung:
    uv run python benchmarks/e2e_bench.py --config benchmarks/e2e.example.json --runs 3

Voraussetzung für Variante A: whisper-server läuft (siehe Projekt-README).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import statistics
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from desktop_assistant.action_engine import SYSTEM_PROMPT, TOOLS          # noqa: E402
from desktop_assistant import config as app_config                       # noqa: E402
from desktop_assistant import screenshot as app_screenshot               # noqa: E402

OMNI_TEXT = (
    "Du hörst eine deutsche Sprachäußerung und siehst den aktuellen Bildschirm. "
    "Analysiere die Äußerung und führe die Aufgabe auf dem Bildschirm aus "
    "(per Tool-Calls). Antworte auf Deutsch."
)


def _load_dotenv():
    try:
        from dotenv import load_dotenv

        env = ROOT / ".env"
        if env.exists():
            load_dotenv(env)
        load_dotenv()
    except ImportError:
        pass


# --------------------------------------------------------------------------- #
# Bausteine: ASR + Messages + Streaming                                        #
# --------------------------------------------------------------------------- #

def local_asr(audio_bytes: bytes) -> str:
    """Lokale Transkription über whisper.cpp-Server (KEIN Cloud-Fallback)."""
    r = requests.post(
        app_config.WHISPER_SERVER_URL + "/inference",
        files={"file": ("audio.wav", audio_bytes, "audio/wav")},
        data={"temperature": "0", "response_format": "json",
              "language": app_config.ASR_LANGUAGE},
        timeout=60,
    )
    r.raise_for_status()
    return (r.json().get("text") or "").strip()


def _img_part(data: bytes) -> dict:
    return {"type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(data).decode()}}


def _audio_part(data: bytes, data_uri: bool) -> dict:
    b64 = base64.b64encode(data).decode()
    return {"type": "input_audio",
            "input_audio": {"data": ("data:audio/wav;base64," + b64) if data_uri else b64,
                            "format": "wav"}}


def action_messages(task_text: str, image: bytes) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": f"Aufgabe: \"{task_text}\""},
            _img_part(image),
        ]},
    ]


def omni_messages(image: bytes, audio: bytes, data_uri: bool) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": OMNI_TEXT},
            _img_part(image),
            _audio_part(audio, data_uri),
        ]},
    ]


def chat_stream(provider: dict, messages: list[dict], timeout: int) -> dict:
    """Streaming-Chat mit Tools. Misst TTFT bis zum ersten Tool-Call/Content."""
    base_url = provider["base_url"].rstrip("/")
    api_key = os.getenv(provider.get("api_key_env", ""), "")
    body = {
        "model": provider["model"],
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
        "max_tokens": provider.get("max_tokens", 256),
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    body.update(provider.get("extra", {}) or {})
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    session = requests.Session()
    t0 = time.perf_counter()
    ttft = None
    total = None
    tool_name = None
    error = None
    try:
        with session.post(base_url + "/chat/completions", headers=headers,
                          json=body, timeout=timeout, stream=True) as resp:
            if resp.status_code != 200:
                error = f"HTTP {resp.status_code}: {(resp.text or '')[:200]}"
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
                    try:
                        delta = chunk["choices"][0].get("delta") or {}
                    except (KeyError, IndexError):
                        delta = {}
                    if ttft is None:
                        calls = delta.get("tool_calls") or []
                        if calls:
                            ttft = time.perf_counter() - t0
                            tool_name = (calls[0].get("function") or {}).get("name")
                        elif delta.get("content"):
                            ttft = time.perf_counter() - t0
    except requests.RequestException as e:
        error = f"Netzwerkfehler: {e}"
    total = time.perf_counter() - t0
    return {"ok": error is None, "ttft": ttft, "total": total,
            "tool": tool_name, "error": error}


# --------------------------------------------------------------------------- #
# Pipelines                                                                     #
# --------------------------------------------------------------------------- #

def run_round(pipeline: dict, audio: bytes, image: bytes, timeout: int) -> dict:
    """Eine komplette Runde. Gibt Metriken oder Fehler zurück."""
    if "omni" in pipeline:
        p = pipeline["omni"]
        r = chat_stream(p, omni_messages(image, audio, p.get("audio_data_uri", False)), timeout)
        if not r["ok"]:
            return {"ok": False, "error": r["error"]}
        return {"ok": True, "asr": None, "ttft": r["ttft"], "total": r["total"],
                "e2e_ttft": r["ttft"], "e2e_total": r["total"], "tool": r["tool"]}

    # Variante A: lokale ASR → Action-Modell
    t0 = time.perf_counter()
    try:
        text = local_asr(audio)
    except Exception as e:
        return {"ok": False, "error": f"ASR: {e}"}
    asr_time = time.perf_counter() - t0
    if not text:
        return {"ok": False, "error": "ASR leer (kein Text erkannt)"}

    r = chat_stream(pipeline["action"], action_messages(text, image), timeout)
    if not r["ok"]:
        return {"ok": False, "error": r["error"], "asr": asr_time}
    return {"ok": True, "asr": asr_time, "ttft": r["ttft"], "total": r["total"],
            "e2e_ttft": (asr_time + r["ttft"]) if r["ttft"] is not None else None,
            "e2e_total": asr_time + r["total"], "tool": r["tool"],
            "transcript": text}


# --------------------------------------------------------------------------- #
# Report                                                                        #
# --------------------------------------------------------------------------- #

def _m(vals):
    return statistics.mean(vals) if vals else None


def _f(x):
    return "—" if x is None else f"{x:.2f}s"


def run_benchmark(cfg, only, runs, timeout):
    audio = Path(cfg.get("audio") or "/tmp/test_speech.wav").read_bytes()
    image, _, _ = app_screenshot.capture()  # echter Screenshot (JPEG)

    results = []
    for p in cfg.get("pipelines", []):
        name = p.get("name") or (p.get("omni") or p.get("action"))["model"]
        if only and only not in name:
            continue
        prov = p.get("omni") or p.get("action")
        if not os.getenv(prov.get("api_key_env", ""), ""):
            print(f"[skip] {name}: env {prov.get('api_key_env')} nicht gesetzt")
            continue
        e2e, totals, asrs, tools = [], [], [], []
        errs = []
        transcripts = set()
        for _ in range(runs):
            r = run_round(p, audio, image, timeout)
            if r["ok"]:
                e2e.append(r["e2e_ttft"])
                totals.append(r["e2e_total"])
                if r.get("asr") is not None:
                    asrs.append(r["asr"])
                if r.get("tool"):
                    tools.append(r["tool"])
                if r.get("transcript"):
                    transcripts.add(r["transcript"])
            else:
                errs.append(r["error"])
        results.append({
            "name": name, "runs": runs, "ok": len(e2e),
            "asr_avg": _m(asrs), "ttft_avg": _m(e2e),
            "ttft_min": min(e2e) if e2e else None, "ttft_max": max(e2e) if e2e else None,
            "total_avg": _m(totals), "tools": tools, "transcripts": sorted(transcripts),
            "errors": errs[:2],
        })
    return results


def print_report(results):
    print("End-to-End-Latenz (Task-Start → Action-Antwort) — echte App-Komponenten\n")
    print(f"{'Pipeline':<34} {'Runs':<5} {'OK':<4} {'ASR':<8} {'E2E TTFT':<10} "
          f"{'min/max':<16} {'E2E Total'}")
    for r in results:
        err = f"  FEHLER: {r['errors'][0][:70]}" if r["errors"] else ""
        tools = f"  [{','.join(set(r['tools']))}]" if r["tools"] else ""
        print(f"{r['name']:<34} {r['runs']:<5} {r['ok']:<4} {_f(r['asr_avg']):<8} "
              f"{_f(r['ttft_avg']):<10} {_f(r['ttft_min'])}/{_f(r['ttft_max']):<14} "
              f"{_f(r['total_avg'])}{tools}{err}")
        for t in r["transcripts"]:
            print(f"    ↳ ASR: {t!r}")


def main():
    _load_dotenv()
    ap = argparse.ArgumentParser(description="End-to-End-Latenz-Benchmark (realistisch)")
    ap.add_argument("--config", default="benchmarks/e2e.example.json")
    ap.add_argument("--runs", type=int, default=0, help="Runden je Pipeline (überschreibt Config)")
    ap.add_argument("--only", default=None, help="Nur Pipelines, deren Name den String enthält")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        sys.exit(f"Config nicht gefunden: {cfg_path}")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    runs = args.runs or int(cfg.get("runs", 3))

    results = run_benchmark(cfg, args.only, runs, args.timeout)
    print_report(results)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(results, indent=2, ensure_ascii=False),
                                       encoding="utf-8")
        print(f"\nJSON: {args.json_out}")


if __name__ == "__main__":
    main()
