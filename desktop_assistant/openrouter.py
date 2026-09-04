"""Minimaler OpenRouter-HTTP-Client (requests) mit Retry bei transienten Fehlern.

Warum requests statt openai-SDK: Das SDK (3.8.0) mappt `content` bei Metas
Muse-Modellen (reasoning.encrypted-Feld) fälschlich auf None. Rohes JSON ist zuverlässig.
"""
import time

import requests

from . import config


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
        r = requests.post(
            config.OPENROUTER_BASE_URL + "/chat/completions",
            headers=headers, json=body, timeout=timeout,
        )
        if r.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
            last = r
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()

    if last is not None:
        raise RuntimeError(f"OpenRouter {last.status_code}: {last.text[:400]}")
    raise RuntimeError("OpenRouter: Anfrage fehlgeschlagen")
