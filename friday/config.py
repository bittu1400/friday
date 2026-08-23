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


def is_disabled() -> bool:
    """True if the panic switch is engaged (file present or env var set)."""
    return PANIC_FILE.exists() or bool(os.environ.get(PANIC_ENV))
