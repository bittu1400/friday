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


class StreamingFakeDetector:
    """Mirrors OpenWakeWordDetector's streaming contract: it needs `chunk`
    samples before it can produce a NEW score, and returns the previous one
    until then. `scores` supplies one value per completed chunk. This is the
    behaviour the constant-score FakeDetector cannot express — and the reason
    the OQ-29 loop was invisible to the original wake tests.
    """

    def __init__(self, scores: list[float], chunk: int = 1280):
        self._scores = list(scores)
        self._chunk = chunk
        self._buffered = 0
        self._last = 0.0

    def score(self, frame: np.ndarray) -> float:
        self._buffered += len(frame)
        while self._buffered >= self._chunk:
            self._buffered -= self._chunk
            self._last = self._scores.pop(0) if self._scores else 0.0
        return self._last


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


def _speak_over(monkeypatch, enabled: bool):
    monkeypatch.setattr(config, "BARGE_VAD_ENABLED", enabled)
    fired = []
    calls = WakeCallbacks(
        on_wake=lambda: None,
        on_speech_end=lambda: None,
        on_barge=lambda: fired.append("barge"),
    )
    wl = make(score=0.0, voiced=True, idle=False, speaking=True, calls=calls)
    for _ in range(20):  # exceed min_speech_s (15 frames = 300ms)
        wl._on_frame(_frame())
    return fired


def test_speech_during_speaking_fires_barge(monkeypatch):
    assert "barge" in _speak_over(monkeypatch, True)


def test_voice_barge_is_off_by_default(monkeypatch):
    """ADR-064: the AEC yields only ~-5 to -15 dB on this machine's real
    acoustic path, so speech detected during playback is usually Friday's own
    voice. Until a better canceller is chosen, voice barge-in stays off and PTT
    is the interrupt."""
    assert config.BARGE_VAD_ENABLED is False, "voice barge-in must default off"
    assert _speak_over(monkeypatch, False) == []


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
    det = create_detector(model_path=config.WAKE_MODEL)
    assert det is not None
    # Feed silent frame
    score = det.score(np.zeros(320, dtype=np.float32))
    assert 0.0 <= score <= 1.0


def test_stale_score_cannot_refire_wake_after_capture():
    """OQ-29 regression: one real wake must not become an endless loop of 15 s
    empty captures.

    The detector is a streaming model. If it is polled only while idle it is
    starved for the whole capture, and because one frame (320) is smaller than
    a prediction chunk (1280) the first frame afterwards returns the very score
    that started the capture — firing the wake again immediately, forever.
    """
    fired = []
    idle = {"v": True}
    calls = WakeCallbacks(
        on_wake=lambda: fired.append("wake"),
        on_speech_end=lambda: None,
        on_barge=lambda: None,
    )
    # One chunk of wake word, then nothing but silence for the rest of the run.
    det = StreamingFakeDetector([0.9] + [0.0] * 5000)
    wl = WakeListener(
        detector=det,
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

    for _ in range(4):  # 4 x 320 = one 1280-sample chunk
        wl._on_frame(_frame())
    assert fired == ["wake"]

    # 15 s of capture: the daemon is not idle. The detector must still be fed,
    # or its last score stays 0.9 for the whole capture.
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



def test_silent_capture_is_abandoned_early(monkeypatch):
    """ADR-066: a false wake starts a capture nobody speaks into. The
    end-of-speech timer can only arm AFTER speech, so such a capture ran to the
    15 s FR-4 cap with Friday deaf the whole time (FR-5). Measured live
    2026-08-25: three in one 3-minute session, two of them the full cap."""
    ended = []
    calls = WakeCallbacks(
        on_wake=lambda: None,
        on_speech_end=lambda: ended.append("end"),
        on_barge=lambda: None,
    )
    wl = make(score=0.0, voiced=False, idle=False, speaking=False, calls=calls)
    wl._arm()

    quiet = int(config.VAD_NO_SPEECH_TIMEOUT_S * 1000 / wl.frame_ms)
    for _ in range(quiet - 1):
        wl._on_frame(_frame())
    assert ended == [], "must not give up before the timeout"

    wl._on_frame(_frame())
    assert ended == ["end"], "a capture with no speech at all must be abandoned"

    # and it must be far cheaper than the 15 s cap it replaces
    assert quiet * wl.frame_ms / 1000 < config.MAX_CAPTURE_S


def test_capture_with_speech_is_not_abandoned(monkeypatch):
    """The bail-out must never cut off someone who is actually talking."""
    ended = []
    calls = WakeCallbacks(
        on_wake=lambda: None,
        on_speech_end=lambda: ended.append("end"),
        on_barge=lambda: None,
    )
    wl = make(score=0.0, voiced=True, idle=False, speaking=False, calls=calls)
    wl._arm()
    for _ in range(int(config.VAD_NO_SPEECH_TIMEOUT_S * 1000 / wl.frame_ms) + 50):
        wl._on_frame(_frame())
    assert ended == [], "continuous speech must not trigger the no-speech bail-out"
