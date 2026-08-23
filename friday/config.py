"""Typed configuration and fixed paths.

Minimal at G3: the paths the executor and panic control need, plus the
llama-server URL. A full typed-config loader (architecture.md §2) arrives
when there is more than this to configure.
"""

from __future__ import annotations

import os
from pathlib import Path

# XDG state dir (ADR-023). Created at G0; not created here.
STATE_DIR: Path = Path(
    os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")
) / "friday"

# Panic control (FR-36): either this file exists, or the env var is set.
# Checked before EVERY dispatch. Two forms so it can be tripped from a key
# bind (touch the file) or from the environment (a wrapping service).
PANIC_FILE: Path = STATE_DIR / "DISABLED"
PANIC_ENV: str = "FRIDAY_DISABLED"

LLAMA_BASE_URL: str = os.environ.get("FRIDAY_LLAMA_URL", "http://127.0.0.1:8080")

# The persistence store (FR-50). Mode 0600, in the 0700 state dir; both are
# enforced by store/db.py on open, not assumed.
MEMORY_DB: Path = STATE_DIR / "memory.db"

# Retention (FR-59 / ADR-038): audit rows + session summaries only.
RETENTION_DAYS: int = int(os.environ.get("FRIDAY_RETENTION_DAYS", "90"))

# Voice out (G5, ADR-039/040). Kokoro-82M via kokoro-onnx, CPU only, fp32.
# Model lives in the XDG data dir alongside the LLM, not in the repo.
_DATA_DIR: Path = Path(
    os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
) / "friday"
KOKORO_MODEL: Path = _DATA_DIR / "models" / "kokoro" / "model.onnx"
KOKORO_VOICES: Path = _DATA_DIR / "models" / "kokoro" / "voices-v1.0.bin"
# af_bella primary, af_heart fallback if the primary is missing (OQ-22).
KOKORO_VOICE: str = os.environ.get("FRIDAY_VOICE", "af_bella")
KOKORO_VOICE_FALLBACK: str = "af_heart"
# 8 = the P-core count; measured optimum, 24 threads is worse (ADR-039).
KOKORO_THREADS: int = int(os.environ.get("FRIDAY_TTS_THREADS", "8"))


def is_disabled() -> bool:
    """True if the panic switch is engaged (file present or env var set)."""
    return PANIC_FILE.exists() or bool(os.environ.get(PANIC_ENV))
