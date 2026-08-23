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

# G2 eval: fixture -> prompt -> llama-server -> validator -> compare.
eval:
    uv run python -m friday.eval_harness

# OQ-08: run the eval set with and without the `thought` field.
eval-thought:
    uv run python -m friday.eval_harness --both

# Record the current pass/fail map as the regression baseline (ADR-030).
eval-baseline:
    uv run python -m friday.eval_harness --update-baseline

# Adversarial suite AS-1..AS-12 straight into the validator.
test-adversarial:
    uv run pytest tests/test_adversarial.py -q

# Unit tests (schema/grammar drift, validator, adversarial).
test:
    uv run pytest -q
