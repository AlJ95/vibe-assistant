"""ASR: Default lokal (whisper.cpp-Server, CUDA), Fallback OpenRouter (Omni-Modell).

Lokales Backend minimiert die Latenz: kein Netzwerk-Roundtrip, keine Cloud-Kosten.
"""
import base64

import requests

from . import config, openrouter

SYSTEM_PROMPT = (
    "Du bist ein Transkriptions-Modul. Transkribiere den folgenden Sprachinput wortgetreu. "
    "Rekonstruiere falsch erkannte Wörter aus dem Satzkontext, korrigiere Grammatik, "
    "entferne Füllwörter (äh, hm, also). Gib NUR den bereinigten Text zurück, ohne "
    "Kommentar, ohne Anführungszeichen. Sprache: Deutsch."
)


def _local_transcribe(wav_bytes: bytes) -> str:
    """Whisper.cpp-Server (/inference): WAV → Text, komplett lokal."""
    files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
    data = {"temperature": "0", "response_format": "json"}
    r = requests.post(
        config.WHISPER_SERVER_URL + "/inference",
        files=files, data=data, timeout=30,
    )
    r.raise_for_status()
    return (r.json().get("text") or "").strip()


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
    if config.ASR_BACKEND == "local":
        try:
            return _local_transcribe(wav_bytes)
        except Exception as e:
            print(f"[asr] lokale Transkription fehlgeschlagen ({e}) — Fallback OpenRouter")
    return _remote_transcribe(wav_bytes)
