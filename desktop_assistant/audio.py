"""Audio-Aufnahme (sounddevice, 24/7) + Silero-VAD (v5, stateful)."""
import collections
import io
import queue
import threading
import wave

import numpy as np
import onnxruntime as ort
import sounddevice as sd

from . import config


def choose_input_device():
    """Wählt ein Eingabegerät (portabel): System-Default-Input, per AUDIO_DEVICE übersteuerbar."""
    if config.AUDIO_DEVICE:
        v = str(config.AUDIO_DEVICE)
        return int(v) if v.isdigit() else v
    # System-Default-Input (PulseAudio/PipeWire-Default-Source) — portabel & korrekt.
    try:
        idx = int(sd.default.device[0])
        if idx >= 0:
            name = sd.query_devices(idx).get("name", "")
            if "monitor" not in name.lower():
                return idx
    except Exception:
        pass
    # Fallback: erstes Nicht-Monitor-Input
    try:
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) <= 0:
                continue
            if "monitor" in d.get("name", "").lower():
                continue
            return i
    except Exception as e:
        print(f"[audio] Device-Auto-Detect fehlgeschlagen: {e}")
    return None  # System-Default


def _to_wav(audio: np.ndarray, sr: int) -> bytes:
    """float32 [-1,1] → 16-bit-PCM-WAV-Bytes."""
    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


class SileroVAD:
    """Silero-VAD v5 (stateful) über onnxruntime."""

    def __init__(self, model_path):
        self.sess = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self.sr = np.array(config.SAMPLE_RATE, dtype=np.int64)
        self.window = config.VAD_WINDOW_SAMPLES
        self.threshold = config.VAD_THRESHOLD
        # Silero v5 braucht einen Context-Buffer (64 Samples @16kHz), der jedem Chunk
        # vorangestellt und nach jeder Inferenz aktualisiert wird.
        self.context_size = 64 if config.SAMPLE_RATE == 16000 else 32
        self.reset()

    def reset(self):
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, self.context_size), dtype=np.float32)

    def prob(self, chunk: np.ndarray) -> float:
        if len(chunk) < self.window:
            chunk = np.pad(chunk, (0, self.window - len(chunk)))
        x = chunk[: self.window].astype(np.float32).reshape(1, -1)
        x = np.concatenate([self._context, x], axis=1)
        out, state_n = self.sess.run(None, {"input": x, "state": self._state, "sr": self.sr})
        self._state = state_n
        self._context = x[:, -self.context_size:]
        return float(out[0, 0])


class AudioPipeline(threading.Thread):
    """Dauerläufer: nimmt auf, detektiert Äußerungen per VAD, meldet sie als WAV."""

    def __init__(self, on_utterance):
        super().__init__(daemon=True, name="audio")
        self.on_utterance = on_utterance
        self._stop = threading.Event()
        self._active = threading.Event()
        self._active.set()  # default: aktiviert
        self.q = queue.Queue()
        self.stream = None

    def set_active(self, active: bool):
        self._active.set() if active else self._active.clear()

    def stop(self):
        self._stop.set()

    def _cb(self, indata, frames, time_info, status):
        self.q.put(indata[:, 0].astype(np.float32).copy())

    def run(self):
        sr = config.SAMPLE_RATE
        window = config.VAD_WINDOW_SAMPLES
        threshold = config.VAD_THRESHOLD
        min_silence = int(config.VAD_MIN_SILENCE_MS * sr / 1000)
        max_speech = int(config.VAD_MAX_SPEECH_S * sr)
        pad = int(config.VAD_SPEECH_PAD_MS * sr / 1000)

        vad = SileroVAD(config.VAD_MODEL_PATH)
        device = choose_input_device()
        self.stream = sd.InputStream(
            samplerate=sr, channels=1, dtype="float32",
            blocksize=window, device=device, callback=self._cb,
        )
        self.stream.start()
        print(f"[audio] Aufnahme läuft (Device={device}, {sr} Hz, VAD-Threshold={threshold})")

        triggered = False
        temp_end = 0
        idx = 0
        pre = collections.deque(maxlen=max(1, pad // window + 1))
        utt = []

        try:
            while not self._stop.is_set():
                try:
                    chunk = self.q.get(timeout=0.5)
                except queue.Empty:
                    continue

                if not self._active.is_set():
                    vad.reset()
                    triggered = False
                    utt = []
                    pre.clear()
                    idx += window
                    continue

                prob = vad.prob(chunk)

                if prob >= threshold:
                    if temp_end != 0:
                        temp_end = 0
                    if not triggered:
                        triggered = True
                        utt = list(pre)
                    utt.append(chunk)
                elif triggered:
                    utt.append(chunk)
                    if temp_end == 0:
                        temp_end = idx
                    if idx - temp_end >= min_silence:
                        triggered = False
                        temp_end = 0
                        self._emit(utt, sr)
                        utt = []
                        vad.reset()

                if triggered and len(utt) * window >= max_speech:
                    triggered = False
                    self._emit(utt, sr)
                    utt = []
                    vad.reset()

                pre.append(chunk)
                idx += window
        finally:
            self.stream.stop()
            self.stream.close()
            print("[audio] Aufnahme gestoppt")

    def _emit(self, chunks, sr):
        if not chunks:
            return
        audio = np.concatenate(chunks)
        if len(audio) < sr * 0.1:  # < 100 ms → verwerfen
            return
        print(f"[vad] Äußerung erkannt ({len(audio) / sr:.2f}s)")
        self.on_utterance(_to_wav(audio, sr))
