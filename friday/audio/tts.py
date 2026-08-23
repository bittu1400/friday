"""Voice out: Kokoro-82M via kokoro-onnx, CPU only (ADR-039/040).

The runtime, model, and thread count are the measured optimum from the G5
benchmark: `kokoro-onnx` on the onnxruntime `CPUExecutionProvider`, the fp32
`model.onnx`, `intra_op_num_threads=8` (= the P-core count), no torch. This
holds FR-71 (zero VRAM, one CUDA process) by construction — there is no CUDA
code in this package.

`Speaker.create()` fails soft: if the model or an audio device is missing it
returns `None`, and the caller stays text-only rather than crashing. `say()`
synthesizes and plays blocking — cancellation (barge-in) is deferred to G6,
where the mic that would trigger it exists (ADR-040).

Heavy imports (onnxruntime, kokoro_onnx, sounddevice) are lazy so importing
this module — and the whole app under test — costs nothing and needs no
audio hardware.
"""

from __future__ import annotations

from pathlib import Path


class Speaker:
    """Loads Kokoro once, then voices strings on demand (blocking)."""

    def __init__(self, kokoro: object, voice: str) -> None:
        self._kokoro = kokoro
        self._voice = voice

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
        return cls(kokoro, chosen)

    def say(self, text: str) -> None:
        """Synthesize `text` and play it, blocking until finished. A failure
        to synthesize or reach the audio device is swallowed — a silent turn
        beats a crash, and the text was already printed by the caller."""
        if not text or not text.strip():
            return
        try:
            samples, sr = self._kokoro.create(
                text, voice=self._voice, speed=1.0, lang="en-us"
            )
            import sounddevice as sd

            sd.play(samples, sr)
            sd.wait()
        except Exception:
            return
