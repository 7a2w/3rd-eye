"""
The 30 s rolling buffer (stand-in for the earpiece's clip memory).

Audio blocks and camera JPEGs go in as they arrive; anything older than CLIP_SECONDS is dropped.
Saving a clip copies the buffer to the session folder as clip_NNN.wav plus clip_NNN/ frames.
"""
import collections
import threading
import time
import wave
from pathlib import Path

import numpy as np

import config


class RollingBuffer:
    def __init__(self, seconds: float = None, fps: float = None):
        self.seconds = seconds or config.CLIP_SECONDS
        self.frame_gap = 1.0 / (fps or config.CLIP_FPS)
        self._audio = collections.deque()      # (wall time, float32 block)
        self._frames = collections.deque()     # (wall time, jpeg bytes)
        self._last_frame = 0.0
        self._lock = threading.Lock()

    def _trim(self, dq, now):
        while dq and now - dq[0][0] > self.seconds:
            dq.popleft()

    def add_audio(self, block: np.ndarray):
        now = time.time()
        with self._lock:
            self._audio.append((now, block.copy()))
            self._trim(self._audio, now)

    def add_frame(self, jpeg: bytes):
        now = time.time()
        if now - self._last_frame < self.frame_gap:
            return
        self._last_frame = now
        with self._lock:
            self._frames.append((now, jpeg))
            self._trim(self._frames, now)

    def clear(self):
        with self._lock:
            self._audio.clear()
            self._frames.clear()

    def save(self, folder: Path, name: str) -> dict:
        """Write the buffer as <name>.wav and <name>/frame_NN.jpg. Returns what was written."""
        with self._lock:
            audio = [b for _, b in self._audio]
            frames = list(self._frames)
        folder = Path(folder)
        out = {"audio": None, "frames": 0, "seconds": 0.0}
        if audio:
            pcm = np.concatenate(audio)
            path = folder / f"{name}.wav"
            with wave.open(str(path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(config.SAMPLE_RATE)
                w.writeframes((np.clip(pcm, -1, 1) * 32767).astype("<i2").tobytes())
            out["audio"] = path.name
            out["seconds"] = round(len(pcm) / config.SAMPLE_RATE, 1)
        if frames:
            fdir = folder / name
            fdir.mkdir(exist_ok=True)
            for i, (_, jpg) in enumerate(frames, 1):
                (fdir / f"frame_{i:02d}.jpg").write_bytes(jpg)
            out["frames"] = len(frames)
        return out
