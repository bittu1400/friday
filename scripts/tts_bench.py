"""TTS drill (ADR-041 rule 7) — is Kokoro-82M still the right voice engine?

ADR-039/040 chose kokoro-onnx fp32 on 8 threads and ADR-005/G5 chose the
`af_bella` voice by audition. This re-runs the drill against the engines that
did not exist then, on kokoro-bench's own texts so the latency numbers stay
comparable.

Quality here is NOT a number. Each engine renders the same two lines to
`~/.cache/friday-accel-eval/tts-samples/`, to be auditioned the way af_bella
was — a TTS that is faster and flatter is a loss, not a trade.

    ~/.cache/friday-accel-eval/venv/bin/python scripts/tts_bench.py

Samples are synthesized speech of fixed benchmark sentences, not user content,
so writing them does not touch invariant #7.
"""
from __future__ import annotations

import statistics as st
import subprocess
import time
import wave
from pathlib import Path

import numpy as np

OUT = Path.home() / ".cache/friday-accel-eval/tts-samples"
MODELS = Path.home() / ".local/share/friday/models"
SHORT = "Opening Brave."
PARA = ("It's twenty-four degrees and sunny in your area right now. "
        "I found three results on the web for that question. "
        "Let me know if you want me to open any of them.")


def save(name: str, wav: np.ndarray, sr: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(np.asarray(wav, dtype=np.float32), -1, 1) * 32767).astype(np.int16)
    with wave.open(str(OUT / f"{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def report(name: str, construct_ms: float, short_ms: list[float],
           para_ms: list[float], para_s: float, rss_mb: float) -> None:
    print(f"\n=== {name} ===")
    print(f"  construct={construct_ms:.0f}ms  short p50={st.median(short_ms):.0f}ms"
          f"  paragraph p50={st.median(para_ms):.0f}ms"
          f"  RTF={st.median(para_ms) / 1000 / para_s:.3f}  RSS={rss_mb:.0f}MB")


def timed(fn, n=3):
    fn()
    out = []
    for _ in range(n):
        t0 = time.perf_counter()
        r = fn()
        out.append((time.perf_counter() - t0) * 1000)
    return out, r


def bench_kokoro():
    import onnxruntime as ort
    import psutil
    from kokoro_onnx import Kokoro
    proc = psutil.Process()
    t0 = time.perf_counter()
    so = ort.SessionOptions()
    so.intra_op_num_threads = 8
    so.inter_op_num_threads = 1
    so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess = ort.InferenceSession(str(MODELS / "kokoro/model.onnx"), so,
                                providers=["CPUExecutionProvider"])
    k = Kokoro.__new__(Kokoro)
    k._setup(session=sess, model_path=str(MODELS / "kokoro/model.onnx"),
             voices_path=str(MODELS / "kokoro/voices-v1.0.bin"),
             espeak_config=None, vocab_config=None)
    construct = (time.perf_counter() - t0) * 1000
    s_ms, (w, sr) = timed(lambda: k.create(SHORT, voice="af_bella", speed=1.0, lang="en-us"))
    save("kokoro_af_bella_short", w, sr)
    p_ms, (pw, sr) = timed(lambda: k.create(PARA, voice="af_bella", speed=1.0, lang="en-us"))
    save("kokoro_af_bella_para", pw, sr)
    report("kokoro-82M fp32 af_bella 8t (INCUMBENT)", construct, s_ms, p_ms,
           len(pw) / sr, proc.memory_info().rss / 1e6)


def bench_supertonic():
    import psutil
    import supertonic as sp
    proc = psutil.Process()
    t0 = time.perf_counter()
    tts = sp.TTS(intra_op_num_threads=8)
    style = tts.get_voice_style("F1")   # 10 built-ins: M1..M5, F1..F5
    construct = (time.perf_counter() - t0) * 1000

    def gen(text):
        # synthesize() returns (audio, DURATION_SECONDS) — the second value is
        # not a sample rate. Treating it as one writes a WAV header of "1 Hz"
        # and produces an audition file that cannot be judged.
        audio, _dur = tts.synthesize(text, style)
        return np.asarray(audio, dtype=np.float32).reshape(-1), 44100
    s_ms, (w, sr) = timed(lambda: gen(SHORT))
    save("supertonic_short", w, sr)
    p_ms, (pw, sr) = timed(lambda: gen(PARA))
    save("supertonic_para", pw, sr)
    report("supertonic-3", construct, s_ms, p_ms, len(pw) / sr,
           proc.memory_info().rss / 1e6)


def voices_supertonic():
    """Render every built-in Supertonic voice for audition.

    Kokoro's voice was chosen by ear at G5 (ADR-005/OQ-22) and this is the same
    procedure: one identical line per voice, judged by the owner, not by me.
    """
    import supertonic as sp
    tts = sp.TTS(intra_op_num_threads=8)
    names = list(tts.voice_style_names)
    print(f"  supertonic voices: {names}")
    for v in names:
        style = tts.get_voice_style(v)
        for label, text in (("short", SHORT), ("para", PARA)):
            audio, _dur = tts.synthesize(text, style)
            save(f"supertonic_{v}_{label}",
                 np.asarray(audio, dtype=np.float32).reshape(-1), 44100)
    print(f"  rendered {len(names) * 2} files")


def tune_supertonic():
    """Sweep Supertonic's quality/latency knob before pinning it.

    Whisper was pinned only after three tuning rounds (ADR-042); the fallback
    voice gets the same treatment. `total_steps` is the diffusion step count --
    fewer is faster and flatter. Renders F1 at each setting for audition,
    because "flatter" is not a number.
    """
    import psutil
    import supertonic as sp
    proc = psutil.Process()
    tts = sp.TTS(intra_op_num_threads=8)
    style = tts.get_voice_style("F1")
    print(f"  {'setting':22s} {'short':>9s} {'para':>9s} {'RTF':>7s}")
    for steps in (2, 4, 8, 16, 32):
        for speed in (1.05,) if steps != 8 else (1.05, 1.0):
            label = f"steps={steps} speed={speed}"
            gen = lambda t: np.asarray(  # noqa: E731
                tts.synthesize(t, style, total_steps=steps, speed=speed)[0],
                dtype=np.float32).reshape(-1)
            s_ms, w = timed(lambda: gen(SHORT))
            p_ms, pw = timed(lambda: gen(PARA))
            save(f"supertonic_F1_s{steps}_sp{str(speed).replace('.','')}", pw, 44100)
            print(f"  {label:22s} {st.median(s_ms):>7.0f}ms {st.median(p_ms):>7.0f}ms"
                  f" {st.median(p_ms)/1000/(len(pw)/44100):>7.3f}")
    print(f"  RSS={proc.memory_info().rss/1e6:.0f}MB   samples -> {OUT}")


if __name__ == "__main__":
    prof = subprocess.run(["powerprofilesctl", "get"], capture_output=True,
                          text=True).stdout.strip()
    print(f"power={prof}  samples -> {OUT}")
    import sys
    fns = ((voices_supertonic,) if "--voices" in sys.argv else
           (tune_supertonic,) if "--tune" in sys.argv else
           (bench_kokoro, bench_supertonic))
    for fn in fns:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            print(f"\n=== {fn.__name__} ===\n  FAIL {type(e).__name__}: "
                  f"{str(e).splitlines()[0][:140]}")
