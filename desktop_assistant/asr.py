"""ASR: Default lokal (whisper.cpp-Server, CUDA), Fallback OpenRouter (Omni-Modell).

Lokales Backend minimiert die Latenz: kein Netzwerk-Roundtrip, keine Cloud-Kosten.
"""
import base64
import time

import requests

from . import config, openrouter

SYSTEM_PROMPT = (
    "Du bist ein Transkriptions-Modul. Transkribiere den folgenden Sprachinput wortgetreu. "
    "Rekonstruiere falsch erkannte Wörter aus dem Satzkontext, korrigiere Grammatik, "
    "entferne Füllwörter (äh, hm, also). Gib NUR den bereinigten Text zurück, ohne "
    "Kommentar, ohne Anführungszeichen. Sprache: Deutsch."
)


def _dedupe_lines(text: str) -> str:
    """Entfernt aufeinanderfolgende identische Zeilen (whisper-Halluzination)."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line and (not out or line != out[-1]):
            out.append(line)
    return "\n".join(out)


def _local_transcribe(wav_bytes: bytes) -> str:
    """Whisper.cpp-Server (/inference): WAV → Text, komplett lokal."""
    files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
    data = {"temperature": "0", "response_format": "json", "language": config.ASR_LANGUAGE}
    r = requests.post(
        config.WHISPER_SERVER_URL + "/inference",
        files=files, data=data, timeout=30,
    )
    r.raise_for_status()
    return _dedupe_lines(r.json().get("text") or "")


def _remote_transcribe(wav_bytes: bytes) -> str:
    """OpenRouter-Omni-Modell (Audio-in → Text) — Fallback ohne lokalen Server."""
    b64 = base64.b64encode(wav_bytes).decode()
    data = openrouter.chat(
        model=config.ASR_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "input_audio", "input_audio": {"data": b64, "format": "wav"}},
                ],
            },
        ],
        max_tokens=2000,
        extra={"reasoning_effort": "minimal"},
    )
    return (data["choices"][0]["message"].get("content") or "").strip()


def transcribe(wav_bytes: bytes) -> str:
    """WAV → Text, je nach ASR_BACKEND ('local' = Default, 'openrouter')."""
    t0 = time.perf_counter()
    if config.ASR_BACKEND == "local":
        try:
            text = _local_transcribe(wav_bytes)
            print(f"[asr] lokal (whisper) in {time.perf_counter() - t0:.1f}s → "
                  f"{len(text)} Zeichen")
            return text
        except Exception as e:
            print(f"[asr] lokal FEHLER ({type(e).__name__}: {e}) nach "
                  f"{time.perf_counter() - t0:.1f}s → Fallback OpenRouter")
    text = _remote_transcribe(wav_bytes)
    print(f"[asr] openrouter ({config.ASR_MODEL}) in {time.perf_counter() - t0:.1f}s → "
          f"{len(text)} Zeichen")
    return text
