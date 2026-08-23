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

# Voice in (G6). Locked by the ADR-041 STT drill (ADR-042): faster-whisper
# `small.en` int8, 8 threads, beam_size=1, hotwords-biased — p95 ~741 ms on
# this CPU (large-v3-turbo failed at 2.7 s; base.en botched app commands;
# distil-large-v3 slower with no accuracy win). CPU only (FR-11, invariant
# #6). int8 beat fp32 here — no AVX-512 penalty for CTranslate2, unlike Kokoro.
STT_MODEL: str = os.environ.get("FRIDAY_STT_MODEL", "small.en")
STT_COMPUTE: str = os.environ.get("FRIDAY_STT_COMPUTE", "int8")
STT_THREADS: int = int(os.environ.get("FRIDAY_STT_THREADS", "8"))
STT_BEAM: int = int(os.environ.get("FRIDAY_STT_BEAM", "1"))  # greedy; = accuracy, faster
STT_SAMPLE_RATE: int = 16000  # whisper's native rate (FR-10 pipeline)
MAX_CAPTURE_S: int = 15  # FR-4 hard cap

# Hotwords bias STT toward Friday's fixed domain (the 5 apps + youtube + pref
# subjects). Measured: fixed neovim/arch misses at no latency cost (ADR-042).
# Keep this tracking the registry — a new app should join this list.
STT_HOTWORDS: str = os.environ.get(
    "FRIDAY_STT_HOTWORDS",
    "Brave, foot, terminal, Visual Studio Code, VLC, mpv, Neovim, Arch Linux, "
    "Kathmandu, lo-fi, jazz, YouTube, dark theme, web search",
)

# PTT control socket (FR-3). A unix socket in the per-user runtime dir (0700
# on Linux) — the Hyprland bind runs `friday-ptt press|release`, which sends
# one line here. It is a local IPC socket, not a network bind (invariant #8
# is about 127.0.0.1 TCP; this touches no network at all).
RUNTIME_DIR: Path = Path(
    os.environ.get("XDG_RUNTIME_DIR", str(STATE_DIR))
) / "friday"
PTT_SOCKET: Path = RUNTIME_DIR / "ptt.sock"


def is_disabled() -> bool:
    """True if the panic switch is engaged (file present or env var set)."""
    return PANIC_FILE.exists() or bool(os.environ.get(PANIC_ENV))
