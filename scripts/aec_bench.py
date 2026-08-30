"""AEC drill (OQ-32) — is WebRTC APM still the right echo canceller?

WHAT THIS IS. Friday's speaker plays her reply; her own microphone hears it.
An echo canceller is given two signals -- `near` (what the mic heard) and `far`
(what was sent to the speaker) -- and subtracts the second from the first, so
that what is left is only the room. Without it, Friday's VAD hears Friday, calls
it a user interruption, and cuts her own sentence off.

WHY IT MATTERS HERE. `docs/aec-probe.md` measured the incumbent at **-52 dB on
synthetic echo and -5 to -10 dB in this actual room**. At -6 dB Friday still
hears herself at half volume, which is why ADR-064 turned voice barge-in OFF and
made PTT the only interrupt. The cause is not delay: speaker-to-mic lag measured
58 ms with envelope correlation 0.53, so the reference content is right. WebRTC's
adaptive filter assumes a roughly LINEAR echo path, and a laptop speaker at
volume is not linear -- it distorts and the enclosure resonates.

DTLN-aec was trained on exactly that (Microsoft AEC-Challenge, 3rd place) and
costs 0.448 ms per 8 ms hop on this CPU -- 5.6% of one core.

    A candidate is only interesting at roughly -30 dB or better with ZERO
    barge events. Below that the VAD still hears Friday.

HOW TO RUN IT. The friday service must be stopped or two daemons fight over the
microphone:

    systemctl --user stop friday
    ~/.cache/friday-accel-eval/venv/bin/python scripts/aec_bench.py

It plays a rendered Kokoro reply through the speakers and records the microphone
at the same time, three times -- once with no cancellation, once with the
incumbent, once with DTLN-aec. Nobody needs to speak; silence during playback is
the whole point. Speak only if you want to check the canceller does not eat you
too (`--talk`).

Audio is held in RAM and never written to disk (invariant #7).
"""
from __future__ import annotations

import argparse
import queue
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SR = 16000
BLOCK_LEN = 512      # DTLN-aec window
BLOCK_SHIFT = 128    # 8 ms hop
DTLN = Path.home() / ".cache/friday-accel-eval/dtln-aec"
SILERO = (Path.home() / ".cache/friday-accel-eval/venv/lib/python3.12"
          / "site-packages/silero_vad/data/silero_vad_op18_ifless.onnx")
REPLY = (Path.home() / ".cache/friday-accel-eval/tts-samples"
         / "kokoro_af_bella_para.wav")


