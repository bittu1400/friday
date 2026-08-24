"""Speaker verification & voiceprint enrollment (G13, ADR-059).

Uses sherpa-onnx 3D-Speaker/CAM++ on CPU (invariant #6) to extract 512-dim
speaker embeddings and verify speaker identity with cosine similarity.
No raw audio is written to disk (invariant #7).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Sequence

import numpy as np

from friday import config

log = logging.getLogger(__name__)


def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    """Compute cosine similarity between two 1D vectors."""
    n1 = float(np.linalg.norm(v1))
    n2 = float(np.linalg.norm(v2))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return float(np.dot(v1, v2) / (n1 * n2))


def save_voiceprint(path: Path, vector: np.ndarray) -> None:
    """Save enrolled voiceprint vector to disk with strict permissions (0600 file, 0700 dir)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except Exception:
        pass

    np.save(str(path), vector.astype(np.float32))
    try:
        path.chmod(0o600)
    except Exception:
        pass


def load_voiceprint(path: Path) -> np.ndarray | None:
    """Load enrolled voiceprint vector from disk fail-soft."""
    if not path.exists():
        return None
    try:
        arr = np.load(str(path))
        if arr.ndim == 1:
            return arr.astype(np.float32)
        return arr.flatten().astype(np.float32)
    except Exception as exc:
        log.warning("Failed to load voiceprint from %s: %s", path, exc)
        return None


class SpeakerVerifier:
    """Speaker verification engine using sherpa-onnx embedding extractor on CPU."""

    def __init__(
        self,
        model_path: Path | str | None = None,
        voiceprint: np.ndarray | None = None,
        threshold: float = config.SPEAKER_SIMILARITY_THRESHOLD,
    ) -> None:
        self._model_path = Path(model_path) if model_path else config.SPEAKER_MODEL
        self._voiceprint = voiceprint
        self._threshold = threshold
        self._extractor = None

        if self._voiceprint is None and config.VOICEPRINT_FILE.exists():
            self._voiceprint = load_voiceprint(config.VOICEPRINT_FILE)

    def _get_extractor(self):
        if self._extractor is None:
            if not self._model_path.exists():
                raise FileNotFoundError(f"Speaker model not found at {self._model_path}")
            import sherpa_onnx

            cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=str(self._model_path),
                num_threads=2,
                provider="cpu",
                debug=False,
            )
            self._extractor = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)
        return self._extractor

    def compute_embedding(self, pcm: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
        """Extract a 512-dim normalized speaker embedding from 16kHz float32 PCM."""
        extractor = self._get_extractor()
        stream = extractor.create_stream()
        audio_flat = pcm.flatten().astype(np.float32)
        stream.accept_waveform(sample_rate=sample_rate, waveform=audio_flat)
        stream.input_finished()
        raw_emb = np.array(extractor.compute(stream), dtype=np.float32)
        norm = np.linalg.norm(raw_emb)
        if norm > 0:
            raw_emb = raw_emb / norm
        return raw_emb

    def verify(
        self,
        pcm: np.ndarray,
        sample_rate: int = 16000,
        threshold: float | None = None,
    ) -> tuple[bool, float]:
        """Verify input audio against enrolled voiceprint. Returns (is_match, score)."""
        if self._voiceprint is None:
            # No voiceprint enrolled: fail-open or log warning
            return True, 1.0

        th = threshold if threshold is not None else self._threshold
        emb = self.compute_embedding(pcm, sample_rate=sample_rate)
        score = cosine_similarity(self._voiceprint, emb)
        return score >= th, score

    def enroll(self, embeddings: Sequence[np.ndarray]) -> np.ndarray:
        """Compute mean normalized voiceprint from a collection of sample embeddings."""
        if not embeddings:
            raise ValueError("No embeddings provided for enrollment")
        stack = np.stack(embeddings, axis=0)
        mean_vec = np.mean(stack, axis=0)
        norm = np.linalg.norm(mean_vec)
        if norm > 0:
            mean_vec = mean_vec / norm
        self._voiceprint = mean_vec.astype(np.float32)
        return self._voiceprint
