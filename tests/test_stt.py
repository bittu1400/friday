"""STT policy (FR-12 empty, FR-13 over-limit) — backend-independent."""

import numpy as np

from friday.audio import stt


def test_empty_is_not_actionable():
    t = stt.finalize("")
    assert t.text == ""
    assert t.over_limit is False
    assert t.actionable is False


def test_whitespace_only_is_empty():
    assert stt.finalize("   \n\t ").actionable is False


def test_normal_transcript_is_actionable():
    t = stt.finalize("  open my browser  ")
    assert t.text == "open my browser"  # stripped
    assert t.actionable is True


def test_over_limit_is_refused_not_truncated():
    """FR-13: >500 tokens -> refused (empty text, over_limit), not cut down."""
    wall = " ".join(["word"] * 501)
    t = stt.finalize(wall)
    assert t.over_limit is True
    assert t.text == ""  # not a truncated prefix
    assert t.actionable is False


def test_exactly_at_limit_is_allowed():
    ok = " ".join(["word"] * 500)
    assert stt.finalize(ok).actionable is True


def test_transcriber_applies_policy_over_backend():
    class Fake:
        def __init__(self, out):
            self._out = out

        def transcribe(self, pcm):
            return self._out

    pcm = np.zeros(16000, dtype=np.float32)
    assert stt.Transcriber(Fake("hello there")).run(pcm).actionable is True
    assert stt.Transcriber(Fake("")).run(pcm).actionable is False
    assert stt.Transcriber(Fake(" ".join(["x"] * 900))).run(pcm).over_limit is True
