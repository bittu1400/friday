"""VAD drill (ADR-041 rule 7) — is `webrtcvad` still the right detector?

This is the OQ-39 probe, and it is aimed at **D3**: hands-free is unusable
because every wake capture ran the full 15 s cap, which means the gate never
saw end-of-speech. OQ-39 asks for the voiced fraction at aggressiveness 0-3.
This answers that, and then asks the question that actually decides D3 --
**does `SpeechGate` ever emit `end`, and how long after the talking stops?**

Candidates:
    webrtcvad 0..3      incumbent (2011 GMM, 20 ms frames)
    silero v4           already on disk, shipped inside openwakeword
    silero current      `silero-vad` package, 512-sample/32 ms frames
    silero ifless       same, built without the ONNX `If` op (accelerator path)

It drives the REAL `friday.audio.vad.SpeechGate`, not a copy, on the 20 real
DMIC clips, each with 2 s of that clip's own quietest room noise appended --
digital silence would flatter every detector and prove nothing.

    ~/.cache/friday-accel-eval/venv/bin/python scripts/vad_bench.py

Nothing is written to disk (invariant #7).
"""
from __future__ import annotations

import glob
import statistics as st
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from friday.audio.vad import SpeechGate  # noqa: E402  the real gate, not a copy

CLIPS = sorted((Path.home() / ".cache/whisper-bench/clips").glob("clip_*.wav"))
TAIL_S = 2.0        # room noise appended after speech, to test end-of-speech
END_SILENCE_S = 0.8  # config.VAD_END_SILENCE_S
MIN_SPEECH_S = 0.3   # config.VAD_MIN_SPEECH_S


