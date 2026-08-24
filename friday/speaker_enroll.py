"""10-utterance speaker enrollment CLI tool (G13, ADR-059).

Collects 10 sample utterances (user decision 2026-08-24), extracts speaker embeddings
on CPU, computes the mean normalized voiceprint, and saves it to ~/.local/state/friday/voiceprint.npy.
"""

from __future__ import annotations

import argparse
import sys
import time

import numpy as np

from friday import config
from friday.audio.recorder import Recorder
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


def record_utterance(recorder: Recorder, phrase: str, index: int, total: int) -> np.ndarray:
    print(f"\n[{index}/{total}] Please read aloud:")
    print(f"  --> \"{phrase}\"")
    input("Press ENTER when ready to speak...")

    gate = SpeechGate(
        vad=create_vad(mode=config.VAD_AGGRESSIVENESS),
        frame_len=(16000 * config.WAKE_FRAME_MS) // 1000,
        end_silence_s=config.VAD_END_SILENCE_S,
        min_speech_s=config.VAD_MIN_SPEECH_S,
    )

    frames: list[np.ndarray] = []
    print("Listening... (speak the phrase)")
    start_t = time.monotonic()

    recorder.reset()
    while time.monotonic() - start_t < 10.0:
        chunk = recorder.read()
        if len(chunk) == 0:
            time.sleep(0.01)
            continue

        frames.append(chunk)
        # Check VAD end-of-speech
        flen = gate._frame_len
        if len(chunk) >= flen:
            event = gate.push(chunk[:flen])
            if event == "end" and len(frames) > 5:
                break

    print("Done recording phrase.")
    if not frames:
        return np.zeros(16000, dtype=np.float32)
    return np.concatenate(frames)


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
    recorder = Recorder()
    if not recorder.open():
        print("Error: Could not open audio input device.")
        return 1

    embeddings: list[np.ndarray] = []
    try:
        count = min(num_utterances, len(ENROLLMENT_PHRASES))
        for i in range(count):
            phrase = ENROLLMENT_PHRASES[i]
            audio = record_utterance(recorder, phrase, i + 1, count)
            if len(audio) < 8000:  # less than 0.5s
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
        print(f"SUCCESS: Voiceprint enrolled successfully from {len(embeddings)} samples.")
        print(f"Saved to: {config.VOICEPRINT_FILE} (mode 0600)")
        print("=" * 60)
        return 0
    finally:
        recorder.close()


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
