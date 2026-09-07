"""Einstieg: Audio-Pipeline (Thread) + Worker (ASR→Action) + Tray (Main-Loop).

Latenz: Der Screenshot wird parallel zur ASR aufgenommen (ThreadPool), statt seriell
danach — der Bildschirm ändert sich während der Transkription normalerweise nicht.
Logging: Alle relevanten Schritte werden mit Zeitstempel + Dauer ausgegeben.
"""
import concurrent.futures
import queue
import sys
import threading
import time

from . import action_engine, asr, feedback, screenshot
from .audio import AudioPipeline
from .tray import Tray

_shot_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="screenshot"
)


class _TSWriter:
    """Stellt jedem print() einen Zeitstempel [HH:MM:SS] voran (für /tmp/da.log)."""

    def __init__(self, stream):
        self._stream = stream

    def write(self, s):
        if s.strip():
            self._stream.write(f"[{time.strftime('%H:%M:%S')}] {s}")
        else:
            self._stream.write(s)

    def flush(self):
        self._stream.flush()


def process_utterance(wav: bytes, icon=None):
    dur = len(wav) / 16000
    print(f"[worker] Äußerung ({dur:.2f}s) — starte ASR")
    # Screenshot JETZT parallel zur ASR aufnehmen (spart ~0.3-0.5 s serielle Latenz)
    shot_future = _shot_pool.submit(screenshot.capture)

    t0 = time.perf_counter()
    try:
        text = asr.transcribe(wav).strip()
    except Exception as e:
        print(f"[asr] FEHLER nach {time.perf_counter() - t0:.1f}s: {e}")
        return
    print(f"[asr] {text!r} ({time.perf_counter() - t0:.1f}s)")
    if not text:
        print("[asr] leer → übersprungen (kein Task)")
        return

    feedback.play_start()  # Task beginnt

    t_shot = time.perf_counter()
    try:
        img, sx, sy = shot_future.result(timeout=5)
    except Exception:
        img, sx, sy = screenshot.capture()  # Fallback: seriell
    print(f"[worker] Screenshot bereit ({time.perf_counter() - t_shot:.2f}s, "
          f"scale {sx:.2f}x{sy:.2f})")

    try:
        summary = action_engine.run_task(text, img, scale=(sx, sy))
    except Exception as e:
        print(f"[action] FEHLER: {type(e).__name__}: {e}")
        return

    feedback.play_done()  # Task fertig
    body = (summary or "").strip() or "Aufgabe erledigt"
    feedback.notify("Task successful", body, icon=icon)
    print(f"[agent] fertig nach {time.perf_counter() - t0:.1f}s gesamt: {body}")


def main():
    sys.stdout = _TSWriter(sys.stdout)  # Zeitstempel auf allen Log-Zeilen

    task_q = queue.Queue()
    stop = threading.Event()

    def on_utterance(wav):
        task_q.put(wav)
        print(f"[vad→queue] Utterance ({len(wav) / 16000:.2f}s), Queue: {task_q.qsize()}")

    audio = AudioPipeline(on_utterance)

    def on_quit():
        stop.set()
        audio.stop()
        _shot_pool.shutdown(wait=False)  # Executor-Threads dürfen Exit nicht blockieren

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
