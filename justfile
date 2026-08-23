# Friday task runner (ADR-025). Recipes land per gate; unimplemented gates
# are absent rather than faked. See CLAUDE.md "Commands" for the full set.

model := "~/.local/share/friday/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf"

# Start llama-server (G1 config: ctx 8192, q8_0 KV, all layers on GPU).
serve:
    PATH=/opt/cuda/bin:$PATH /opt/llama.cpp/build/bin/llama-server \
      --model {{model}} \
      --host 127.0.0.1 --port 8080 --ctx-size 8192 --n-gpu-layers 99 \
      --cache-type-k q8_0 --cache-type-v q8_0 --no-webui

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

# Full unit suite (schema drift, validator, registry, executor, turn, adversarial).
test:
    uv run pytest -q
