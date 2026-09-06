"""Einstieg: Audio-Pipeline (Thread) + Worker (ASR→Action) + Tray (Main-Loop).

Latenz: Der Screenshot wird parallel zur ASR aufgenommen (ThreadPool), statt seriell
danach — der Bildschirm ändert sich während der Transkription normalerweise nicht.
"""
import concurrent.futures
import queue
import threading

from . import action_engine, asr, feedback, screenshot
from .audio import AudioPipeline
from .tray import Tray

_shot_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="screenshot"
)


def process_utterance(wav: bytes, icon=None):
    # Screenshot JETZT parallel zur ASR aufnehmen (spart ~0.3-0.5 s serielle Latenz)
    shot_future = _shot_pool.submit(screenshot.capture)

    try:
        text = asr.transcribe(wav).strip()
    except Exception as e:
        print(f"[asr] Fehler: {e}")
        return
    if not text:
        return
    print(f"[asr] {text!r}")

    feedback.play_start()  # Task beginnt

    try:
        img, sx, sy = shot_future.result(timeout=5)
    except Exception:
        img, sx, sy = screenshot.capture()  # Fallback: seriell

    try:
        summary = action_engine.run_task(text, img, scale=(sx, sy))
    except Exception as e:
        print(f"[action] Fehler: {e}")
        return

    feedback.play_done()  # Task fertig
    body = (summary or "").strip() or "Aufgabe erledigt"
    feedback.notify("Task successful", body, icon=icon)
    print(f"[agent] fertig: {body}")


def main():
    task_q = queue.Queue()
    stop = threading.Event()

    def on_utterance(wav):
        task_q.put(wav)

    audio = AudioPipeline(on_utterance)

    def on_quit():
        stop.set()
        audio.stop()

    tray = Tray(audio, on_quit)

    def worker():
        while not stop.is_set():
            try:
                wav = task_q.get(timeout=0.5)
            except queue.Empty:
                continue
            process_utterance(wav, icon=tray.icon)

    audio.start()
    threading.Thread(target=worker, daemon=True, name="worker").start()
    tray.run()


if __name__ == "__main__":
    main()
