"""Einstieg: Audio-Pipeline (Thread) + Worker (ASR→Action) + Tray (Main-Loop)."""
import queue
import threading

from . import action_engine, asr, screenshot
from .audio import AudioPipeline
from .tray import Tray


def process_utterance(wav: bytes):
    try:
        text = asr.transcribe(wav).strip()
    except Exception as e:
        print(f"[asr] Fehler: {e}")
        return
    if not text:
        return
    print(f"[asr] {text!r}")

    try:
        img = screenshot.capture_png()
        summary = action_engine.run_task(text, img)
    except Exception as e:
        print(f"[action] Fehler: {e}")
        return

    if summary:
        print(f"[agent] fertig: {summary}")


def main():
    task_q = queue.Queue()
    stop = threading.Event()

    def on_utterance(wav):
        task_q.put(wav)

    audio = AudioPipeline(on_utterance)
    audio.start()

    def worker():
        while not stop.is_set():
            try:
                wav = task_q.get(timeout=0.5)
            except queue.Empty:
                continue
            process_utterance(wav)

    threading.Thread(target=worker, daemon=True, name="worker").start()

    def on_quit():
        stop.set()
        audio.stop()

    tray = Tray(audio, on_quit)
    tray.run()


if __name__ == "__main__":
    main()
