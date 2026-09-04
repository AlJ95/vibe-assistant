"""Action-Engine: DeepSeek V4 Vision + Tool-Calling, mehrstufige Agent-Schleife."""
import base64
import json

from . import config, executor, openrouter, screenshot

TOOLS = [
    {"type": "function", "function": {
        "name": "type_text",
        "description": "Tippt Text in das aktuell fokussierte Fenster (für Diktat oder Eingaben).",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}},
                       "required": ["text"]},
    }},
    {"type": "function", "function": {
        "name": "press_keys",
        "description": "Drückt eine Tastenkombination, z. B. ['ctrl','s'].",
        "parameters": {"type": "object", "properties": {"keys": {"type": "array", "items": {"type": "string"}}},
                       "required": ["keys"]},
    }},
    {"type": "function", "function": {
        "name": "click",
        "description": "Klickt an Bildschirmkoordinaten (aus dem Screenshot ableitbar).",
        "parameters": {"type": "object", "properties": {
            "x": {"type": "integer"}, "y": {"type": "integer"},
            "button": {"type": "string", "enum": ["left", "middle", "right"]}},
            "required": ["x", "y"]},
    }},
    {"type": "function", "function": {
        "name": "open_app",
        "description": "Öffnet eine Anwendung (z. B. 'firefox', 'slack').",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}},
                       "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "focus_window",
        "description": "Fokussiert ein Fenster per Namensfragment.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}},
                       "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "run_command",
        "description": "Führt ein Shell-Kommando aus (Whitelist-gesteuert).",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}},
                       "required": ["command"]},
    }},
    {"type": "function", "function": {
        "name": "task_finished",
        "description": "Melde, dass die Aufgabe vollständig erledigt ist. Beendet die Agent-Schleife.",
        "parameters": {"type": "object", "properties": {"summary": {"type": "string"}},
                       "required": ["summary"]},
    }},
]

SYSTEM_PROMPT = (
    "Du bist ein Desktop-Agent auf einem Linux-Rechner. Du bekommst eine Aufgabe "
    "(transkribierte Sprachäußerung) und einen Screenshot des aktuellen Desktops.\n"
    "Arbeite die Aufgabe in Schritten ab:\n"
    "1. Analysiere den aktuellen Screenshot.\n"
    "2. Rufe genau EIN Tool auf, das den nächsten sinnvollen Schritt ausführt.\n"
    "3. Du bekommst danach einen neuen Screenshot und machst den nächsten Schritt.\n"
    "4. Wiederhole, bis die Aufgabe vollständig erledigt ist.\n"
    "5. Wenn die Aufgabe erledigt ist, rufe task_finished mit einer kurzen Zusammenfassung auf.\n"
    "Regeln:\n"
    "- Reines Diktat / Text → type_text.\n"
    "- Anwendung öffnen → open_app.\n"
    "- Tastenkombination → press_keys.\n"
    "- Klick auf ein sichtbares UI-Element → click mit Koordinaten aus dem Screenshot.\n"
    "- Fenster fokussieren → focus_window.\n"
    "- Mehrschrittige Aufgaben (z. B. \"öffne Firefox und geh zu Gmail\") in mehreren "
    "Schritten abarbeiten und erst am Ende task_finished aufrufen.\n"
    "Antworte auf Deutsch."
)


def _img(png: bytes) -> dict:
    return {"type": "image_url",
            "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}}


def run_task(transcribed_text: str, screenshot_png: bytes, max_steps: int = 10) -> str:
    """Mehrstufige Computer-Use-Schleife. Gibt die Abschluss-Zusammenfassung zurück."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": f"Aufgabe: \"{transcribed_text}\""},
            _img(screenshot_png),
        ]},
    ]

    summary = ""
    for step in range(max_steps):
        data = openrouter.chat(
            model=config.ACTION_MODEL, messages=messages,
            tools=TOOLS, tool_choice="auto", max_tokens=1024,
            extra={"reasoning_effort": "low"},
        )
        msg = data["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            if msg.get("content"):
                summary = msg["content"].strip()
            break

        messages.append({
            "role": "assistant",
            "content": msg.get("content"),
            "tool_calls": [
                {"id": tc["id"], "type": "function",
                 "function": {"name": tc["function"]["name"],
                              "arguments": tc["function"].get("arguments", "{}")}}
                for tc in tool_calls
            ],
        })

        done = False
        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            if name == "task_finished":
                summary = args.get("summary", "")
                done = True
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": "ok"})
                break
            try:
                executor.execute(name, args)
                result = "ok"
            except Exception as e:
                result = f"Fehler: {e}"
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

        if done:
            break

        try:
            img = screenshot.capture_png()
        except Exception:
            img = screenshot_png
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": "Aktueller Bildschirm (nach deiner letzten Aktion):"},
                _img(img),
            ],
        })

    return summary
