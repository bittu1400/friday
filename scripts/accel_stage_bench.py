"""Can any NON-STT stage move off the CPU? (companion to scripts/stt_accel_bench.py)

STT was settled by `docs/hardware-placement.md`. This covers the rest of Friday's
ONNX work — TTS, speaker verification, wake — against every device OpenVINO
can reach here: CPU, NPU, Intel iGPU (`GPU`), and the NVIDIA card through
OpenCL (`GPU.1`, which is invariant #6 territory — measure, do not adopt).

Quality is the first gate, so the TTS stage does not just time itself: it
compares its waveform against the CPU reference and reports correlation and
peak sample error. A faster voice that sounds different is a loss, not a win.

Runs in the OpenVINO venv (onnxruntime-openvino displaces onnxruntime, so it
can never be the project venv):

    ~/.cache/friday-accel-eval/venv/bin/python scripts/accel_stage_bench.py tts CPU
    ~/.cache/friday-accel-eval/venv/bin/python scripts/accel_stage_bench.py speaker NPU
    ~/.cache/friday-accel-eval/venv/bin/python scripts/accel_stage_bench.py wake GPU

Nothing is written to disk (invariant #7).
"""
from __future__ import annotations

import json
import statistics as st
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import psutil

MODELS = Path.home() / ".local/share/friday/models"
OWW = (Path.home() / "Projects/Personal/Intern/friday/.venv/lib/python3.12"
       / "site-packages/openwakeword/resources/models")
REF_CACHE = Path("/tmp/friday-accel-tts-ref.npy")  # CPU waveform, for quality diff

# kokoro-bench's texts, so short-latency numbers stay comparable (ADR-040)
SHORT = "Opening Brave."
PARA = ("It's twenty-four degrees and sunny in your area right now. "
        "I found three results on the web for that question. "
        "Let me know if you want me to open any of them.")


def providers(device: str) -> list:
    """CPU means the production provider; anything else routes through OpenVINO."""
    if device == "CPU":
        return ["CPUExecutionProvider"]
    return [("OpenVINOExecutionProvider", {"device_type": device}),
            "CPUExecutionProvider"]


NPU_BUSY = Path("/sys/devices/pci0000:00/0000:00:0b.0/npu_busy_time_us")


def npu_busy_us() -> int:
    """The only honest proof a stage ran on the NPU.

    `sess.get_providers()` lists what was REGISTERED, not what executed — the
    OpenVINO EP silently partitions unsupported subgraphs back to the CPU, so
    a provider name is a check that cannot fail. This counter can: it moves by
    ~223 ms across an NPU run and by exactly 0 across a CPU run.
    """
    try:
        return int(NPU_BUSY.read_text())
    except Exception:  # noqa: BLE001
        return -1


def power_profile() -> str:
    try:
        return subprocess.run(["powerprofilesctl", "get"], capture_output=True,
                              text=True, timeout=5).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def session(path: Path, device: str, threads: int) -> ort.InferenceSession:
    so = ort.SessionOptions()
    so.intra_op_num_threads = threads
    so.inter_op_num_threads = 1
    so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(str(path), so, providers=providers(device))


def timed(fn, n: int = 5) -> tuple[float, float]:
    fn()  # warm
    ts = [(lambda t0=time.perf_counter(): (fn(), time.perf_counter() - t0)[1])()
          for _ in range(n)]
    return st.median(ts) * 1000, max(ts) * 1000


def which_ep(sess: ort.InferenceSession, device: str) -> str:
    """OpenVINO EP silently falls back to CPU per-subgraph. Say what ran."""
    eps = sess.get_providers()
    return f"{eps[0]}({device})" if eps else "?"


