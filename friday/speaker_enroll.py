"""10-utterance speaker enrollment CLI tool (G13, ADR-059).

Collects sample utterances (user decision 2026-08-24: 10), extracts speaker
embeddings on CPU (invariant #6), computes the mean normalized voiceprint, and
saves it to ~/.local/state/friday/voiceprint.npy (mode 0600). Raw audio never
touches disk (invariant #7).

Run with `just enroll` (or `uv run python -m friday.speaker_enroll`).
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from friday import config
from friday.audio.speaker import SpeakerVerifier, save_voiceprint
from friday.audio.vad import SpeechGate, create as create_vad

ENROLLMENT_PHRASES: tuple[str, ...] = (
    "Hey Jarvis, what is the weather today?",
    "Friday, open my browser.",
    "Turn up the volume and play some music.",
    "What time is my next meeting?",
    "Take a note to buy groceries.",
    "Remind me in ten minutes to stretch.",
    "Switch to workspace two.",
    "Search the web for local news.",
    "Close the current window.",
    "Goodnight Friday, see you tomorrow.",
)

_FRAME_LEN = (config.STT_SAMPLE_RATE * config.WAKE_FRAME_MS) // 1000  # 320 @ 16 kHz


def record_utterance(
    phrase: str,
    index: int,
    total: int,
    *,
    max_s: float = 12.0,
) -> np.ndarray:
    """Block until the user speaks `phrase` and falls silent; return the mono
    float32 PCM. Uses a blocking sounddevice stream + VAD end-of-utterance so a
    key press is not needed. Returns an empty array if nothing was captured."""
    import sounddevice as sd

    print(f"\n[{index}/{total}] Please read aloud:")
    print(f'  --> "{phrase}"')
    input("Press ENTER when ready to speak...")

    vad = create_vad(mode=config.VAD_AGGRESSIVENESS, sample_rate=config.STT_SAMPLE_RATE)
    gate = SpeechGate(
        frame_ms=config.WAKE_FRAME_MS,
        end_silence_s=config.VAD_END_SILENCE_S,
        min_speech_s=config.VAD_MIN_SPEECH_S,
    )

    frames: list[np.ndarray] = []
    print("Listening... (speak the phrase)")
    start_t = time.monotonic()

    with sd.InputStream(
        samplerate=config.STT_SAMPLE_RATE,
        channels=1,
        dtype="float32",
        blocksize=_FRAME_LEN,
    ) as stream:
        while time.monotonic() - start_t < max_s:
            data, _overflowed = stream.read(_FRAME_LEN)
            frame = data[:, 0] if data.ndim > 1 else data
            frames.append(frame.copy())
            voiced = vad.is_speech(frame) if vad is not None else True
            if gate.push(voiced) == "end":
                break

    print("Done recording phrase.")
    if not frames:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(frames).astype(np.float32)


def run_enrollment(num_utterances: int = config.SPEAKER_ENROLL_UTTERANCES) -> int:
    print("=" * 60)
    print("  Friday Voiceprint Enrollment (10-Utterance Profiler)")
    print("=" * 60)
    print(f"Model: {config.SPEAKER_MODEL}")
    print(f"Target Voiceprint: {config.VOICEPRINT_FILE}")

    if not config.SPEAKER_MODEL.exists():
        print(f"Error: Speaker model missing at {config.SPEAKER_MODEL}")
        return 1

    verifier = SpeakerVerifier(config.SPEAKER_MODEL)

    embeddings: list[np.ndarray] = []
    count = min(num_utterances, len(ENROLLMENT_PHRASES))
    for i in range(count):
        phrase = ENROLLMENT_PHRASES[i]
        audio = record_utterance(phrase, i + 1, count)
        if len(audio) < 8000:  # less than 0.5 s of speech
            print("Warning: Utterance too short, skipping.")
            continue
        emb = verifier.compute_embedding(audio)
        embeddings.append(emb)
        print(f"Captured sample {len(embeddings)}/{count}.")

    if len(embeddings) < 3:
        print("Error: Not enough valid samples captured.")
        return 1

    voiceprint = verifier.enroll(embeddings)
    save_voiceprint(config.VOICEPRINT_FILE, voiceprint)
    print("\n" + "=" * 60)
    print(f"SUCCESS: Voiceprint enrolled from {len(embeddings)} samples.")
    print(f"Saved to: {config.VOICEPRINT_FILE} (mode 0600)")
    print("=" * 60)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Friday speaker verification voice enrollment")
    parser.add_argument(
        "--samples",
        type=int,
        default=config.SPEAKER_ENROLL_UTTERANCES,
        help="Number of enrollment samples (default: 10)",
    )
    args = parser.parse_args()
    return run_enrollment(num_utterances=args.samples)


if __name__ == "__main__":
    raise SystemExit(main())