class DtlnAec:
    """DTLN-aec as an `friday.audio.aec.AecProcessor`.

    Two stages: stage 1 masks the microphone magnitude spectrum using the
    loopback spectrum; stage 2 cleans the resulting time-domain block using the
    loopback block. LSTM state is carried between hops, so frames MUST be fed in
    order and a reset is a real reset.
    """

    def __init__(self, size: str = "512", device: str = "CPU") -> None:
        import openvino as ov

        core = ov.Core()
        self.m1 = core.compile_model(str(DTLN / f"dtln_aec_{size}_1.tflite"), device)
        self.m2 = core.compile_model(str(DTLN / f"dtln_aec_{size}_2.tflite"), device)
        self.r1, self.r2 = self.m1.create_infer_request(), self.m2.create_infer_request()
        # declared order is (signal, states, loopback) for both stages
        self.i1 = list(self.m1.inputs)
        self.i2 = list(self.m2.inputs)
        self.s1 = np.zeros(list(self.i1[1].get_shape()), dtype=np.float32)
        self.s2 = np.zeros(list(self.i2[1].get_shape()), dtype=np.float32)
        self.reset()

    def reset(self) -> None:
        self.buf = np.zeros(BLOCK_LEN, dtype=np.float32)
        self.buf_lpb = np.zeros(BLOCK_LEN, dtype=np.float32)
        self.out = np.zeros(BLOCK_LEN, dtype=np.float32)
        self.s1[...] = 0.0
        self.s2[...] = 0.0

    def _hop(self, near: np.ndarray, far: np.ndarray) -> np.ndarray:
        self.buf[:-BLOCK_SHIFT] = self.buf[BLOCK_SHIFT:]
        self.buf[-BLOCK_SHIFT:] = near
        self.buf_lpb[:-BLOCK_SHIFT] = self.buf_lpb[BLOCK_SHIFT:]
        self.buf_lpb[-BLOCK_SHIFT:] = far

        fft = np.fft.rfft(self.buf)
        in_mag = np.abs(fft).reshape(1, 1, -1).astype(np.float32)
        lpb_mag = np.abs(np.fft.rfft(self.buf_lpb)).reshape(1, 1, -1).astype(np.float32)

        o1 = self.r1.infer({self.i1[0]: in_mag, self.i1[1]: self.s1,
                            self.i1[2]: lpb_mag})
        mask, self.s1 = o1[self.m1.outputs[0]], o1[self.m1.outputs[1]]
        est = np.fft.irfft(fft * mask.reshape(-1)).astype(np.float32)

        o2 = self.r2.infer({self.i2[0]: est.reshape(1, 1, -1), self.i2[1]: self.s2,
                            self.i2[2]: self.buf_lpb.reshape(1, 1, -1)})
        blk, self.s2 = o2[self.m2.outputs[0]], o2[self.m2.outputs[1]]

        self.out[:-BLOCK_SHIFT] = self.out[BLOCK_SHIFT:]
        self.out[-BLOCK_SHIFT:] = 0.0
        self.out += blk.reshape(-1)
        return self.out[:BLOCK_SHIFT].copy()

    def process(self, near: np.ndarray, far: np.ndarray | None) -> np.ndarray:
        if far is None:
            far = np.zeros_like(near)
        n = min(len(near), len(far)) // BLOCK_SHIFT * BLOCK_SHIFT
        return np.concatenate([self._hop(near[i:i + BLOCK_SHIFT], far[i:i + BLOCK_SHIFT])
                               for i in range(0, n, BLOCK_SHIFT)]) if n else near


def silero_speech_frames(x: np.ndarray, thr: float = 0.5) -> int:
    """How many 32 ms frames a VAD would call speech. This is the number that
    decides whether Friday interrupts herself; dB alone does not."""
    import onnxruntime as ort

    s = ort.InferenceSession(str(SILERO), providers=["CPUExecutionProvider"])
    state = np.zeros((2, 1, 128), dtype=np.float32)
    ctx = np.zeros((1, 64), dtype=np.float32)
    n = 0
    for i in range(0, len(x) - 512, 512):
        f = np.concatenate([ctx, x[i:i + 512].reshape(1, -1)], axis=1).astype(np.float32)
        ctx = f[:, -64:]
        out, state = s.run(None, {"input": f, "state": state,
                                  "sr": np.array(SR, dtype=np.int64)})
        n += float(out[0][0]) >= thr
    return n


