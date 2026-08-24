import numpy as np
from friday.audio.aec import NullAec, create, AecProcessor


def test_nullaec_is_passthrough():
    near = np.random.randn(160).astype(np.float32)
    out = NullAec().process(near, None)
    assert np.array_equal(out, near)


def test_create_falls_soft_to_nullaec_when_disabled():
    aec = create(enabled=False, sample_rate=16000, frame_ms=10)
    near = np.zeros(160, dtype=np.float32)
    assert isinstance(aec, NullAec)
    assert np.array_equal(aec.process(near, near), near)


def test_process_returns_near_when_far_is_none():
    aec = create(enabled=True, sample_rate=16000, frame_ms=10)
    near = np.random.randn(160).astype(np.float32)
    assert np.array_equal(aec.process(near, None), near)


def test_real_aec_processes_audio_frames():
    aec = create(enabled=True, sample_rate=16000, frame_ms=10)
    near = np.random.randn(320).astype(np.float32) * 0.1
    far = np.random.randn(320).astype(np.float32) * 0.1
    out = aec.process(near, far)
    assert out.shape == near.shape
    assert out.dtype == np.float32
