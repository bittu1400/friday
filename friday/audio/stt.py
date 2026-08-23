"""Speech to text (FR-10..13).

The concrete backend is chosen by the ADR-041 benchmark, not here — this
module defines the interface the daemon depends on and the two policy rules
that are backend-independent:

  FR-12  an empty / VAD-silent transcript yields "" -> the FSM returns to
         IDLE silently (E_STT_EMPTY), no planning turn, no speech.
  FR-13  a transcript over the token cap is REFUSED, not truncated — a wall
         of text is almost always a mis-capture or an injection attempt, and
         truncating it would act on half a sentence.

`language="en"` is hardcoded (FR-10): no detection pass (~15-20% faster, and
no hallucinated language on a mumbled input). STT is CPU-only (FR-11,
invariant #6) — the backend must never touch CUDA.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

# FR-13. Whitespace tokens are a cheap proxy for model tokens for a *guard*
# (the real tokenizer lives downstream in planning); a mis-capture or an
# injection wall trips this long before 500 real tokens.
MAX_TOKENS = 500


@dataclass(frozen=True)
class Transcript:
    text: str
    over_limit: bool = False  # FR-13: refused, not truncated

    @property
    def actionable(self) -> bool:
        """True iff this should proceed to planning. Empty (FR-12) and
        over-limit (FR-13) both stop here -> FSM to IDLE."""
        return bool(self.text) and not self.over_limit


class Backend(Protocol):
    """A CPU STT engine. Takes 16 kHz mono float32 PCM, returns raw text."""

    def transcribe(self, pcm: np.ndarray) -> str: ...


def finalize(raw: str) -> Transcript:
    """Apply the backend-independent FR-12/FR-13 policy to raw engine text."""
    text = raw.strip()
    if not text:
        return Transcript("", over_limit=False)
    if len(text.split()) > MAX_TOKENS:
        return Transcript("", over_limit=True)
    return Transcript(text, over_limit=False)


class Transcriber:
    """Wraps a Backend with the FR-12/FR-13 policy. The daemon holds one."""

    def __init__(self, backend: Backend) -> None:
        self._backend = backend

    def run(self, pcm: np.ndarray) -> Transcript:
        return finalize(self._backend.transcribe(pcm))


class FasterWhisperBackend:
    """faster-whisper (CTranslate2), CPU only. The winner of the ADR-041
    backend round (beat whisper.cpp 2.8x); the model + compute_type are the
    round-2 sweep verdict, read from config so they can be tuned without a
    code change. `create()` fails soft like `Speaker` — no library, no model,
    the daemon stays text-only."""

    def __init__(self, model: object, *, beam: int, hotwords: str) -> None:
        self._model = model
        self._beam = beam
        self._hotwords = hotwords or None

    @classmethod
    def create(
        cls,
        model_name: str,
        *,
        compute_type: str,
        threads: int,
        beam: int = 1,
        hotwords: str = "",
    ) -> "FasterWhisperBackend | None":
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            return None
        try:
            m = WhisperModel(
                model_name, device="cpu", compute_type=compute_type, cpu_threads=threads
            )
        except Exception:
            return None
        return cls(m, beam=beam, hotwords=hotwords)

    def transcribe(self, pcm: np.ndarray) -> str:
        # language="en" hardcoded (FR-10): no detection pass. VAD on (FR-12).
        # beam=1 + domain hotwords are the ADR-042 tuning (fix proper nouns,
        # lower latency).
        segments, _ = self._model.transcribe(
            pcm,
            language="en",
            vad_filter=True,
            beam_size=self._beam,
            hotwords=self._hotwords,
        )
        return " ".join(s.text.strip() for s in segments)