def play_and_record(reply: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Play the reply and capture the mic simultaneously, returning
    (mic, far_reference) aligned sample-for-sample."""
    import sounddevice as sd

    mic_q: queue.Queue = queue.Queue()
    played = np.zeros(len(reply) + SR, dtype=np.float32)
    pos = {"i": 0}

    xruns: list[str] = []

    def out_cb(outdata, frames, t, status):
        if status:
            xruns.append(f"out:{status}")
        i = pos["i"]
        chunk = reply[i:i + frames]
        if len(chunk) < frames:
            chunk = np.concatenate([chunk, np.zeros(frames - len(chunk), np.float32)])
        outdata[:, 0] = chunk
        played[i:i + frames] = chunk
        pos["i"] = i + frames

    def in_cb(indata, frames, t, status):
        # Ignoring this is how a corrupted capture passes for a real one: a
        # dropped input block shifts everything after it, so the reference no
        # longer lines up for the rest of the signal and BOTH cancellers score
        # badly on the same capture. That is the bimodal result set.
        if status:
            xruns.append(f"in:{status}")
        mic_q.put(indata[:, 0].copy())

    with sd.OutputStream(samplerate=SR, channels=1, dtype="float32",
                         blocksize=BLOCK_SHIFT, callback=out_cb), \
         sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                        blocksize=BLOCK_SHIFT, callback=in_cb):
        while pos["i"] < len(reply):
            time.sleep(0.05)
        time.sleep(0.3)
    mic = np.concatenate(list(mic_q.queue)) if not mic_q.empty() else np.zeros(1, np.float32)
    n = min(len(mic), len(reply))
    return mic[:n], played[:n], xruns


def estimate_delay(mic: np.ndarray, far: np.ndarray, max_ms: int = 400) -> int:
    """Samples of lag from `far` to `mic`, by GCC-PHAT at SAMPLE resolution.

    This has to be exact. The sweep in `--sweep` shows 20 ms of error costs
    17 dB, so an estimator working on 10 ms envelope hops -- which is what this
    used to be -- lands inside the error band by construction. That produced a
    bimodal result set (DTLN quiet frames 5..248) which looked like canceller
    instability and was actually estimator quantisation: the bad captures were
    bad for BOTH processors at once, which no quality difference can cause.

    GCC-PHAT whitens the cross-spectrum before the inverse transform, so the
    peak is set by phase alignment rather than by whichever band happens to
    carry the most energy. It is the standard estimator for exactly this.
    """
    n = min(len(mic), len(far))
    if n < SR // 10:
        return 0
    size = 1 << int(np.ceil(np.log2(2 * n)))
    M = np.fft.rfft(mic[:n], size)
    F = np.fft.rfft(far[:n], size)
    cross = M * np.conj(F)
    cross /= np.maximum(np.abs(cross), 1e-12)      # PHAT weighting
    corr = np.fft.irfft(cross, size)
    limit = int(max_ms * SR / 1000)
    return int(np.argmax(corr[:limit]))


def db(out: np.ndarray, mic: np.ndarray) -> float:
    """Suppression, in `docs/aec-probe.md`'s convention: NEGATIVE is good.
    -30 dB means the echo came out about 32x quieter than it went in."""
    ro = float(np.sqrt(np.mean(out ** 2)))
    rm = float(np.sqrt(np.mean(mic ** 2)))
    return 20 * np.log10(max(ro, 1e-9) / max(rm, 1e-9))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="512", choices=("128", "256", "512"))
    ap.add_argument("--device", default="CPU")
    ap.add_argument("--drift", action="store_true",
                    help="estimate the reference lag per 2 s window, to see "
                         "whether the playback and capture clocks diverge")
    ap.add_argument("--sweep", action="store_true",
                    help="capture once, then score DTLN at many reference lags. "
                         "Alignment is not something to guess at: a canceller "
                         "fed a misaligned reference measures as a broken one.")
    ap.add_argument("--yes", action="store_true",
                    help="skip the ENTER prompt (non-interactive shells)")
    ap.add_argument("--talk", action="store_true",
                    help="say something over the playback, to check the canceller "
                         "does not eat the user as well as the echo")
    a = ap.parse_args()

    import wave
    with wave.open(str(REPLY)) as w:
        raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        reply = (raw.astype(np.float32) / 32768.0)
        if w.getframerate() != SR:  # kokoro is 24 kHz; resample to the mic rate
            idx = np.linspace(0, len(reply) - 1, int(len(reply) * SR / w.getframerate()))
            reply = np.interp(idx, np.arange(len(reply)), reply).astype(np.float32)

    print(f"reply {len(reply)/SR:.1f}s @ {SR} Hz   dtln={a.size} on {a.device}")
    if a.talk:
        print("SPEAK over the playback when it starts.")
    if a.yes:
        for i in (3, 2, 1):
            print(f"  starting in {i}...", flush=True)
            time.sleep(1)
    else:
        input("press ENTER, keep the room quiet, then do not touch the laptop... ")

    mic, far, xruns = play_and_record(reply)
    far_raw = far.copy()
    if xruns:
        print(f"  {len(xruns)} audio callback problem(s): {sorted(set(xruns))}")
        print("  the capture is not trustworthy — discarding it")
        return 3
    lag = estimate_delay(mic, far)
    if lag:
        far = np.concatenate([np.zeros(lag, np.float32), far])[:len(mic)]
    print(f"captured {len(mic)/SR:.1f}s   mic RMS {np.sqrt(np.mean(mic**2)):.5f}"
          f"   speaker->mic lag {lag/SR*1000:.0f} ms (aligned)")
    if np.sqrt(np.mean(mic ** 2)) < 1e-4:
        print("  mic is silent — check the input device before trusting anything")
        return 1

    from friday.audio import aec as fr_aec
    incumbent = fr_aec.create(enabled=True)
    if isinstance(incumbent, fr_aec.NullAec):
        # `aec.create()` falls back to NullAec on ImportError and only logs it.
        # A "WebRTC" row that is silently a passthrough reads as +0.0 dB and
        # looks like a real measurement of a useless canceller. It is not a
        # measurement at all.
        print("\n  pywebrtc_audio is not importable in THIS interpreter, so the "
              "incumbent\n  would be measured as a passthrough. Refusing to "
              "print a fake row.\n  Install it into this venv and re-run.")
        return 2
    if a.drift:
        # A single fixed lag can only align two streams that share a clock.
        # The DAC and the ADC here are separate domains, so estimate the lag
        # independently in each window and see whether it moves.
        print(f"\n{'window':>10s} {'lag':>8s}")
        win = 2 * SR
        for i in range(0, len(mic) - win, win):
            L = estimate_delay(mic[i:i + win], far_raw[i:i + win])
            print(f"{i/SR:>7.0f}-{(i+win)/SR:<3.0f}s {L/SR*1000:>6.1f} ms")
        return 0

    if a.sweep:
        print(f"\n{'lag':>8s} {'DTLN suppression':>18s} {'VAD frames':>12s}")
        raw_frames = silero_speech_frames(mic)
        print(f"{'raw':>8s} {'+0.0 dB':>18s} {raw_frames:>9d}")
        for ms in (0, 20, 40, 60, 80, 100, 140, 180, 240, 300):
            k = int(ms * SR / 1000)
            f2 = np.concatenate([np.zeros(k, np.float32), far_raw])[:len(mic)]
            out = DtlnAec(a.size, a.device).process(mic.copy(), f2)
            print(f"{ms:>6d}ms {db(out, mic):>+15.1f} dB "
                  f"{silero_speech_frames(out):>9d}")
        return 0

    rows = [("none (raw mic)", fr_aec.NullAec()),
            ("WebRTC APM (incumbent)", incumbent),
            (f"DTLN-aec {a.size} ({a.device})", DtlnAec(a.size, a.device))]
    print(f"\n{'processor':30s} {'suppression':>12s} {'VAD speech frames':>18s}")
    for name, proc in rows:
        t0 = time.perf_counter()
        out = proc.process(mic.copy(), far.copy())
        rt = (time.perf_counter() - t0) / (len(mic) / SR)
        supp = db(out, mic)
        frames = silero_speech_frames(out)
        print(f"{name:30s} {supp:>+9.1f} dB {frames:>13d} frames   "
              f"(RTF {rt:.3f})")
    if a.talk:
        print("\nREAD THIS AS A PRESERVATION TEST, NOT A SUPPRESSION ONE.")
        print("  You were talking, so the RIGHT answer is a HEALTHY frame count —")
        print("  your own speech should survive. A processor that reports ~0 frames")
        print("  here did not cancel the echo, it deleted the room, and it will")
        print("  delete you mid-barge-in too. Compare each row against its own")
        print("  quiet-run number: echo gone, voice kept.")
    else:
        print("\ntarget: <= -30 dB and 0 VAD frames. Anything less and the VAD "
              "still hears Friday, so ADR-064 stands.")
        print("  CAVEAT: this feeds the whole utterance offline with a perfectly")
        print("  aligned reference. The live daemon feeds it from the playback")
        print("  callback frame by frame. These numbers are an UPPER BOUND for")
        print("  both cancellers, not the live condition.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
