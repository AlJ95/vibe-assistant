"""ASR über OpenRouter (Omni-Modell, Audio-in → Text)."""
import base64

from . import config, openrouter

SYSTEM_PROMPT = (
    "Du bist ein Transkriptions-Modul. Transkribiere den folgenden Sprachinput wortgetreu. "
    "Rekonstruiere falsch erkannte Wörter aus dem Satzkontext, korrigiere Grammatik, "
    "entferne Füllwörter (äh, hm, also). Gib NUR den bereinigten Text zurück, ohne "
    "Kommentar, ohne Anführungszeichen. Sprache: Deutsch."
)


def transcribe(wav_bytes: bytes) -> str:
    """WAV → Text (Omni-Modell, mit Rekonstruktions-Prompt)."""
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
