"""Minimaler OpenRouter-HTTP-Client (requests) mit Retry bei transienten Fehlern.

Warum requests statt openai-SDK: Das SDK (3.8.0) mappt `content` bei Metas
Muse-Modellen (reasoning.encrypted-Feld) fälschlich auf None. Rohes JSON ist zuverlässig.

Latenz: Eine persistente Session (keep-alive) vermeidet den TLS-Handshake pro Call.
"""
import time

import requests

from . import config

_session = requests.Session()  # keep-alive: ein TCP/TLS-Handshake für alle Calls


def chat(messages, model=None, tools=None, tool_choice=None, max_tokens=512,
         retries=3, timeout=90, extra=None):
    body = {
        "model": model or config.ACTION_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if tools:
        body["tools"] = tools
    if tool_choice:
        body["tool_choice"] = tool_choice
    if extra:
        body.update(extra)

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    last = None
    for attempt in range(retries):
        t0 = time.perf_counter()
        try:
            r = _session.post(
                config.OPENROUTER_BASE_URL + "/chat/completions",
                headers=headers, json=body, timeout=timeout,
            )
        except requests.RequestException as e:
            # Netzwerkfehler (z. B. Connection-Reset): kurz warten, erneut versuchen
            last = e
            if attempt < retries - 1:
                dt = time.perf_counter() - t0
                print(f"[openrouter] {body['model']} Netzwerkfehler nach {dt:.1f}s "
                      f"({type(e).__name__}) → Retry {attempt + 2}/{retries}")
                time.sleep(1.0 * (attempt + 1))
                continue
            raise RuntimeError(f"OpenRouter: Netzwerkfehler: {e}") from e

        dt = time.perf_counter() - t0
        if r.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
            last = r
            # Retry-After-Header respektieren, sonst kurzes Backoff
            try:
                wait = float(r.headers.get("Retry-After", 0)) or 1.0 * (attempt + 1)
            except ValueError:
                wait = 1.0 * (attempt + 1)
            wait = min(wait, 10)
            print(f"[openrouter] {body['model']} HTTP {r.status_code} nach {dt:.1f}s "
                  f"→ Retry {attempt + 2}/{retries} in {wait:.0f}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        print(f"[openrouter] {body['model']} → HTTP {r.status_code} in {dt:.1f}s")
        return r.json()

    if last is not None:
        code = getattr(last, "status_code", None)
        text = getattr(last, "text", str(last))
        raise RuntimeError(f"OpenRouter {code}: {text[:400]}")
    raise RuntimeError("OpenRouter: Anfrage fehlgeschlagen")
