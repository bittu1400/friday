# Friday task runner (ADR-025). Recipes land per gate; unimplemented gates
# are absent rather than faked. See CLAUDE.md "Commands" for the full set.

model := "~/.local/share/friday/models/gemma-4-12B-it-qat-UD-Q4_K_XL.gguf"

# Start llama-server. MUST stay byte-for-byte equivalent to the ExecStart in
# deploy/systemd/friday-llm.service -- two copies of one config IS the bug
# (C1's lesson). If you change one, change the other. That file carries the
# reasoning for --parallel 1, -fa on and --reasoning off; do not drop them here,
# they are worth 514 MiB and one invariant.
serve:
    PATH=/opt/cuda/bin:$PATH /opt/llama.cpp/build/bin/llama-server \
      --model {{model}} \
      --host 127.0.0.1 --port 8080 --ctx-size 8192 --n-gpu-layers 99 \
      --parallel 1 --cache-type-k q8_0 --cache-type-v q8_0 -fa on \
      --reasoning off --no-webui

# Manage the loopback SearXNG unit (ADR-045). `just searxng start|stop|status`.
# The unit binds 127.0.0.1:8888 ONLY (invariant #8). Install once with:
#   systemctl --user link $PWD/deploy/searxng/friday-searxng.service
searxng CMD="status":
    systemctl --user {{CMD}} friday-searxng

# Regenerate the GBNF grammars from the single schema source of truth.
grammar:
    uv run python -m friday.llm.schema

# Start the text-mode orchestrator (TUI). Add --dry-run to print argv
# instead of launching apps: `just run --dry-run` (needs `--` passthrough).
run *ARGS:
    uv run python -m friday {{ARGS}}

# G2 eval: fixture -> prompt -> llama-server -> validator -> compare.
eval:
    uv run python -m friday.eval_harness

# Record the current pass/fail map as the regression baseline (ADR-030).
eval-baseline:
    uv run python -m friday.eval_harness --update-baseline

# Adversarial 16/16: AS-1..12 into the validator, AS-13..16 the youtube builder.
test-adversarial:
    uv run pytest tests/test_adversarial.py tests/test_youtube.py -q

# G7 injection suite: 20 hostile result sets, zero executor dispatches (FR-63).
test-injection:
    uv run pytest tests/test_injection.py -v

# Assert store/ SQL is strictly parameterized (no f-string/format/concat) — guards user free-text (notes, reminder messages, prefs) against SQL injection.
test-no-fstring-sql:
    @echo "asserting store/ contains no f-string / interpolated SQL:"
    @! grep -rniE "f[\"'][^\"']*(select|insert|update|delete|from|where|values)" friday/store/ \
      && echo "OK: store/ is strictly parameterized SQL" \
      || (echo "FAIL: interpolated SQL literal found in store/" && exit 1)

# Confirms no service binds beyond loopback (FR-60, invariant #8).
test-binds:
    @echo "listening sockets (must be 127.0.0.1 only):"
    @ss -ltnp | grep -E '8080|8888' || true
    @echo "asserting no 0.0.0.0 bind on 8080/8888:"
    @! ss -ltnp | grep -E '0\.0\.0\.0:(8080|8888)'

# G7 egress proof (FR-60, invariant #8): SearXNG is the ONLY outbound path.
test-egress:
    uv run pytest tests/test_egress.py -v

# Manage stored preferences (FR-56): list | export | forget [--hard] | reset --yes.
# `just prefs list`; `just prefs forget editor`; `just prefs reset --yes`.
prefs *ARGS:
    uv run python -m friday.prefs_cli {{ARGS}}

# Speak a line with Kokoro (G5, ADR-039/040). `just say "hello"`.
say *ARGS:
    uv run python -m friday.audio.say {{ARGS}}

# Audition the three candidate voices on one line (af_bella/af_heart/af_sky).
audition:
    uv run python -m friday.audio.say --audition

# Fetch + checksum the Kokoro model and voices into the XDG data dir (ADR-039).
fetch-voice:
    #!/usr/bin/env bash
    set -euo pipefail
    dst="${XDG_DATA_HOME:-$HOME/.local/share}/friday/models/kokoro"
    mkdir -p "$dst"
    base="https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX/resolve/main/onnx"
    [ -f "$dst/model.onnx" ] || curl -sL -o "$dst/model.onnx" "$base/model.onnx"
    [ -f "$dst/voices-v1.0.bin" ] || curl -sL -o "$dst/voices-v1.0.bin" \
      "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
    echo "8fbea51ea711f2af382e88c833d9e288c6dc82ce5e98421ea61c058ce21a34cb  $dst/model.onnx" | sha256sum -c -
    echo "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d  $dst/voices-v1.0.bin" | sha256sum -c -

