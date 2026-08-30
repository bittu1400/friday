"""Moonshine tuning drill — the rounds ADR-042 gave Whisper, given to Moonshine.

The first pass benched stock Moonshine against a Whisper that had already had
three rounds of tuning (model choice, beam, hotwords) and rejected it at
10/20 misses. That comparison was not fair, so this runs the equivalent rounds.

Moonshine's ONNX package exposes no beam search, no hotwords and no
initial_prompt -- `generate()` is a plain greedy argmax loop. So the levers are:

    R1  model + precision      tiny/base x float/quantized
    R2  audio preprocessing    peak normalisation, silence trimming
    R3  domain logit bias      the hotword equivalent, implemented here,
                               because the decode loop is ordinary Python

Scored with `stt_accel_bench.is_miss` -- character for character the rule that
produced ADR-042's `miss 4/20`, so every number on this page is comparable.

    ~/.cache/friday-accel-eval/venv/bin/python scripts/moonshine_tune.py
"""
from __future__ import annotations

import statistics as st
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stt_accel_bench import CLIPS, HOTWORDS, REFS, is_miss, pctl, read_pcm  # noqa: E402

MAX_LEN_CAP = 96  # ADR-042's utterances are short; runaway decodes are pure cost


def preprocess(pcm: np.ndarray, *, normalize: bool = False,
               trim: bool = False, thresh: float = 0.02) -> np.ndarray:
    """Moonshine uses variable-length windows, so what you feed it is a lever
    in a way it never was for Whisper's fixed 30 s chunks."""
    x = pcm
    if trim:
        win = 320
        frames = x[: len(x) // win * win].reshape(-1, win)
        loud = np.sqrt((frames ** 2).mean(axis=1)) > thresh
        if loud.any():
            i, j = int(np.argmax(loud)), int(len(loud) - np.argmax(loud[::-1]))
            x = x[max(0, (i - 3) * win): min(len(x), (j + 3) * win)]
    if normalize:
        peak = float(np.abs(x).max())
        if peak > 1e-6:
            x = x / peak * 0.95
    return x.astype(np.float32)


def domain_token_ids(tok) -> list[int]:
    """Every token that spells a word in Friday's fixed vocabulary.

    This is what `hotwords` does inside faster-whisper: make the domain words
    cheaper to emit. Moonshine has no such knob, so it is applied directly to
    the logits below.
    """
    ids: set[int] = set()
    for phrase in HOTWORDS.split(","):
        p = phrase.strip()
        for variant in (p, " " + p, p.lower(), " " + p.lower()):
            ids.update(tok.encode(variant).ids)
    return sorted(ids)


def generate_biased(m, audio: np.ndarray, bias_ids: list[int], bias: float,
                    max_len: int = MAX_LEN_CAP) -> list[int]:
    """`MoonshineOnnxModel.generate`, with a constant logit bonus on the domain
    tokens. Everything else is byte-for-byte the upstream greedy loop."""
    x = audio[None, ...].astype(np.float32)
    enc_in = {"input_values": x}
    if "attention_mask" in m.encoder_input_names:
        enc_in["attention_mask"] = np.ones(x.shape, dtype=np.int64)
        audio_mask = enc_in["attention_mask"]
    else:
        audio_mask = None
    last_hidden_state = m.encoder.run(None, enc_in)[0]

    past = {
        f"past_key_values.{i}.{a}.{b}": np.zeros(
            (1, m.num_key_value_heads, 0, m.head_dim), dtype=np.float32)
        for i in range(m.num_layers) for a in ("decoder", "encoder")
        for b in ("key", "value")
    }
    tokens = [m.decoder_start_token_id]
    input_ids = [tokens]
    bias_idx = np.asarray(bias_ids, dtype=np.int64)
    for i in range(max_len):
        dec = dict(input_ids=input_ids, encoder_hidden_states=last_hidden_state,
                   use_cache_branch=[i > 0], **past)
        if "encoder_attention_mask" in m.decoder_input_names:
            dec = dict(encoder_attention_mask=audio_mask, **dec)
        logits, *present = m.decoder.run(None, dec)
        row = logits[0, -1].copy()
        if bias:
            row[bias_idx] += bias
        nxt = int(row.argmax())
        tokens.append(nxt)
        if nxt == m.eos_token_id:
            break
        input_ids = [[nxt]]
        for k, v in zip(past.keys(), present):
            if i == 0 or "decoder" in k:
                past[k] = v
    return tokens


def run(label: str, model_name: str, *, precision: str = "float",
        normalize: bool = False, trim: bool = False, bias: float = 0.0) -> None:
    import moonshine_onnx as mo
    import psutil
    proc = psutil.Process()
    try:
        t0 = time.perf_counter()
        m = mo.MoonshineOnnxModel(model_name=model_name, model_precision=precision)
        tok = mo.load_tokenizer()
        construct = (time.perf_counter() - t0) * 1000
    except Exception as e:  # noqa: BLE001
        print(f"\n=== {label} ===\n  LOAD FAIL {type(e).__name__}: "
              f"{str(e).splitlines()[0][:110]}")
        return
    bias_ids = domain_token_ids(tok) if bias else []
    pcms = {c.name: preprocess(read_pcm(c), normalize=normalize, trim=trim)
            for c in CLIPS}
    decode = (lambda a: generate_biased(m, a, bias_ids, bias)) if bias \
        else (lambda a: m.generate(a[None, ...])[0])
    decode(pcms[CLIPS[0].name])  # warm
    times, misses = [], []
    for c in CLIPS:
        t0 = time.perf_counter()
        text = tok.decode_batch([decode(pcms[c.name])])[0]
        times.append((time.perf_counter() - t0) * 1000)
        if is_miss(c.name, text):
            misses.append(f"{c.name[:-4]}: {text.strip()!r}")
    print(f"\n=== {label} ===")
    for ln in misses:
        print(f"    {ln}")
    print(f"  construct={construct:.0f}ms p50={pctl(times,0.5):.0f}ms "
          f"p95={pctl(times,0.95):.0f}ms RSS={proc.memory_info().rss/1e6:.0f}MB "
          f"miss={len(misses)}/{len(CLIPS)}")


if __name__ == "__main__":
    prof = subprocess.run(["powerprofilesctl", "get"], capture_output=True,
                          text=True).stdout.strip()
    print(f"{len(CLIPS)} clips, power={prof}   "
          f"(beat: whisper small.en p95 714-804ms, miss 4/20)")

    print("\n----- R1: model + precision -----")
    for name in ("tiny", "base"):
        for prec in ("float", "quantized"):
            run(f"moonshine/{name} {prec}", name, precision=prec)

    print("\n----- R2: audio preprocessing (base/float) -----")
    run("base +normalize", "base", normalize=True)
    run("base +trim", "base", trim=True)
    run("base +normalize +trim", "base", normalize=True, trim=True)

    print("\n----- R3: domain logit bias, the hotwords equivalent -----")
    for b in (2.0, 5.0, 10.0):
        run(f"base +bias{b:g}", "base", bias=b)
    run("base +bias5 +normalize +trim", "base", bias=5.0,
        normalize=True, trim=True)
