"""Voice out: Kokoro-82M via kokoro-onnx, CPU only (ADR-039/040).

The runtime, model, and thread count are the measured optimum from the G5
benchmark: `kokoro-onnx` on the onnxruntime `CPUExecutionProvider`, the fp32
`model.onnx`, `intra_op_num_threads=8` (= the P-core count), no torch. This
holds FR-71 (zero VRAM, one CUDA process) by construction — there is no CUDA
code in this package.

`Speaker.create()` fails soft: if the model or an audio device is missing it
returns `None`, and the caller stays text-only rather than crashing. `say()`
synthesizes and plays, blocking until finished or until `stop()` is called
from another thread — that is barge-in (FR-73, FR-7): the PTT handler on the
event loop calls `stop()` to cut playback mid-sentence while the turn's
`say()` runs in a worker thread. `say()` returns True if it played to the
end, False if it was cancelled (or produced nothing).

Heavy imports (onnxruntime, kokoro_onnx, sounddevice) are lazy so importing
this module — and the whole app under test — costs nothing and needs no
audio hardware.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path


def _resample_16k(samples, sr: int):
    """Resample mono float32 audio to 16 kHz for the AEC reference."""
    import numpy as np
    import scipy.signal

    if sr == 16000:
        return np.asarray(samples, dtype=np.float32)
    if sr == 24000:
        return scipy.signal.resample_poly(samples, 2, 3).astype(np.float32)
    return scipy.signal.resample(samples, int(len(samples) * 16000 / sr)).astype(np.float32)


class Speaker:
    """Loads Kokoro once, then voices strings on demand. `say()` blocks;
    `stop()` cancels an in-flight `say()` from another thread (barge-in)."""

    def __init__(self, kokoro: object, voice: str, far_ref: object | None = None) -> None:
        self._kokoro = kokoro
        self._voice = voice
        self._far_ref = far_ref
        self._cancel = threading.Event()
        self._stream: object | None = None  # the in-flight OutputStream, for stop()

    @property
    def voice(self) -> str:
        return self._voice

    @classmethod
    def create(
        cls,
        model_path: Path,
        voices_path: Path,
        *,
        voice: str,
        fallback: str,
        threads: int = 8,
        far_ref: object | None = None,
    ) -> "Speaker | None":
        """Build a Speaker, or return None if the model is absent/unloadable.

        The voice is resolved against the blob: primary if present, else the
        fallback, else None (ADR-040 / OQ-22)."""
        if not model_path.exists() or not voices_path.exists():
            return None
        try:
            import onnxruntime as ort
            from kokoro_onnx import Kokoro
        except ImportError:
            return None

        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        try:
            sess = ort.InferenceSession(
                str(model_path), so, providers=["CPUExecutionProvider"]
            )
            kokoro = Kokoro.__new__(Kokoro)
            kokoro._setup(
                session=sess,
                model_path=str(model_path),
                voices_path=str(voices_path),
                espeak_config=None,
                vocab_config=None,
            )
        except Exception:
            return None

        available = set(kokoro.get_voices())
        chosen = voice if voice in available else fallback
        if chosen not in available:
            return None
        return cls(kokoro, chosen, far_ref=far_ref)

    def say(self, text: str, on_play: Callable[[], None] | None = None) -> bool:
        """Synthesize `text` and play it, blocking until finished or cancelled.
        Returns True if it played to the end, False if it produced nothing or
        was cut short by `stop()`. A failure to synthesize or reach the audio
        device is swallowed (returns False) — a silent turn beats a crash, and
        the text was already printed by the caller.

        `on_play`, if given, is called once at the instant audio starts (after
        synthesis, before the first sample) — the daemon uses it to measure
        TTFA. It must not raise; it runs on the worker thread."""
        if not text or not text.strip():
            return False
        self._cancel.clear()
        try:
            samples, sr = self._kokoro.create(
                text, voice=self._voice, speed=1.0, lang="en-us"
            )
            # Barge-in may have arrived during synthesis; don't start audio.
            if self._cancel.is_set():
                return False
            import numpy as np
            import sounddevice as sd

            # The AEC reference must be what the SPEAKER is playing right now.
            # Writing the whole utterance in one lump before playback and
            # letting the listener drain it free-running does not achieve that:
            # measured 2026-08-25, the reference was absent for 40% of playback
            # frames (AEC a pure passthrough, 0 dB) and worth only -15.6 dB on
            # the rest — so Friday heard herself, the barge VAD called it
            # speech, and every reply was cut off mid-sentence. A 5 s ring cap
            # made it worse: any reply longer than 5 s lost its beginning, so
            # the reference held the WRONG audio for the whole utterance.
            #
            # Feeding it from the output callback ties the reference to the
            # device's own playback position, sample for sample.
            samples_16k = _resample_16k(samples, sr) if self._far_ref is not None else None

            if on_play is not None:
                on_play()

            pos = 0

            def _callback(outdata, frames, time_info, status):  # noqa: ANN001
                nonlocal pos
                if self._cancel.is_set():
                    raise sd.CallbackAbort
                chunk = samples[pos : pos + frames]
                n = len(chunk)
                outdata[:n, 0] = chunk
                if self._far_ref is not None and samples_16k is not None:
                    i0 = (pos * 16000) // sr
                    i1 = ((pos + n) * 16000) // sr
                    self._far_ref.write(samples_16k[i0:i1])
                pos += n
                if n < frames:
                    outdata[n:, 0] = 0
                    raise sd.CallbackStop

            done = threading.Event()
            stream = sd.OutputStream(
                samplerate=sr, channels=1, dtype="float32",
                callback=_callback, finished_callback=done.set,
            )
            self._stream = stream
            try:
                with stream:
                    # Never wait unbounded on a device callback: if the driver
                    # never fires finished_callback, an un-timed wait would
                    # wedge the daemon's speak task forever — worse than the
                    # echo it is here to fix.
                    done.wait(timeout=len(samples) / sr + 5.0)
            finally:
                self._stream = None
        except Exception:
            return False
        return not self._cancel.is_set()

    def stop(self) -> None:
        """Cancel an in-flight `say()` (barge-in, FR-73). Safe to call from
        any thread and when nothing is playing. Sets the cancel flag so a
        cancel that lands mid-synthesis is honoured before playback starts,
        and stops the output stream so a `wait()` already in progress unblocks.
        """
        self._cancel.set()
        if self._far_ref is not None:
            self._far_ref.clear()
        # say() owns an OutputStream. `sd.stop()` used to be called here too,
        # but it only stops the module-level stream `sd.play()` uses and nothing
        # has called `sd.play()` since say() grew its own stream — it was noise
        # that made this look like it did more than it does.
        stream = self._stream
        if stream is not None:
            try:
                stream.abort(ignore_errors=True)
            except Exception:
                pass

