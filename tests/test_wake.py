import numpy as np
import pytest
import time
from friday import config
from friday.audio.aec import NullAec
from friday.audio.wake import WakeListener, WakeCallbacks, FarEndRef, WakeDetector, create_detector


class FakeDetector:
    def __init__(self, score: float):
        self._s = score

    def score(self, frame: np.ndarray) -> float:
        return self._s

    def reset(self) -> None:
        # Mirrors OpenWakeWordDetector.reset(): buffered audio and the retained
        # score are dropped, so the next score() cannot return the old value.
        self._s = 0.0


class FakeVad:
    def __init__(self, voiced: bool):
        self._v = voiced

    def is_speech(self, frame: np.ndarray) -> bool:
        return self._v


def test_config_constants_present():
    assert config.WAKE_FRAME_MS in (10, 20, 30)
    assert 0.0 < config.WAKE_THRESHOLD < 1.0
    assert config.VAD_END_SILENCE_S > config.VAD_MIN_SPEECH_S


def make(*, score: float, voiced: bool, idle: bool, speaking: bool, calls: WakeCallbacks):
    return WakeListener(
        detector=FakeDetector(score),
        vad=FakeVad(voiced),
        aec=NullAec(),
        callbacks=calls,
        far_ref=FarEndRef(),
        threshold=0.5,
        frame_len=320,
        refractory_s=1.5,
        is_idle=lambda: idle,
        is_speaking=lambda: speaking,
        schedule=lambda cb: cb(),
    )


def _frame():
    return np.zeros(320, dtype=np.float32)


def test_wake_hit_when_idle_fires_on_wake():
    fired = []
    calls = WakeCallbacks(
        on_wake=lambda: fired.append("wake"),
        on_speech_end=lambda: None,
        on_barge=lambda: None,
    )
    wl = make(score=0.9, voiced=False, idle=True, speaking=False, calls=calls)
    wl._on_frame(_frame())
    assert fired == ["wake"]


def test_no_wake_when_below_threshold():
    fired = []
    calls = WakeCallbacks(
        on_wake=lambda: fired.append("wake"),
        on_speech_end=lambda: None,
        on_barge=lambda: None,
    )
    wl = make(score=0.2, voiced=False, idle=True, speaking=False, calls=calls)
    wl._on_frame(_frame())
    assert fired == []


def test_speech_during_speaking_fires_barge():
    fired = []
    calls = WakeCallbacks(
        on_wake=lambda: None,
        on_speech_end=lambda: None,
        on_barge=lambda: fired.append("barge"),
    )
    wl = make(score=0.0, voiced=True, idle=False, speaking=True, calls=calls)
    for _ in range(20):  # exceed min_speech_s (15 frames = 300ms)
        wl._on_frame(_frame())
    assert "barge" in fired


def test_refractory_suppresses_second_wake():
    fired = []
    calls = WakeCallbacks(
        on_wake=lambda: fired.append("wake"),
        on_speech_end=lambda: None,
        on_barge=lambda: None,
    )
    wl = make(score=0.9, voiced=False, idle=True, speaking=False, calls=calls)
    wl._on_frame(_frame())
    wl._on_frame(_frame())  # immediately again, inside refractory
    assert fired == ["wake"]


def test_farend_ref_ring():
    ref = FarEndRef(max_samples=16000)
    assert ref.read(320) is None
    pcm = np.ones(640, dtype=np.float32)
    ref.write(pcm)
    chunk1 = ref.read(320)
    assert chunk1 is not None
    assert len(chunk1) == 320
    assert np.all(chunk1 == 1.0)
    chunk2 = ref.read(320)
    assert chunk2 is not None
    assert len(chunk2) == 320
    assert ref.read(320) is None  # drained


def test_detector_create_smoke():
    det = create_detector(model_path=config.WAKE_MODEL, threshold=0.5)
    assert det is not None
    # Feed silent frame
    score = det.score(np.zeros(320, dtype=np.float32))
    assert 0.0 <= score <= 1.0


def test_detector_reset_drops_retained_score():
    """The wrapper returns _last_score for sub-chunk frames (320 < 1280), so a
    retained high score survives any gap in input unless reset() clears it."""
    det = create_detector(model_path=config.WAKE_MODEL, threshold=0.5)
    assert det is not None
    det._last_score = 0.9
    assert det.score(np.zeros(320, dtype=np.float32)) == 0.9  # stale, no new predict
    det.reset()
    assert det.score(np.zeros(320, dtype=np.float32)) == 0.0


def test_stale_score_cannot_refire_wake_after_capture():
    """OQ-29 regression: one real wake must not become an endless loop of 15 s
    empty captures. The detector is not polled while capturing, so on return to
    idle its retained score must NOT be able to fire a second wake."""
    fired = []
    idle = {"v": True}
    calls = WakeCallbacks(
        on_wake=lambda: fired.append("wake"),
        on_speech_end=lambda: None,
        on_barge=lambda: None,
    )
    wl = WakeListener(
        detector=FakeDetector(0.9),
        vad=None,
        aec=NullAec(),
        callbacks=calls,
        far_ref=FarEndRef(),
        threshold=0.5,
        frame_len=320,
        refractory_s=0.0,  # refractory must not be what saves us here
        is_idle=lambda: idle["v"],
        is_speaking=lambda: False,
        schedule=lambda cb: cb(),
    )

    wl._on_frame(_frame())
    assert fired == ["wake"]

    # 15 s of capture: the daemon is not idle, so the detector is never polled.
    idle["v"] = False
    for _ in range(750):
        wl._on_frame(_frame())
    assert fired == ["wake"]

    # Turn finished (empty transcript short-circuits) -> back to idle.
    idle["v"] = True
    wl._awaiting_end = False
    for _ in range(10):
        wl._on_frame(_frame())
    assert fired == ["wake"], f"stale score re-fired the wake: {fired}"


def test_detector_on_cuda_is_rejected(monkeypatch):
    """Invariant #6: wake must run on CPU. If openWakeWord lands the melspec /
    embedding sessions on CUDA, the detector must fail (create_detector then
    disables wake) rather than silently break the invariant."""
    import openwakeword.model as owm
    from friday.audio.wake import OpenWakeWordDetector, create_detector

    class _FakePreproc:
        onnx_execution_provider = "CUDAExecutionProvider"

    class _FakeModel:
        def __init__(self, *a, **k):
            self.preprocessor = _FakePreproc()
            self.models = {"hey_jarvis": object()}

    monkeypatch.setattr(owm, "Model", _FakeModel)

    with pytest.raises(RuntimeError):
        OpenWakeWordDetector(config.WAKE_MODEL)

    # Fail-soft at the factory: wake disabled, not a crash.
    assert create_detector(model_path=config.WAKE_MODEL) is None


def test_self_trigger_suppressed_during_speaking():
    fired = []
    calls = WakeCallbacks(
        on_wake=lambda: fired.append("wake"),
        on_speech_end=lambda: None,
        on_barge=lambda: None,
    )
    # Even if detector gives high score, speaking state suppresses wake trigger
    wl = make(score=0.99, voiced=False, idle=False, speaking=True, calls=calls)
    for _ in range(10):
        wl._on_frame(_frame())
    assert fired == []