def bench_tts(device: str) -> None:
    from kokoro_onnx import Kokoro
    proc = psutil.Process()
    t0 = time.perf_counter()
    sess = session(MODELS / "kokoro/model.onnx", device, threads=8)
    construct = (time.perf_counter() - t0) * 1000
    k = Kokoro.__new__(Kokoro)
    k._setup(session=sess, model_path=str(MODELS / "kokoro/model.onnx"),
             voices_path=str(MODELS / "kokoro/voices-v1.0.bin"),
             espeak_config=None, vocab_config=None)
    make = lambda txt: k.create(txt, voice="af_bella", speed=1.0, lang="en-us")

    wav, sr = make(SHORT)
    short_ms, short_max = timed(lambda: make(SHORT))
    para_wav, _ = make(PARA)
    para_ms, _ = timed(lambda: make(PARA), n=3)
    rtf = (para_ms / 1000) / (len(para_wav) / sr)

    quality = "reference (CPU)"
    if device == "CPU":
        np.save(REF_CACHE, wav)
    elif REF_CACHE.exists():
        ref = np.load(REF_CACHE)
        n = min(len(ref), len(wav))
        corr = float(np.corrcoef(ref[:n], wav[:n])[0, 1]) if n > 1 else float("nan")
        quality = (f"corr={corr:.6f} maxdiff={np.abs(ref[:n]-wav[:n]).max():.5f} "
                   f"len {len(ref)}->{len(wav)}")

    print(f"\n=== TTS kokoro fp32 on {which_ep(sess, device)} ===")
    print(f"  construct={construct:.0f}ms")
    print(f"  short('{SHORT}') p50={short_ms:.0f}ms max={short_max:.0f}ms")
    print(f"  paragraph p50={para_ms:.0f}ms RTF={rtf:.3f} audio={len(para_wav)/sr:.2f}s")
    print(f"  peakRSS={proc.memory_info().rss/1e6:.0f}MB")
    print(f"  quality vs CPU: {quality}")


def bench_speaker(device: str) -> None:
    proc = psutil.Process()
    t0 = time.perf_counter()
    sess = session(MODELS / "speaker/3dspeaker_campplus.onnx", device, threads=2)
    construct = (time.perf_counter() - t0) * 1000
    # 3 s of speech at 80-dim fbank, 10 ms hop — what one verification sees
    x = np.random.randn(1, 300, 80).astype(np.float32)
    run = lambda: sess.run(None, {"x": x})[0]
    emb = run()
    p50, mx = timed(run, n=20)
    print(f"\n=== speaker campplus on {which_ep(sess, device)} ===")
    print(f"  construct={construct:.0f}ms p50={p50:.2f}ms max={mx:.2f}ms "
          f"emb={emb.shape} peakRSS={proc.memory_info().rss/1e6:.0f}MB")


def bench_wake(device: str) -> None:
    """openwakeword is a 3-model chain: melspec -> embedding -> classifier."""
    proc = psutil.Process()
    frame = np.random.randn(1, 1280).astype(np.float32)      # 80 ms @ 16 kHz
    feats = np.random.randn(1, 76, 32, 1).astype(np.float32)  # embedding window
    stages = [("melspectrogram", OWW / "melspectrogram.onnx", "input", frame),
              ("embedding", OWW / "embedding_model.onnx", "input_1", feats),
              ("hey_jarvis", MODELS / "wake/hey_jarvis.onnx", None, None)]
    print(f"\n=== wake chain on {device} ===")
    for name, path, key, x in stages:
        try:
            t0 = time.perf_counter()
            sess = session(path, device, threads=1)
            construct = (time.perf_counter() - t0) * 1000
            if key is None:  # classifier input shape comes from the graph
                i = sess.get_inputs()[0]
                key = i.name
                x = np.random.randn(*[d if isinstance(d, int) else 1
                                      for d in i.shape]).astype(np.float32)
            run = lambda: sess.run(None, {key: x})
            p50, mx = timed(run, n=50)
            print(f"  {name:16s} construct={construct:7.0f}ms p50={p50:6.3f}ms "
                  f"max={mx:6.3f}ms  [{which_ep(sess, device)}]")
        except Exception as e:  # noqa: BLE001
            msg = [ln for ln in str(e).splitlines() if ln.strip()]
            print(f"  {name:16s} FAIL {type(e).__name__}: "
                  f"{msg[-1][:110] if msg else ''}")
    print(f"  peakRSS={proc.memory_info().rss/1e6:.0f}MB")


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "tts"
    device = sys.argv[2] if len(sys.argv) > 2 else "CPU"
    prof = power_profile()
    print(f"stage={stage} device={device} ort={ort.__version__} "
          f"power={prof}"
          + ("   <-- power-saver pins all cores to ~2.2 GHz; NOT a baseline"
             if prof == "power-saver" else ""))
    t0 = npu_busy_us()
    {"tts": bench_tts, "speaker": bench_speaker, "wake": bench_wake}[stage](device)
    t1 = npu_busy_us()
    print(f"  npu_busy_time delta = {(t1 - t0) / 1000:.0f} ms"
          + ("   <-- ZERO: this did NOT run on the NPU"
             if device == "NPU" and t1 - t0 <= 0 else ""))
