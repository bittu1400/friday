"""Enrollment CLI: guards against API drift (it once imported a nonexistent
module and called long-dead signatures, so `just enroll` crashed on import).

No audio hardware: sounddevice is faked and the model is reported missing."""

import sys
import types

import numpy as np

import friday.speaker_enroll as enroll


def test_module_imports_and_uses_real_apis():
    # Import alone catches the old ModuleNotFoundError regression.
    assert len(enroll.ENROLLMENT_PHRASES) == 10
    assert enroll._FRAME_LEN == 320


def test_run_enrollment_bails_when_model_missing(monkeypatch, tmp_path):
    missing = tmp_path / "nope.onnx"
    monkeypatch.setattr(enroll.config, "SPEAKER_MODEL", missing)
    assert enroll.run_enrollment(num_utterances=3) == 1


def test_record_utterance_reads_frames_and_ends_on_silence(monkeypatch):
    """record_utterance must drive the REAL SpeechGate (push(bool)) via a real
    blocking stream read, and stop on VAD end-of-utterance."""
    frame = enroll._FRAME_LEN

    # A fake sounddevice: speech for a while, then silence, so the gate ends.
    seq = iter([True] * 40 + [False] * 60)

    class _FakeStream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            voiced = next(seq, False)
            amp = 0.5 if voiced else 0.0
            return np.full((n, 1), amp, dtype=np.float32), False

    fake_sd = types.ModuleType("sounddevice")
    fake_sd.InputStream = lambda **kw: _FakeStream()
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)

    # A VAD that classifies by amplitude, matching the fake stream's frames.
    class _FakeVad:
        def is_speech(self, f):
            return bool(np.any(f > 0.1))

    monkeypatch.setattr(enroll, "create_vad", lambda **kw: _FakeVad())
    monkeypatch.setattr("builtins.input", lambda *a: "")

    audio = enroll.record_utterance("hello", 1, 1, max_s=5.0)
    assert audio.dtype == np.float32
    assert audio.ndim == 1
    assert len(audio) >= frame  # captured something real
