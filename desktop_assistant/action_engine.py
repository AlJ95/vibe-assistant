"""Action-Engine: Vision-Modell + Tool-Calling, mehrstufige Agent-Schleife.

Latenz-Optimierungen:
- Stabile Prefix-Ordnung (System-Prompt + Tools zuerst, Bild zuletzt) → Prompt-Caching.
- Mehrere tool_calls pro Antwort werden erlaubt/gefördert → weniger API-Runden.
- JPEG-Screenshots (klein) + Klick-Koordinaten-Skalierung Bild → Bildschirm.
"""
import base64
import json
import time

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
        "description": "Klickt an Bildschirmkoordinaten. Koordinaten relativ zum sichtbaren Screenshot angeben.",
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
    "2. Rufe die Tool(s) auf, die den nächsten sinnvollen Schritt ausführen.\n"
    "3. Du bekommst danach einen neuen Screenshot und machst den nächsten Schritt.\n"
    "4. Wiederhole, bis die Aufgabe vollständig erledigt ist.\n"
    "5. Wenn die Aufgabe erledigt ist, rufe task_finished mit einer kurzen Zusammenfassung auf.\n"
    "Regeln:\n"
    "- Reines Diktat / Text → type_text.\n"
    "- Anwendung öffnen → open_app.\n"
    "- Tastenkombination → press_keys.\n"
    "- Klick auf ein sichtbares UI-Element → click mit Koordinaten aus dem Screenshot.\n"
    "- Fenster fokussieren → focus_window.\n"
    "- Latenz: Wenn mehrere Aktionen sicher direkt hintereinander ausführbar sind, ohne "
    "dass du den Bildschirm dazwischen prüfen musst (z. B. Text tippen und danach Enter, "
    "oder eine App öffnen und sofort tippen), gib sie in EINER Antwort als MEHRERE "
    "tool_calls zurück. Bei unsicheren Klick-Koordinaten oder wenn ein Zustand erst "
    "sichtbar werden muss, nur EIN Tool pro Antwort aufrufen und den neuen Screenshot abwarten.\n"
    "- Mehrschrittige Aufgaben (z. B. \"öffne Firefox und geh zu Gmail\") erst am Ende mit "
    "task_finished abschließen.\n"
    "Antworte auf Deutsch."
)


def _img(data: bytes) -> dict:
    mime = getattr(screenshot, "IMAGE_MIME", "image/jpeg")
    return {"type": "image_url",
            "image_url": {"url": f"data:{mime};base64," + base64.b64encode(data).decode()}}


def run_task(transcribed_text: str, screenshot_data: bytes, scale=(1.0, 1.0),
             max_steps: int = 10) -> str:
    """Mehrstufige Computer-Use-Schleife. Gibt die Abschluss-Zusammenfassung zurück."""
    executor.set_click_scale(*scale)  # Klick-Koordinaten des ersten Bildes korrekt mappen
    t_task = time.perf_counter()
    print(f"[agent] Aufgabe: {transcribed_text!r} | Modell: {config.ACTION_MODEL}")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": f"Aufgabe: \"{transcribed_text}\""},
            _img(screenshot_data),
        ]},
    ]

    summary = ""
    for step in range(max_steps):
        t0 = time.perf_counter()
        data = openrouter.chat(
            model=config.ACTION_MODEL, messages=messages,
            tools=TOOLS, tool_choice="auto", max_tokens=1024,
            extra={"reasoning_effort": "low"},
        )
        dt = time.perf_counter() - t0
        msg = data["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []
        print(f"[agent] Step {step + 1}: API-Call {dt:.1f}s, "
              f"{len(tool_calls)} Tool-Call(s)")

        if not tool_calls:
            if msg.get("content"):
                summary = msg["content"].strip()
                print(f"[agent] Step {step + 1}: keine Tool-Calls — Antwort: {summary[:120]!r}")
            else:
                print(f"[agent] Step {step + 1}: keine Tool-Calls, kein Content — Ende")
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
                print(f"[agent]   → task_finished: {summary!r}")
                break
            print(f"[agent]   → ausführen: {name}({args})")
            t_exec = time.perf_counter()
            try:
                executor.execute(name, args)
                result = "ok"
            except Exception as e:
                result = f"Fehler: {type(e).__name__}: {e}"
            print(f"[agent]   ← {name}: {result[:100]} ({time.perf_counter() - t_exec:.2f}s)")
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

        if done:
            break

        t_shot = time.perf_counter()
        try:
            img, sx, sy = screenshot.capture()
            executor.set_click_scale(sx, sy)
        except Exception:
            img = screenshot_data
        print(f"[agent]   Screenshot nach Aktion ({time.perf_counter() - t_shot:.2f}s, "
              f"{len(img) // 1024} KB)")
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": "Aktueller Bildschirm (nach deiner letzten Aktion):"},
                _img(img),
            ],
        })

    print(f"[agent] Loop-Ende nach {time.perf_counter() - t_task:.1f}s "
          f"(max_steps={max_steps}) | summary: {summary[:120]!r}")
    return summary
