"""Wake-word and VAD benchmark harness (G10, RAM-only).

Measures live wake detection, AEC performance, VAD events, and execution latency.
No audio is written to disk (invariant #7).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from friday import config
from friday.audio import aec, vad, wake


class _Probe:
    """Wraps the detector to record peak input level and the highest score seen.

    Without these two numbers a dead microphone and a genuinely quiet room both
    print "Wake Hits: 0", and a zero that cannot distinguish them is not
    evidence of anything.
    """

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.max_score = 0.0
        self.peak = 0.0

    def score(self, frame: np.ndarray) -> float:
        if frame.size:
            self.peak = max(self.peak, float(np.abs(frame).max()))
        s = self._inner.score(frame)
        self.max_score = max(self.max_score, s)
        return s

def run_benchmark(duration_s: float = 10.0, threshold: float = 0.5) -> None:
    print(f"=== Friday Wake-Word & VAD Benchmark ({duration_s}s) ===")
    print(f"Model: {config.WAKE_MODEL}")
    print(f"Threshold: {threshold} | AEC: {config.AEC_ENABLED} | VAD Mode: {config.VAD_AGGRESSIVENESS}")
    print("Listening... (Say 'hey jarvis' or speak to test)")

    far_ref = wake.FarEndRef()
    aec_proc = aec.create(enabled=config.AEC_ENABLED, sample_rate=16000, frame_ms=config.AEC_FRAME_MS)
    vad_det = vad.create(mode=config.VAD_AGGRESSIVENESS, sample_rate=16000)
    wake_det = wake.create_detector(config.WAKE_MODEL)
    probe = _Probe(wake_det) if wake_det is not None else None

    events: list[tuple[float, str]] = []

    def _on_wake() -> None:
        t = time.monotonic()
        events.append((t, "WAKE"))
        print(f"[{t - start_time:.2f}s] >>> WAKE WORD DETECTED (hey jarvis) <<<")

    def _on_speech_end() -> None:
        t = time.monotonic()
        events.append((t, "SPEECH_END"))
        print(f"[{t - start_time:.2f}s] --- Speech End (VAD) ---")

    def _on_barge() -> None:
        t = time.monotonic()
        events.append((t, "BARGE_IN"))
        print(f"[{t - start_time:.2f}s] !!! Barge-in Detected !!!")

    callbacks = wake.WakeCallbacks(
        on_wake=_on_wake,
        on_speech_end=_on_speech_end,
        on_barge=_on_barge,
    )

    listener = wake.WakeListener(
        detector=probe,
        vad=vad_det,
        aec=aec_proc,
        callbacks=callbacks,
        far_ref=far_ref,
        threshold=threshold,
        frame_len=(16000 * config.WAKE_FRAME_MS) // 1000,
        refractory_s=config.WAKE_REFRACTORY_S,
        is_idle=lambda: True,
        is_speaking=lambda: False,
    )

    start_time = time.monotonic()
    if not listener.start():
        print("Error: Could not open audio input stream.")
        return

    try:
        while time.monotonic() - start_time < duration_s:
            time.sleep(0.1)
    finally:
        listener.stop()

    print("\n=== Benchmark Summary ===")
    print(f"Total Duration: {duration_s:.1f}s")
    wake_count = sum(1 for _, ev in events if ev == "WAKE")
    speech_end_count = sum(1 for _, ev in events if ev == "SPEECH_END")
    barge_count = sum(1 for _, ev in events if ev == "BARGE_IN")
    print(f"Wake Hits: {wake_count}")
    print(f"Speech End Triggers: {speech_end_count}")
    print(f"Barge-In Triggers: {barge_count}")
    if probe is not None:
        print(f"Peak input level: {probe.peak:.4f}")
        print(f"Max wake score:   {probe.max_score:.3f}  (threshold {threshold})")
        if probe.peak == 0.0:
            print("VERDICT: microphone delivered pure zeros - this run proves NOTHING.")
        elif wake_count == 0 and probe.max_score < 0.05:
            print("VERDICT: mic live, wake word never came close. Clean silence run.")
        elif wake_count == 0:
            print("VERDICT: mic live, wake word approached but did not cross threshold.")
    print("=========================")


def main() -> int:
    parser = argparse.ArgumentParser(description="Friday wake-word benchmark")
    parser.add_argument("--duration", type=float, default=5.0, help="Duration in seconds")
    parser.add_argument("--threshold", type=float, default=config.WAKE_THRESHOLD, help="Wake threshold")
    args = parser.parse_args()

    run_benchmark(duration_s=args.duration, threshold=args.threshold)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