def read_pcm(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def with_room_tail(pcm: np.ndarray, sr: int = 16000) -> tuple[np.ndarray, float]:
    """Append this clip's own quietest half-second, tiled. Returns (audio, speech_end_s).

    Real room noise, real microphone, real noise floor — appending zeros would
    make every detector look good and would not resemble the live path at all.
    """
    win = sr // 2
    if len(pcm) <= win:
        quiet = pcm
    else:
        rms = [np.sqrt(np.mean(pcm[i:i + win] ** 2)) for i in range(0, len(pcm) - win, win // 2)]
        i = int(np.argmin(rms)) * (win // 2)
        quiet = pcm[i:i + win]
    tail = np.tile(quiet, int(np.ceil(TAIL_S * sr / len(quiet))))[: int(TAIL_S * sr)]
    return np.concatenate([pcm, tail]), len(pcm) / sr


class Silero:
    """Streaming Silero VAD. v4 carries (h, c); v5+ carries a single `state`."""

    def __init__(self, path: str, threshold: float = 0.5) -> None:
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.intra_op_num_threads = 1
        self.s = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
        self.names = {i.name for i in self.s.get_inputs()}
        self.v4 = "h" in self.names
        self.threshold = threshold
        self.frame = 512  # both generations want 512 samples @ 16 kHz
        # v5+ prepends a 64-sample context so the graph actually sees 576.
        # Feeding a bare 512 returns ~0.001 on obvious speech — silently, with
        # no error. That is what makes this the easy way to "prove" the new
        # model is worse than the old one.
        self.ctx_size = 0 if self.v4 else 64
        self.reset()

    def reset(self) -> None:
        if self.v4:
            self.h = np.zeros((2, 1, 64), dtype=np.float32)
            self.c = np.zeros((2, 1, 64), dtype=np.float32)
        else:
            self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.ctx = np.zeros((1, self.ctx_size), dtype=np.float32)

    def is_speech(self, frame: np.ndarray) -> bool:
        x = frame.reshape(1, -1).astype(np.float32)
        if self.ctx_size:
            x = np.concatenate([self.ctx, x], axis=1)
            self.ctx = x[:, -self.ctx_size:]
        sr = np.array(16000, dtype=np.int64)
        if self.v4:
            out, self.h, self.c = self.s.run(None, {"input": x, "sr": sr,
                                                    "h": self.h, "c": self.c})
        else:
            out, self.state = self.s.run(None, {"input": x, "sr": sr,
                                                "state": self.state})
        return float(out[0][0]) >= self.threshold


class WebRtc:
    def __init__(self, mode: int) -> None:
        import webrtcvad

        self.v = webrtcvad.Vad(mode)
        self.frame = 320  # 20 ms, what friday/audio/vad.py uses

    def reset(self) -> None:
        pass

    def is_speech(self, frame: np.ndarray) -> bool:
        pcm = (np.clip(frame, -1.0, 1.0) * 32767.0).astype(np.int16)
        return self.v.is_speech(pcm.tobytes(), 16000)


def evaluate(name: str, det) -> None:
    frame_ms = det.frame / 16.0
    voiced, ends, starts, costs, no_start = [], [], 0, [], []
    for c in CLIPS:
        audio, speech_end_s = with_room_tail(read_pcm(c))
        det.reset()
        gate = SpeechGate(frame_ms=int(round(frame_ms)),
                          end_silence_s=END_SILENCE_S, min_speech_s=MIN_SPEECH_S)
        n_v = n_f = 0
        started = ended_at = None
        for i in range(0, len(audio) - det.frame, det.frame):
            f = audio[i:i + det.frame]
            t0 = time.perf_counter()
            sp = det.is_speech(f)
            costs.append((time.perf_counter() - t0) * 1000)
            n_v += sp
            n_f += 1
            ev = gate.push(sp)
            t = (i + det.frame) / 16000.0
            if ev == "start" and started is None:
                started = t
            if ev == "end" and ended_at is None:
                ended_at = t
        voiced.append(n_v / max(1, n_f))
        if started is not None:
            starts += 1
        else:
            no_start.append(c.name)
        if ended_at is not None:
            ends.append(ended_at - speech_end_s)
    print(f"\n=== {name} ===")
    print(f"  voiced fraction  p50={st.median(voiced):.3f} "
          f"min={min(voiced):.3f} max={max(voiced):.3f}")
    print(f"  start detected   {starts}/{len(CLIPS)}"
          + (f"   MISSED: {','.join(n[:-4] for n in no_start)}" if no_start else ""))
    print(f"  end   detected   {len(ends)}/{len(CLIPS)}", end="")
    if ends:
        print(f"   latency after speech p50={st.median(ends) * 1000:+.0f}ms "
              f"min={min(ends) * 1000:+.0f} max={max(ends) * 1000:+.0f}")
    else:
        print("   <-- NEVER ENDS: this is D3")
    print(f"  cost/frame       p50={st.median(costs):.4f}ms "
          f"({frame_ms:.0f}ms frames, {st.median(costs) / frame_ms * 100:.2f}% of realtime)")


if __name__ == "__main__":
    prof = subprocess.run(["powerprofilesctl", "get"], capture_output=True,
                          text=True).stdout.strip()
    print(f"{len(CLIPS)} clips + {TAIL_S}s room-noise tail each, power={prof}")
    sv = glob.glob(str(Path(__file__).resolve().parent.parent
                       / ".venv/**/openwakeword/resources/models/silero_vad.onnx"),
                   recursive=True)
    for mode in (0, 1, 2, 3):
        evaluate(f"webrtcvad mode={mode}" + ("  (INCUMBENT)" if mode == 2 else ""),
                 WebRtc(mode))
    if sv:
        evaluate("silero v4 (bundled with openwakeword)", Silero(sv[0]))
    # current silero lives in the scratch venv; it is only a file, so the
    # project venv (which already has onnxruntime + webrtcvad) can read it.
    d = Path.home() / ".cache/friday-accel-eval/venv/lib/python3.12/site-packages/silero_vad/data"
    for fn, label in (("silero_vad.onnx", "silero current"),
                      ("silero_vad_op18_ifless.onnx", "silero current, If-free")):
        if (d / fn).exists():
            for thr in (0.5, 0.3):
                evaluate(f"{label}  thr={thr}", Silero(str(d / fn), threshold=thr))
        else:
            print(f"\nmissing {d / fn}")
