"""PortAudio callbacks must not be able to die quietly (audit M-A1).

sounddevice calls back on a PortAudio thread. Anything that escapes is caught
by python-sounddevice, printed to stderr, and then **it stops calling back** —
the stream object stays open, `just selftest` still says the audio devices are
fine, and wake / VAD / capture are simply dead. Nothing in the suite drove that
path, so a single bad frame could have taken hands-free operation out for a
whole session with no error anyone would see.
"""

import logging

import numpy as np

from friday.audio.capture import Recorder
from friday.audio.guard import CallbackGuard
from friday.audio.wake import FarEndRef, WakeCallbacks, WakeListener
from friday.audio.aec import NullAec


class RaisingDetector:
    """openWakeWord raises on a frame it cannot shape — the audit's repro."""

    def __init__(self, fail_times: int = 10_000):
        self.calls = 0
        self._fail_times = fail_times

    def score(self, frame: np.ndarray) -> float:
        self.calls += 1
        if self.calls <= self._fail_times:
            raise ValueError("cannot reshape array of size 321 into shape (1,320)")
        return 0.9


class OkVad:
    def is_speech(self, frame: np.ndarray) -> bool:
        return False


def _listener(detector, fired: list) -> WakeListener:
    return WakeListener(
        detector=detector,
        vad=OkVad(),
        aec=NullAec(),
        callbacks=WakeCallbacks(
            on_wake=lambda: fired.append("wake"),
            on_speech_end=lambda: None,
            on_barge=lambda: None,
        ),
        far_ref=FarEndRef(),
        threshold=0.5,
        frame_len=320,
        refractory_s=0.0,
        is_idle=lambda: True,
        is_speaking=lambda: False,
        schedule=lambda cb: cb(),
    )


def _indata(n: int = 320) -> np.ndarray:
    return np.zeros((n, 1), dtype=np.float32)


def test_a_raising_detector_never_escapes_into_sounddevice(caplog):
    fired: list = []
    wl = _listener(RaisingDetector(), fired)

    with caplog.at_level(logging.ERROR):
        for _ in range(20):
            wl._sd_callback(_indata(), 320, None, None)  # must not raise

    assert wl.detector is None, "a detector that always raises must be disabled"
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1, "loud once, not once per frame"
    assert "E_AUDIO_DEAD" in errors[0].getMessage()
    assert "wake" in errors[0].getMessage()


def test_a_transient_failure_does_not_disable_anything(caplog):
    """Consecutive, not cumulative — one bad frame must not cost the session."""
    fired: list = []
    wl = _listener(RaisingDetector(fail_times=1), fired)

    with caplog.at_level(logging.ERROR):
        for _ in range(10):
            wl._sd_callback(_indata(), 320, None, None)

    assert wl.detector is not None
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert fired, "the wake still fires once the detector recovers"


def test_the_capture_callback_swallows_and_keeps_copying(caplog):
    """Capture has nothing to disable, so it stays alive and says so once."""
    rec = Recorder(gate=lambda: True)
    broken = True

    original = rec._write

    def flaky(mono):
        if broken:
            raise ValueError("bad frame")
        original(mono)

    rec._write = flaky  # type: ignore[method-assign]

    with caplog.at_level(logging.ERROR):
        for _ in range(20):
            rec._sd_callback(_indata(), 320, None, None)  # must not raise
        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(errors) == 1 and "E_AUDIO_DEAD" in errors[0].getMessage()

        broken = False
        rec._sd_callback(_indata(), 320, None, None)

    assert rec.seconds > 0, "the capture callback keeps working after recovery"


def test_guard_counts_consecutively_and_calls_on_disable_once():
    disabled: list = []
    g = CallbackGuard("probe", limit=2, on_disable=lambda: disabled.append(1))

    def boom():
        raise RuntimeError("x")

    for _ in range(5):
        g.run(boom)
    assert disabled == [1]
    assert g.disabled is True
