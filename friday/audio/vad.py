"""Voice Activity Detection (VAD) adapter + SpeechGate (G10, ADR-062).

Pure debounce state machine for start-of-speech and end-of-utterance detection,
paired with a webrtcvad adapter for per-frame classification.
"""

from __future__ import annotations

import logging
from typing import Protocol

import numpy as np

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
    """Factory creating a Vad instance, falling soft to None on failure."""
    try:
        return WebRtcVad(mode=mode, sample_rate=sample_rate)
    except Exception as exc:
        log.warning("Failed to initialize VAD (%s); voice activity detection disabled", exc)
        return None
