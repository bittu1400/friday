import numpy as np
import pytest
from pathlib import Path
from friday.audio.speaker import (
    SpeakerVerifier,
    cosine_similarity,
    save_voiceprint,
    load_voiceprint,
)


def test_cosine_similarity():
    v1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    v2 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    v3 = np.array([0.0, 1.0, 0.0], dtype=np.float32)

    assert pytest.approx(cosine_similarity(v1, v2), 0.001) == 1.0
    assert pytest.approx(cosine_similarity(v1, v3), 0.001) == 0.0


def test_save_and_load_voiceprint(tmp_path: Path):
    target = tmp_path / "voiceprint.npy"
    vec = np.random.randn(512).astype(np.float32)

    save_voiceprint(target, vec)
    loaded = load_voiceprint(target)

    assert loaded is not None
    assert loaded.shape == (512,)
    assert np.allclose(vec, loaded)


def test_speaker_verifier_mock():
    ref = np.random.randn(512).astype(np.float32)
    ref /= np.linalg.norm(ref)

    verifier = SpeakerVerifier(model_path=None, voiceprint=ref)

    # Synthetic same speaker embedding (small normalized perturbation)
    noise = np.random.randn(512).astype(np.float32)
    noise /= np.linalg.norm(noise)
    same = ref + noise * 0.1
    same /= np.linalg.norm(same)
    score_same = cosine_similarity(ref, same)
    assert score_same > 0.9

    # Synthetic impostor embedding
    diff = np.random.randn(512).astype(np.float32)
    diff /= np.linalg.norm(diff)
    score_diff = cosine_similarity(ref, diff)
    assert score_diff < 0.5


def test_enrollment_averaging():
    verifier = SpeakerVerifier()
    # 10 sample utterances
    embs = [np.random.randn(512).astype(np.float32) for _ in range(10)]
    enrolled = verifier.enroll(embs)

    assert enrolled.shape == (512,)
    assert pytest.approx(np.linalg.norm(enrolled), 0.001) == 1.0
