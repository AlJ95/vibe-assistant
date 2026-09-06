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
        try:
            r = _session.post(
                config.OPENROUTER_BASE_URL + "/chat/completions",
                headers=headers, json=body, timeout=timeout,
            )
        except requests.RequestException as e:
            # Netzwerkfehler (z. B. Connection-Reset): kurz warten, erneut versuchen
            last = e
            if attempt < retries - 1:
                time.sleep(1.0 * (attempt + 1))
                continue
            raise RuntimeError(f"OpenRouter: Netzwerkfehler: {e}") from e

        if r.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
            last = r
            # Retry-After-Header respektieren, sonst kurzes Backoff
            try:
                wait = float(r.headers.get("Retry-After", 0)) or 1.0 * (attempt + 1)
            except ValueError:
                wait = 1.0 * (attempt + 1)
            time.sleep(min(wait, 10))
            continue
        r.raise_for_status()
        return r.json()

    if last is not None:
        code = getattr(last, "status_code", None)
        text = getattr(last, "text", str(last))
        raise RuntimeError(f"OpenRouter {code}: {text[:400]}")
    raise RuntimeError("OpenRouter: Anfrage fehlgeschlagen")
