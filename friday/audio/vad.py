"""Voice Activity Detection (VAD) adapter + SpeechGate (G10, ADR-062).

Pure debounce state machine for start-of-speech and end-of-utterance detection,
paired with a per-frame classifier. Silero is the classifier since ADR-095;
`webrtcvad` remains as the fallback and is the cause of D3 (see SileroVad).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

import numpy as np

from friday import config

log = logging.getLogger(__name__)


class Vad(Protocol):
    """Interface for frame-level voice activity detection."""

    def is_speech(self, frame: np.ndarray) -> bool:
        """Return True if frame contains voice activity."""
        ...


class WebRtcVad:
    """VAD implementation wrapping webrtcvad."""

    def __init__(self, mode: int = 2, sample_rate: int = 16000) -> None:
        import webrtcvad

        self._sample_rate = sample_rate
        self._vad = webrtcvad.Vad(mode)

    def is_speech(self, frame: np.ndarray) -> bool:
        # Convert float32 [-1.0, 1.0] to 16-bit PCM bytes
        frame_f = np.asarray(frame, dtype=np.float32)
        pcm_i16 = (np.clip(frame_f, -1.0, 1.0) * 32767.0).astype(np.int16)
        pcm_bytes = pcm_i16.tobytes()
        return self._vad.is_speech(pcm_bytes, self._sample_rate)


class SileroVad:
    """Silero VAD (ONNX, CPU) — the classifier since ADR-095, replacing webrtcvad.

    D3: every hands-free capture ran the full 15 s cap. Driven through the real
    `SpeechGate` over the 20 real DMIC clips (each with 2 s of its own quietest
    room noise appended), `webrtcvad` emitted `end` on only 15 of 20 — on the
    failures it called 83-100 % of frames speech, room noise included, so
    trailing silence never accumulated. Silero ends 20/20 and its voiced
    fraction never exceeds 0.482 on any clip. Cost 0.048 ms per frame, 0.15 %
    of one core (ADR-095, OQ-51).

    The graph wants 512 samples; the mic path delivers 320 (WAKE_FRAME_MS, and
    openwakeword chunks to it). So buffer and hold the last verdict between
    inferences — the verdict then updates every 32 ms instead of every 20 ms,
    which is invisible against a 800 ms end-of-silence timer and leaves every
    caller's frame size alone.
    """

    _FRAME = 512      # what the graph wants at 16 kHz
    _CTX = 64         # v5+ prepends a context window; feeding a bare 512
                      # returns ~0.001 on obvious speech, silently, forever.

    def __init__(
        self,
        model_path: Path | None = None,
        threshold: float | None = None,
        sample_rate: int = 16000,
    ) -> None:
        import onnxruntime as ort

        if sample_rate != 16000:
            raise ValueError(f"SileroVad is 16 kHz only, got {sample_rate}")

        so = ort.SessionOptions()
        so.intra_op_num_threads = 1
        # The op18-ifless export carries three unused initializers and ORT warns
        # about each one at load. Under systemd that is three lines of noise in
        # the journal on every daemon start; the model is pinned by SHA256.
        so.log_severity_level = 3
        self._sess = ort.InferenceSession(
            str(model_path or config.VAD_MODEL), so, providers=["CPUExecutionProvider"]
        )
        self._sr = np.array(sample_rate, dtype=np.int64)
        self.threshold = config.VAD_THRESHOLD if threshold is None else threshold
        self.inferences = 0
        self.reset()

    def reset(self) -> None:
        """Clear stream state. Silero is stateful; a stale state biases scores."""
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._ctx = np.zeros((1, self._CTX), dtype=np.float32)
        self._buf = np.zeros(0, dtype=np.float32)
        self._voiced = False
        self.inferences = 0

    def is_speech(self, frame: np.ndarray) -> bool:
        self._buf = np.concatenate([self._buf, np.asarray(frame, dtype=np.float32)])
        while len(self._buf) >= self._FRAME:
            chunk = self._buf[: self._FRAME].reshape(1, -1)
            self._buf = self._buf[self._FRAME :]
            x = np.concatenate([self._ctx, chunk], axis=1)
            self._ctx = x[:, -self._CTX :]
            out, self._state = self._sess.run(
                None, {"input": x, "sr": self._sr, "state": self._state}
            )
            self.inferences += 1
            self._voiced = float(out[0][0]) >= self.threshold
        return self._voiced


class SpeechGate:
    """Pure debounce state machine for speech start / end detection.

    Frame-agnostic counter logic. Emits 'start' on sustained speech and
    'end' on trailing silence following active speech.
    """

    def __init__(
        self,
        frame_ms: int = 20,
        end_silence_s: float = 0.8,
        min_speech_s: float = 0.3,
    ) -> None:
        self.frame_ms = frame_ms
        self.end_silence_s = end_silence_s
        self.min_speech_s = min_speech_s

        self._min_speech_frames = max(1, int(round((min_speech_s * 1000) / frame_ms)))
        self._end_silence_frames = max(1, int(round((end_silence_s * 1000) / frame_ms)))

        self.in_speech = False
        self._voiced_count = 0
        self._silence_count = 0

    def push(self, voiced: bool) -> str | None:
        """Feed one frame's voiced classification; return 'start', 'end', or None."""
        if voiced:
            self._silence_count = 0
            if not self.in_speech:
                self._voiced_count += 1
                if self._voiced_count >= self._min_speech_frames:
                    self.in_speech = True
                    return "start"
            return None
        else:
            if not self.in_speech:
                # Silence before speech ever started resets pre-speech counter
                self._voiced_count = 0
                return None
            else:
                self._silence_count += 1
                if self._silence_count >= self._end_silence_frames:
                    self.in_speech = False
                    self._voiced_count = 0
                    self._silence_count = 0
                    return "end"
                return None

    def reset(self) -> None:
        """Reset all counters and state."""
        self.in_speech = False
        self._voiced_count = 0
        self._silence_count = 0


def create(mode: int = 2, sample_rate: int = 16000) -> Vad | None:
    """Factory creating a Vad instance, falling soft to None on failure.

    Silero first (ADR-095). `webrtcvad` is kept as the fallback so a missing or
    corrupt model file degrades to the pre-ADR-095 behaviour rather than to no
    VAD at all — but it degrades LOUDLY, because that behaviour is D3: captures
    that never end. `mode` applies to the fallback only.
    """
    try:
        return SileroVad(sample_rate=sample_rate)
    except Exception as exc:
        log.warning(
            "Silero VAD unavailable (%s); falling back to webrtcvad, which does "
            "not reliably end captures on this machine (D3). Run `just fetch-vad`.",
            exc,
        )
    try:
        return WebRtcVad(mode=mode, sample_rate=sample_rate)
    except Exception as exc:
        log.warning("Failed to initialize VAD (%s); voice activity detection disabled", exc)
        return None
