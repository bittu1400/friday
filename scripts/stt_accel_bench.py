"""STT accelerator probe — is the Intel NPU/iGPU a better home for Friday's STT?

Answers the question ADR-019 opened and OQ-10 left at "presence is confirmed,
throughput is not". Runs the SAME 20 real DMIC clips, the SAME miss rule and
the SAME p50/p95 that produced ADR-042's winning row, so the numbers are
directly comparable to `small.en beam1 +hotwords  p95 741 ms  miss 4/20`.

Two backends, one scorer:

    fw   faster-whisper / CTranslate2, CPU int8  — production config, baseline
    ov   openvino-genai WhisperPipeline          — CPU / GPU.0 (iGPU) / NPU

They live in different venvs (ctranslate2 vs openvino-genai), so run the file
twice with different interpreters:

    ~/.cache/whisper-bench/.venv/bin/python stt_accel_bench.py fw
    ~/.cache/friday-accel-eval/venv/bin/python stt_accel_bench.py ov NPU

Nothing is written to disk by this script (invariant #7); it prints misses so
accuracy can be read, and those are scripted bench sentences, not user speech.
"""
from __future__ import annotations

import statistics
import sys
import time
import wave
from pathlib import Path

import numpy as np
import psutil

CLIPS = sorted((Path.home() / ".cache/whisper-bench/clips").glob("clip_*.wav"))
REFS = {c.name: c.with_suffix(".txt").read_text().strip() for c in CLIPS}
OV_MODEL = Path.home() / ".cache/friday-accel-eval/whisper-small.en-int8-ov"
THREADS = 8
BEAM = 1
PASS_MS = 800  # ADR-004 / OQ-07 gate
# friday.config.STT_HOTWORDS, verbatim
HOTWORDS = ("Brave, foot, terminal, Visual Studio Code, VLC, mpv, Neovim, "
            "Arch Linux, Kathmandu, lo-fi, jazz, YouTube, dark theme, web search")


