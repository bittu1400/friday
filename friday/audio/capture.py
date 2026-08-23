"""Mic capture (FR-4, FR-6; diagram 05).

A `sounddevice` InputStream at 16 kHz mono float32 — whisper's native rate,
so no resample step. Audio lands in a preallocated 15 s ring; the callback
runs on a PortAudio thread and therefore does the absolute minimum: it
checks the gate (FR-6) and copies samples. It allocates nothing, blocks on
nothing, and never touches the database (architecture.md §5).

The gate is the FSM's `mic_open` (ADR-014): audio is written in exactly one
state, CAPTURING. A held key past 15 s just stops filling the ring (FR-4);
the FSM's own 15 s timer ends the capture.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from .. import config


class Recorder:
    """Owns the ring buffer and the gate check. Split from the stream so the
    buffer logic is testable without audio hardware: feed frames to `_write`
    directly. The daemon calls `open`/`close`/`collect`/`reset`."""

    def __init__(
        self,
        gate: Callable[[], bool],
        *,
        sample_rate: int = config.STT_SAMPLE_RATE,
        max_seconds: int = config.MAX_CAPTURE_S,
    ) -> None:
        self._gate = gate
        self._sr = sample_rate
        self._cap = sample_rate * max_seconds
        self._buf = np.zeros(self._cap, dtype=np.float32)  # preallocated once
        self._n = 0  # write cursor
        self._stream: object | None = None

    # --- callback-side: no allocation, no blocking ------------------------

    def _write(self, mono: np.ndarray) -> None:
        """Append mono float32 frames if the gate is open and there is room.
        Called from the PortAudio thread; must not allocate."""
        if not self._gate():  # FR-6: closed outside CAPTURING
            return
        room = self._cap - self._n
        if room <= 0:  # FR-4: 15 s hard cap, drop the overflow
            return
        take = min(mono.shape[0], room)
        self._buf[self._n : self._n + take] = mono[:take]
        self._n += take

    # --- daemon-side ------------------------------------------------------

    def collect(self) -> np.ndarray:
        """Return a copy of what was captured (one allocation, off the audio
        thread). Empty if nothing came in."""
        return self._buf[: self._n].copy()

    def reset(self) -> None:
        self._n = 0

    @property
    def seconds(self) -> float:
        return self._n / self._sr

    @property
    def is_active(self) -> bool:
        """True if the audio stream is open and actively recording."""
        return self._stream is not None and getattr(self._stream, "active", False)

    def ensure_open(self) -> bool:
        """Ensure audio stream is active; reopens if closed or dropped (e.g. suspend/resume)."""
        if not self.is_active:
            self.close()
            return self.open()
        return True

    def open(self) -> bool:
        """Start the InputStream. Fail-soft: no device / no library -> False,
        the daemon degrades to text-only rather than crashing."""
        try:
            import sounddevice as sd
        except ImportError:
            return False

        def _cb(indata, frames, time_info, status):  # noqa: ANN001 - sd signature
            # indata: (frames, 1) float32. Column 0 is the mono channel.
            self._write(indata[:, 0])

        try:
            self._stream = sd.InputStream(
                samplerate=self._sr, channels=1, dtype="float32", callback=_cb
            )
            self._stream.start()
        except Exception:
            self._stream = None
            return False
        return True

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
