"""Acoustic Echo Cancellation (AEC) adapter (G10, ADR-060).

Cleans the near-end microphone stream using the TTS playback stream as a far-end
reference, preventing Friday from self-triggering wake words or interrupting itself.
"""

from __future__ import annotations

import logging
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)


class AecProcessor(Protocol):
    """Interface for AEC implementations."""

    def process(self, near: np.ndarray, far: np.ndarray | None) -> np.ndarray:
        """Clean near-end audio given an optional far-end reference frame.

        Args:
            near: Mono float32 1D numpy array from mic.
            far: Mono float32 1D numpy array from TTS playback, or None if idle.

        Returns:
            Cleaned mono float32 1D numpy array with identical length.
        """
        ...


class NullAec:
    """Passthrough processor used when AEC is disabled or unavailable."""

    def process(self, near: np.ndarray, far: np.ndarray | None) -> np.ndarray:
        return near


class WebRtcAec:
    """AEC processor backed by pywebrtc-audio (WebRTC APM EchoCanceller)."""

    def __init__(self, sample_rate: int = 16000, frame_ms: int = 10) -> None:
        import pywebrtc_audio

        self._sample_rate = sample_rate
        self._frame_samples = (sample_rate * frame_ms) // 1000
        self._ec = pywebrtc_audio.EchoCanceller(
            sample_rate=sample_rate,
            num_channels=1,
            stream_delay_ms=0,
        )

    def process(self, near: np.ndarray, far: np.ndarray | None) -> np.ndarray:
        if far is None:
            return near

        # Ensure 1D float32
        near_f = np.asarray(near, dtype=np.float32)
        far_f = np.asarray(far, dtype=np.float32)

        # If lengths match frame_samples directly
        if len(near_f) == self._frame_samples and len(far_f) == self._frame_samples:
            return self._ec.process(near_f, far_f)

        # Slice into chunks of frame_samples
        n_samples = len(near_f)
        out = np.empty_like(near_f)
        for i in range(0, n_samples, self._frame_samples):
            n_chunk = near_f[i : i + self._frame_samples]
            if len(n_chunk) < self._frame_samples:
                # Pad trailing incomplete frame
                pad_len = self._frame_samples - len(n_chunk)
                n_padded = np.pad(n_chunk, (0, pad_len))
                f_chunk = far_f[i : i + self._frame_samples] if i < len(far_f) else np.zeros(self._frame_samples, dtype=np.float32)
                if len(f_chunk) < self._frame_samples:
                    f_chunk = np.pad(f_chunk, (0, self._frame_samples - len(f_chunk)))
                cleaned = self._ec.process(n_padded, f_chunk)
                out[i : i + len(n_chunk)] = cleaned[: len(n_chunk)]
            else:
                f_chunk = far_f[i : i + self._frame_samples] if i + self._frame_samples <= len(far_f) else np.zeros(self._frame_samples, dtype=np.float32)
                cleaned = self._ec.process(n_chunk, f_chunk)
                out[i : i + self._frame_samples] = cleaned

        return out


def create(*, enabled: bool = True, sample_rate: int = 16000, frame_ms: int = 10) -> AecProcessor:
    """Factory creating an AecProcessor, falling soft to NullAec on failure."""
    if not enabled:
        return NullAec()

    try:
        return WebRtcAec(sample_rate=sample_rate, frame_ms=frame_ms)
    except Exception as exc:
        log.warning("Failed to initialize AEC (%s); falling back to NullAec", exc)
        return NullAec()
