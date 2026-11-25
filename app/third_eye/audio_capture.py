"""
Microphone -> audio chunks.

LiveMicSource   : records from the laptop mic (stand-in for the earpiece mic).
FileAudioSource : plays a recorded lecture file as if it were live (great backup for demo day).

Both put (start_time_seconds, numpy_float32_audio) chunks on `self.chunks` for the transcriber,
and both offer ask_question(), which grabs a few seconds of YOUR voice for the assistant.
"""
import queue
import threading
import time
import wave

import numpy as np

import config

try:
    import sounddevice as sd
except Exception:  # sounddevice not installed or no audio device
    sd = None


class _BaseSource:
    def __init__(self):
        self.chunks: "queue.Queue[tuple[float, np.ndarray]]" = queue.Queue()
        self.paused = False
        self.session_start = time.time()
        self._buf = []
        self._buf_len = 0
        self._buf_start = 0.0
        self._question_buf = None
        self._lock = threading.Lock()
        self.chunk_samples = int(config.CHUNK_SECONDS * config.SAMPLE_RATE)
        self.level = 0.0          # live loudness 0..1, shown as the mic meter in the dashboard
        self.on_audio = None      # called with every recorded block (feeds the clip buffer)

    def _update_level(self, block: np.ndarray):
        rms = float(np.sqrt(np.mean(block ** 2))) if len(block) else 0.0
        self.level = max(min(1.0, rms * 12), self.level * 0.8)   # quick rise, smooth fall

    def begin(self):
        """Start the lecture clock and begin recording."""
        self.start()

    def _add_lecture_audio(self, block: np.ndarray, t: float):
        if self._buf_len == 0:
            self._buf_start = t
        if self.on_audio is not None:
            self.on_audio(block)
        self._buf.append(block)
        self._buf_len += len(block)
        if self._buf_len >= self.chunk_samples:
            self._flush()

    def _flush(self):
        if self._buf_len:
            self.chunks.put((self._buf_start, np.concatenate(self._buf)))
        self._buf, self._buf_len = [], 0

    def ask_question(self) -> np.ndarray:
        """Record the user's question from the microphone (push-to-talk)."""
        if sd is None:
            raise RuntimeError("sounddevice is not installed, so the mic can't be used for questions.")
        audio = sd.rec(int(config.QUESTION_SECONDS * config.SAMPLE_RATE),
                       samplerate=config.SAMPLE_RATE, channels=1, dtype="float32")
        sd.wait()
        return audio[:, 0]

    def stop(self):
        self._flush()


class LiveMicSource(_BaseSource):
    def __init__(self, device=None):
        super().__init__()
        if sd is None:
            raise RuntimeError("Install sounddevice (pip install sounddevice) to use the microphone.")
        self.stream = sd.InputStream(samplerate=config.SAMPLE_RATE, channels=1, dtype="float32",
                                     callback=self._callback, device=device, blocksize=1600)

    def _callback(self, indata, frames, time_info, status):
        block = indata[:, 0].copy()
        self._update_level(block)
        with self._lock:
            if self._question_buf is not None:       # user is asking a question
                self._question_buf.append(block)
            elif not self.paused:                    # normal lecture recording
                self._add_lecture_audio(block, time.time() - self.session_start)

    def start(self):
        self.session_start = time.time()
        self.stream.start()

    def open_paused(self):
        """Open the mic for the setup screen: the level meter works, but nothing is recorded."""
        self.paused = True
        self.stream.start()

    def begin(self):
        with self._lock:
            self._buf, self._buf_len = [], 0
        self.session_start = time.time()
        self.paused = False

    def ask_question(self) -> np.ndarray:
        # Reuse the open stream instead of opening a second one (more reliable on most laptops).
        with self._lock:
            self._flush()
            self._question_buf = []
        time.sleep(config.QUESTION_SECONDS)
        with self._lock:
            audio = np.concatenate(self._question_buf) if self._question_buf else np.zeros(1, np.float32)
            self._question_buf = None
        return audio

    def stop(self):
        self.stream.stop()
        self.stream.close()
        with self._lock:
            self._flush()


def list_input_devices():
    """Microphones as [(device_number, name)], without the duplicates Windows lists for each driver."""
    if sd is None:
        return []
    try:
        devices = sd.query_devices()
        default_in = sd.default.device[0]
        hostapi = devices[default_in]["hostapi"] if default_in is not None and default_in >= 0 else 0
        mics, seen = [], set()
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0 and d["hostapi"] == hostapi and d["name"] not in seen:
                seen.add(d["name"])
                mics.append((i, d["name"]))
        return mics
    except Exception:
        return []


def load_audio(path: str) -> np.ndarray:
    """Load any audio file as 16 kHz mono float32."""
    try:  # faster-whisper ships a decoder that handles mp3/m4a/mp4/wav
        from faster_whisper.audio import decode_audio
        return decode_audio(path, sampling_rate=config.SAMPLE_RATE).astype(np.float32)
    except ImportError:
        pass
    try:
        import soundfile as sf
        data, sr = sf.read(path, dtype="float32", always_2d=True)
        data = data.mean(axis=1)
    except ImportError:
        with wave.open(path, "rb") as w:  # plain .wav fallback, no extra packages
            sr, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
            raw = w.readframes(w.getnframes())
        dtype = {1: np.uint8, 2: np.int16, 4: np.int32}[width]
        data = np.frombuffer(raw, dtype=dtype).astype(np.float32)
        if width == 1:
            data = (data - 128) / 128
        else:
            data /= float(np.iinfo(dtype).max)
        data = data.reshape(-1, ch).mean(axis=1)
    if sr != config.SAMPLE_RATE:  # simple resample
        n = int(len(data) * config.SAMPLE_RATE / sr)
        data = np.interp(np.linspace(0, len(data) - 1, n), np.arange(len(data)), data).astype(np.float32)
    return data


class FileAudioSource(_BaseSource):
    """Feeds a recorded lecture in real time, and plays it out loud so the audience hears it."""

    def __init__(self, path: str, play_out_loud: bool = True):
        super().__init__()
        self.audio = load_audio(path)
        self.play = play_out_loud and sd is not None
        self.finished = threading.Event()
        self._stopped = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.session_start = time.time()
        self._thread.start()

    def _run(self):
        block = config.SAMPLE_RATE // 10  # 0.1 s
        pos = 0
        out = None
        if self.play:
            out = sd.OutputStream(samplerate=config.SAMPLE_RATE, channels=1, dtype="float32")
            out.start()
        t0 = time.time()
        while pos < len(self.audio) and not self._stopped:
            if self.paused:
                time.sleep(0.1)
                t0 += 0.1
                continue
            piece = self.audio[pos:pos + block]
            if out is not None:
                out.write(piece.reshape(-1, 1))      # blocks ~0.1 s, keeps us real-time
            else:
                time.sleep(max(0.0, t0 + (pos + len(piece)) / config.SAMPLE_RATE - time.time()))
            self._update_level(piece)
            with self._lock:
                self._add_lecture_audio(piece, pos / config.SAMPLE_RATE)
            pos += block
        with self._lock:
            self._flush()
        if out is not None:
            out.stop()
            out.close()
        self.finished.set()

    def stop(self):
        self._stopped = True
        self.finished.wait(timeout=2)
        with self._lock:
            self._flush()