def power_profile() -> str:
    """The lever that invalidated two external audits.

    `balanced` is Friday's TARGET profile: it is what the machine normally
    runs, `performance` may only ever be better, and `power-saver` is a
    capability cap rather than a baseline (all cores pin to ~2.2 GHz, and the
    same clips go p95 804 ms -> 1310 ms). Both 2026-08-30 optimization reports
    benchmarked in `power-saver` and neither noticed. A bench that does not
    print this number is not comparable to anything.
    """
    try:
        import subprocess
        return subprocess.run(["powerprofilesctl", "get"], capture_output=True,
                              text=True, timeout=5).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def pctl(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def is_miss(clip_name: str, text: str) -> bool:
    """sweep3.py's rule, verbatim — so miss counts compare to ADR-042."""
    ref = REFS[clip_name].lower()
    got = text.lower().strip(" .,!?").replace("-", "")
    r = ref.replace("-", "").replace(" ", "")
    return r not in got.replace(" ", "") and got.replace(" ", "") not in r


def read_pcm(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def audio_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / float(w.getframerate())


def report(label: str, construct_ms: float, warm_ms: float,
           times: list[float], misses: list[str], rss_mb: float) -> None:
    total_audio = sum(audio_seconds(c) for c in CLIPS)
    p50, p95 = pctl(times, 0.5), pctl(times, 0.95)
    print(f"\n=== {label} ===")
    for ln in misses:
        print(f"    {ln}")
    print(f"  construct={construct_ms:.0f}ms  first(warmup)={warm_ms:.0f}ms")
    print(f"  n={len(times)} p50={p50:.0f}ms p95={p95:.0f}ms "
          f"max={max(times):.0f}ms mean={statistics.mean(times):.0f}ms")
    print(f"  RTF={sum(times)/1000/total_audio:.3f} (lower=faster)  "
          f"peakRSS={rss_mb:.0f}MB  miss={len(misses)}/{len(CLIPS)}  "
          f"[{'PASS' if p95 <= PASS_MS else 'FAIL'} vs {PASS_MS}ms]")


def bench_fw(device: str = "cpu") -> None:
    """device="cuda" is MEASUREMENT ONLY — invariant #6 forbids adopting it.

    It is here so the size of the forbidden prize is a number rather than an
    argument, and so the FR-71 violation is observable: run it while watching
    `nvidia-smi --query-compute-apps` and count the processes.
    """
    from faster_whisper import WhisperModel
    proc = psutil.Process()
    t0 = time.perf_counter()
    m = WhisperModel("small.en", device=device,
                     compute_type="int8" if device == "cpu" else "int8_float16",
                     cpu_threads=THREADS)
    construct = (time.perf_counter() - t0) * 1000
    kw = dict(language="en", vad_filter=True, beam_size=BEAM, hotwords=HOTWORDS)
    t0 = time.perf_counter()
    list(m.transcribe(str(CLIPS[0]), **kw)[0])
    warm = (time.perf_counter() - t0) * 1000
    times, misses, peak = [], [], 0.0
    for c in CLIPS:
        t0 = time.perf_counter()
        segs, _ = m.transcribe(str(c), **kw)
        text = " ".join(s.text.strip() for s in segs)
        times.append((time.perf_counter() - t0) * 1000)
        if is_miss(c.name, text):
            misses.append(f"{c.name}: {text!r} vs {REFS[c.name]!r}")
        peak = max(peak, proc.memory_info().rss / 1e6)
    report(f"faster-whisper small.en {device.upper()} beam1 +hotwords"
           + (" (PRODUCTION)" if device == "cpu" else " (invariant #6: DO NOT ADOPT)"),
           construct, warm, times, misses, peak)


def bench_ov(device: str, hotwords: bool = False) -> None:
    import openvino_genai as ov_genai
    proc = psutil.Process()
    t0 = time.perf_counter()
    pipe = ov_genai.WhisperPipeline(str(OV_MODEL), device=device)
    construct = (time.perf_counter() - t0) * 1000
    cfg = pipe.get_generation_config()
    # small.en is English-only: setting cfg.language raises in openvino-genai
    # task likewise: English-only model
    cfg.return_timestamps = False
    if hotwords:
        cfg.hotwords = HOTWORDS
    pcms = {c.name: read_pcm(c) for c in CLIPS}
    t0 = time.perf_counter()
    pipe.generate(pcms[CLIPS[0].name], cfg)
    warm = (time.perf_counter() - t0) * 1000
    times, misses, peak = [], [], 0.0
    for c in CLIPS:
        t0 = time.perf_counter()
        text = str(pipe.generate(pcms[c.name], cfg))
        times.append((time.perf_counter() - t0) * 1000)
        if is_miss(c.name, text):
            misses.append(f"{c.name}: {text!r} vs {REFS[c.name]!r}")
        peak = max(peak, proc.memory_info().rss / 1e6)
    report(f"openvino-genai whisper-small.en-int8-ov on {device}"
           f"{' +hotwords' if hotwords else ''}",
           construct, warm, times, misses, peak)


def bench_moonshine(model: str = "moonshine/base") -> None:
    """Moonshine uses variable-length windows instead of Whisper's fixed 30 s,
    which is why it is fast on commands. Its paper documents >100% WER on
    sub-1-second clips (repeated tokens) — Friday says "yes" constantly, so
    that failure mode matters more here than the average WER does."""
    import moonshine_onnx as mo
    proc = psutil.Process()
    t0 = time.perf_counter()
    # transcribe(path, "moonshine/base") REBUILDS the model on every call.
    # Passing the object is the only way to time inference rather than loading.
    m = mo.MoonshineOnnxModel(model_name=model)
    tok = mo.load_tokenizer()
    mo.transcribe(str(CLIPS[0]), m)              # warm
    construct = (time.perf_counter() - t0) * 1000
    times, misses, peak = [], [], 0.0
    for c in CLIPS:
        t0 = time.perf_counter()
        text = " ".join(tok.decode_batch(m.generate(mo.load_audio(str(c)))))
        times.append((time.perf_counter() - t0) * 1000)
        if is_miss(c.name, text):
            misses.append(f"{c.name}: {text!r} vs {REFS[c.name]!r}")
        peak = max(peak, proc.memory_info().rss / 1e6)
    report(f"{model} (onnx, CPU)", construct, times[0], times, misses, peak)


if __name__ == "__main__":
    if not CLIPS:
        sys.exit("no clips in ~/.cache/whisper-bench/clips")
    which = sys.argv[1] if len(sys.argv) > 1 else "fw"
    prof = power_profile()
    print(f"{len(CLIPS)} clips, {sum(audio_seconds(c) for c in CLIPS):.1f}s audio")
    print(f"power profile: {prof}"
          + ("   <-- power-saver pins all cores to ~2.2 GHz; NOT a baseline"
             if prof == "power-saver" else ""))
    if which == "fw":
        bench_fw(sys.argv[2] if len(sys.argv) > 2 else "cpu")
    elif which == "moonshine":
        bench_moonshine(sys.argv[2] if len(sys.argv) > 2 else "moonshine/base")
    else:
        bench_ov(sys.argv[2] if len(sys.argv) > 2 else "CPU",
                 hotwords="--hotwords" in sys.argv)
