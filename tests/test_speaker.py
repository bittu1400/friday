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


def test_verify_accepts_the_owner_and_rejects_an_impostor(monkeypatch):
    """M5: `verify()` is the whole G13 accept/reject decision and was called by
    no test in the repository — `grep -rn "\\.verify(" tests/` returned nothing.
    The old `test_speaker_verifier_mock` built a SpeakerVerifier, never used it,
    and asserted `cosine_similarity()` that the test above already covers, so
    `return score >= th, score` could become `return True, score` (every
    impostor accepted) or `return score < th, score` (the owner locked out)
    with the suite green.

    Deterministic vectors, no RNG: the embedding extractor is the part that
    needs a model, and it is exactly the part this decision does not live in.
    """
    ref = np.zeros(512, dtype=np.float32)
    ref[0] = 1.0
    other = np.zeros(512, dtype=np.float32)
    other[1] = 1.0

    verifier = SpeakerVerifier(model_path=None, voiceprint=ref)
    pcm = np.zeros(16000, dtype=np.float32)

    def _next_embedding(vec):
        monkeypatch.setattr(
            SpeakerVerifier,
            "compute_embedding",
            lambda self, pcm, sample_rate=16000: vec,
        )

    # The owner: same speaker, small perturbation. cos ~= 0.995, threshold 0.75.
    same = ref + 0.1 * other
    same /= np.linalg.norm(same)
    _next_embedding(same)
    ok, score = verifier.verify(pcm)
    assert ok is True
    assert score > 0.9

    # An impostor: orthogonal embedding, cos == 0.0.
    _next_embedding(other)
    ok, score = verifier.verify(pcm)
    assert ok is False
    assert score < 0.5


def test_verify_fails_open_with_no_voiceprint(monkeypatch):
    # Documented behaviour, not an accident: speaker verification is OFF by
    # default and fails OPEN when nobody has enrolled (CLAUDE.md). Pinned so a
    # future change to `verify()` cannot silently turn it into a lockout.
    verifier = SpeakerVerifier(model_path=None, voiceprint=None)
    verifier._voiceprint = None  # no enrolment, and none on disk
    ok, score = verifier.verify(np.zeros(16000, dtype=np.float32))
    assert ok is True
    assert score == 1.0


def test_enrollment_averaging():
    verifier = SpeakerVerifier()
    # 10 sample utterances
    embs = [np.random.randn(512).astype(np.float32) for _ in range(10)]
    enrolled = verifier.enroll(embs)

    assert enrolled.shape == (512,)
    assert pytest.approx(np.linalg.norm(enrolled), 0.001) == 1.0
