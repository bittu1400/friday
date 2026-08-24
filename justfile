# Friday task runner (ADR-025). Recipes land per gate; unimplemented gates
# are absent rather than faked. See CLAUDE.md "Commands" for the full set.

model := "~/.local/share/friday/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf"

# Start llama-server (G1 config: ctx 8192, q8_0 KV, all layers on GPU).
serve:
    PATH=/opt/cuda/bin:$PATH /opt/llama.cpp/build/bin/llama-server \
      --model {{model}} \
      --host 127.0.0.1 --port 8080 --ctx-size 8192 --n-gpu-layers 99 \
      --cache-type-k q8_0 --cache-type-v q8_0 --no-webui

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

# G7 egress proof (FR-60, invariant #8): SearXNG is the ONLY outbound path.
# Confirms no service binds beyond loopback. The block-all-non-loopback half
# is a manual step (needs privileges) documented in progress.md.
test-egress:
    @echo "listening sockets (must be 127.0.0.1 only):"
    @ss -ltnp | grep -E '8080|8888' || true
    @echo "asserting no 0.0.0.0 bind on 8080/8888:"
    @! ss -ltnp | grep -E '0\.0\.0\.0:(8080|8888)'

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

# Start the voice-in daemon (G6): PTT socket + capture + STT + turn + speak.
# Add --dry-run to plan without launching, --no-voice for silent outcomes.
voice *ARGS:
    uv run python -m friday.voice_main {{ARGS}}

# Send a PTT command to the running daemon: `just ptt press` / `just ptt release`.
# The Hyprland bind runs the module directly (no console script; package=false).
ptt CMD:
    uv run python -m friday.ptt_cli {{CMD}}

# Full system self-test (G9): server reachability, GPU arch, DB perms/schema, audio, panic, egress.
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

