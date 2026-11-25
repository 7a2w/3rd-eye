"""
Speech -> text, fully offline, using faster-whisper (falls back to openai-whisper).
The first run downloads the model once (~75-150 MB for base.en); after that no internet is needed.
"""
import numpy as np

import config


class Transcriber:
    def __init__(self, model_size: str = config.WHISPER_MODEL):
        self.backend = None
        try:
            from faster_whisper import WhisperModel
            print(f"[transcriber] loading faster-whisper '{model_size}' (first run downloads it)...")
            self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
            self.backend = "faster-whisper"
        except ImportError:
            try:
                import whisper
                print(f"[transcriber] loading openai-whisper '{model_size}'...")
                self.model = whisper.load_model(model_size)
                self.backend = "whisper"
            except ImportError:
                raise RuntimeError("Install faster-whisper:  pip install faster-whisper")
        print(f"[transcriber] ready ({self.backend})")
        self._prev_text = ""

    def transcribe(self, audio: np.ndarray, use_context: bool = True) -> str:
        audio = np.nan_to_num(audio.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
        if len(audio) and np.abs(audio).max() > 1.5:      # int16 samples, or a broken read from a busy mic
            audio = audio / 32768.0 if np.abs(audio).max() <= 32768 else np.zeros_like(audio)
        audio = np.clip(audio, -1.0, 1.0).astype(np.float32)
        if len(audio) == 0 or float(np.sqrt(np.mean(audio ** 2))) < config.SILENCE_RMS:
            return ""  # silence: skip (saves CPU and avoids Whisper "hallucinating" words)
        # Passing the previous sentence as a prompt helps Whisper keep names/terms consistent.
        prompt = self._prev_text[-200:] if use_context else None
        if self.backend == "faster-whisper":
            segments, _ = self.model.transcribe(audio, language="en", beam_size=config.WHISPER_BEAM,
                                                vad_filter=True, initial_prompt=prompt,
                                                hotwords="Third Eye", condition_on_previous_text=False,
                                                no_speech_threshold=0.6, log_prob_threshold=-1.0)
            segments = [s for s in segments if s.no_speech_prob < 0.6 and s.avg_logprob > -1.0]
            text = " ".join(s.text.strip() for s in segments).strip()
        else:
            result = self.model.transcribe(audio, language="en", fp16=False, initial_prompt=prompt)
            text = result["text"].strip()
        if use_context and text:
            self._prev_text = text
        return text
