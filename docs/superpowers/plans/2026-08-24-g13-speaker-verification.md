# G13 — Speaker Verification Implementation Plan

**Goal:** Provide speaker voiceprint verification gating wake-word activation and enabling two-pass confirmation for dangerous operations, running entirely on CPU (invariant #6).

**Spec:** `docs/superpowers/specs/2026-08-24-phase2-design.md` (§5 G13; ADR-059).

## Constraints
- **#6 CPU only:** Model runs via ONNX / sherpa-onnx (0 torch, 0 CUDA).
- **#7 No raw audio on disk:** Voiceprint stores only 512-float embedding vector in `voiceprint.npy` (0600 mode).
- **User decision (2026-08-24):** 10 sample utterances for enrollment.

---

## Tasks

### Task 1: Speaker Embedding Extractor & Verifier (`friday/audio/speaker.py`, `tests/test_speaker.py`)
- `SpeakerVerifier`:
  - `compute_embedding(pcm: np.ndarray) -> np.ndarray`
  - `verify(pcm: np.ndarray, threshold: float) -> tuple[bool, float]`
  - `save_voiceprint(path: Path, vector: np.ndarray)` (0600 mode, 0700 dir)
  - `load_voiceprint(path: Path) -> np.ndarray | None`
- Unit tests with synthetic/real vectors asserting cosine distance, enrollment averaging, and threshold gating.

### Task 2: 10-Utterance Enrollment Tool (`friday/speaker_enroll.py`)
- CLI interactive enrollment runner collecting 10 distinct utterances.
- Computes mean L2-normalized embedding and saves to `~/.local/state/friday/voiceprint.npy`.

### Task 3: Integration with Wake Detection & Turn FSM (`friday/daemon.py`, `friday/audio/wake.py`)
- When speaker verification is enabled, gate wake-initiated capture on speaker verification score.
- Two-pass dangerous action confirmation requiring spoken affirmative + voiceprint match.

### Task 4: Full Suite & Eval Verification
- Run `pytest`, `just eval`, `just selftest`.