# op18-ifless is the fastest of the three exports and is built without the ONNX
# `If` op, so it stays accelerator-portable (OQ-51). Required: without it, VAD
# falls back to webrtcvad, which ended only 15 of 20 real DMIC clips and is the
# cause of D3 (hands-free captures that never end).
# Fetch the SHA256-pinned Silero VAD model -- end-of-speech detection (ADR-095).
fetch-vad:
    #!/usr/bin/env bash
    set -euo pipefail
    dst="${XDG_DATA_HOME:-$HOME/.local/share}/friday/models/vad"
    mkdir -p "$dst"
    url="https://raw.githubusercontent.com/snakers4/silero-vad/v6.2.1/src/silero_vad/data/silero_vad_op18_ifless.onnx"
    [ -f "$dst/silero_vad_op18_ifless.onnx" ] || curl -sL -o "$dst/silero_vad_op18_ifless.onnx" "$url"
    echo "7671cd04b004e9076da0d4a7b1a5aec36adf161c39230c1cb94a4fd5db6bbd28  $dst/silero_vad_op18_ifless.onnx" | sha256sum -c -

# Start the voice-in daemon (G6): PTT socket + capture + STT + turn + speak.
# Add --dry-run to plan without launching, --no-voice for silent outcomes.
voice *ARGS:
    uv run python -m friday.voice_main {{ARGS}}

# Send a PTT command to the running daemon: `just ptt press` / `just ptt release`.
# The Hyprland bind runs the module directly (no console script; package=false).
ptt CMD:
    uv run python -m friday.ptt_cli {{CMD}}

# Full system self-test (G9), 8 checks: llama-server, searxng, GPU arch,
# LLM actually on GPU, DB perms/schema (incl. WAL sidecars), audio devices,
# panic switch, loopback-only socket binds.
selftest *ARGS:
    uv run python -m friday.selftest {{ARGS}}

# Live wake-word and VAD benchmark harness (G10).
wake-bench *ARGS:
    uv run python scripts/wake_bench.py {{ARGS}}

# Interactive 10-utterance speaker voiceprint enrollment (G13).
enroll-voice *ARGS:
    uv run python -m friday.speaker_enroll {{ARGS}}

# Full unit suite (schema drift, validator, registry, executor, turn, audio, adversarial).
test:
    uv run pytest -q


# --- 2026-08-30 optimization drill harnesses (ADR-085..088) -------------------
# These CANNOT run under `uv run`: onnxruntime-openvino displaces the
# onnxruntime the project depends on, and faster-whisper + openvino-genai
# cannot share one venv. They run from scratch venvs, which is deliberate --
# CLAUDE.md rule 7 forbids touching the project venv to benchmark.
# Every one of them prints `powerprofilesctl get`; a run in `power-saver` is
# void (ADR-087). Full numbers: docs/hardware-placement.md

_ov  := "~/.cache/friday-accel-eval/venv/bin/python"
_fw  := "~/.cache/whisper-bench/.venv/bin/python"
_cu  := "~/.cache/friday-accel-eval/venv-cuda/bin/python"

# STT baseline on the 20 real DMIC clips (ADR-042 config). Beat: p95 713-804ms, miss 4/20.
bench-stt *ARGS:
    {{_fw}} scripts/stt_accel_bench.py fw {{ARGS}}

# STT via OpenVINO. Device: CPU | NPU | GPU.0 (iGPU) | GPU.1. Add --hotwords.
bench-stt-ov *ARGS:
    {{_ov}} scripts/stt_accel_bench.py ov {{ARGS}}

# STT on CUDA -- MEASUREMENT ONLY, invariant #6 forbids adopting it (OQ-53).
bench-stt-cuda:
    LD_LIBRARY_PATH=$HOME/.cache/friday-accel-eval/venv-cuda/lib/python3.12/site-packages/nvidia/cublas/lib:$HOME/.cache/friday-accel-eval/venv-cuda/lib/python3.12/site-packages/nvidia/cudnn/lib \
        {{_cu}} scripts/stt_accel_bench.py fw cuda

# webrtcvad 0-3 vs Silero through the REAL SpeechGate -- the D3 evidence (OQ-51).
bench-vad:
    uv run python scripts/vad_bench.py

# TTS: Kokoro vs Supertonic. --voices renders all 10 voices; --tune sweeps steps.
bench-tts *ARGS:
    {{_ov}} scripts/tts_bench.py {{ARGS}}

# Non-STT stage on an accelerator: STAGE=tts|speaker|wake DEVICE=CPU|NPU|GPU|GPU.1
bench-stage STAGE DEVICE="CPU":
    {{_ov}} scripts/accel_stage_bench.py {{STAGE}} {{DEVICE}}

# Moonshine tuning rounds (ADR-086) -- kept runnable so the reject can be re-checked.
bench-moonshine:
    {{_ov}} scripts/moonshine_tune.py

# LIVE AEC: none/WebRTC/DTLN over one capture. STOP `friday` FIRST. --talk = preservation test.
bench-aec *ARGS:
    {{_ov}} scripts/aec_bench.py {{ARGS}}
