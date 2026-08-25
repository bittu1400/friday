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

# Search (G7, ADR-045/046). SearXNG on loopback is the ONLY egress (FR-60,
# invariant #8). The URL is fixed to 127.0.0.1 — not configurable to a remote
# host by design; the env override exists only to move the local port.
SEARXNG_URL: str = os.environ.get("FRIDAY_SEARXNG_URL", "http://127.0.0.1:8888")
SEARCH_TIMEOUT_S: float = float(os.environ.get("FRIDAY_SEARCH_TIMEOUT_S", "8.0"))  # FR-64
SEARCH_MAX_RESULTS: int = 5     # FR-62
SEARCH_MAX_TOKENS: int = 1500   # FR-62 (a word-count proxy in the sanitizer)
# Connected by default (ADR-046): web_search works out of the box. Local mode
# (no egress; search refuses audibly) is the opt-out, toggled at runtime.
SEARCH_CONNECTED_DEFAULT: bool = os.environ.get("FRIDAY_SEARCH_LOCAL") is None

# The persistence store (FR-50). Mode 0600, in the 0700 state dir; both are
# enforced by store/db.py on open, not assumed.
MEMORY_DB: Path = STATE_DIR / "memory.db"

# Observability & logging (architecture.md §7, FR-43).
# Structured JSON lines to ~/.local/state/friday/friday.log, rotated at 10 MB, 5 files.
LOG_FILE: Path = Path(os.environ.get("FRIDAY_LOG_FILE", STATE_DIR / "friday.log"))
LOG_MAX_BYTES: int = int(os.environ.get("FRIDAY_LOG_MAX_BYTES", str(10 * 1024 * 1024)))  # 10 MB
LOG_BACKUP_COUNT: int = int(os.environ.get("FRIDAY_LOG_BACKUP_COUNT", "5"))

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

# Live-eval visibility only. When set, the daemon logs the transcript and the
# chosen action to the terminal (a StreamHandler — NEVER a file), so a spoken
# clip can be scored. Off by default; FR-26 (no transcript to DISK) still holds.
DEBUG: bool = bool(os.environ.get("FRIDAY_DEBUG"))

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

# Toggle debounce (OQ-03 reopen / ADR-044). The chosen trigger (XF86Presentation
# on this laptop) is a tap-only key that machine-guns press events while held
# (~50-140 ms apart) and can double-fire a single tap. `toggle` collapses any
# events within this window into one, so one deliberate tap = one flip. Must be
# shorter than the gap between two intentional taps (start, then stop after
# speaking) — 0.4 s clears the burst without swallowing a real second tap.
PTT_DEBOUNCE_S: float = float(os.environ.get("FRIDAY_PTT_DEBOUNCE_S", "0.4"))

# Voice in — hands-free (G10, ADR-055/060/061/062). All CPU (invariant #6).
WAKE_ENABLED: bool = os.environ.get("FRIDAY_WAKE_DISABLE") is None
_WAKE_DIR: Path = _DATA_DIR / "models" / "wake"
WAKE_MODEL: Path = _WAKE_DIR / "hey_jarvis.onnx"   # ADR-061; SHA256 pinned in ADR-061
WAKE_THRESHOLD: float = float(os.environ.get("FRIDAY_WAKE_THRESHOLD", "0.5"))
WAKE_FRAME_MS: int = 20            # detector/VAD frame size; must divide evenly at 16 kHz
WAKE_REFRACTORY_S: float = 1.5     # ignore repeat wake hits within this window (debounce)

# VAD end-of-utterance for wake-initiated capture (no key release exists).
VAD_END_SILENCE_S: float = 0.8     # trailing silence that ends a capture
VAD_MIN_SPEECH_S: float = 0.3      # ignore sub-this blips (barge-in + end-of-speech)
VAD_AGGRESSIVENESS: int = 2        # webrtcvad 0-3

# Voice barge-in (FR-7). OFF by default since 2026-08-25 (ADR-064): the AEC
# delivers only about -5 to -15 dB on this machine's real acoustic path
# (measured; -52 dB on a clean synthetic echo), so the barge VAD cannot tell
# Friday's own voice from the user's and cut every reply off mid-sentence.
# PTT remains the interrupt. A better echo canceller is being researched;
# this flag is how voice barge-in comes back once one is chosen.
BARGE_VAD_ENABLED: bool = os.environ.get("FRIDAY_BARGE_VAD_ENABLE") is not None

# AEC (ADR-060). Far-end reference = TTS playback.
AEC_ENABLED: bool = os.environ.get("FRIDAY_AEC_DISABLE") is None
AEC_FRAME_MS: int = 10             # per ADR-060's chosen library

# Speaker verification (G13, ADR-059). All CPU (invariant #6).
SPEAKER_VERIFY_ENABLED: bool = os.environ.get("FRIDAY_SPEAKER_VERIFY_ENABLE") is not None
_SPEAKER_DIR: Path = _DATA_DIR / "models" / "speaker"
SPEAKER_MODEL: Path = _SPEAKER_DIR / "3dspeaker_campplus.onnx"
VOICEPRINT_FILE: Path = STATE_DIR / "voiceprint.npy"
SPEAKER_SIMILARITY_THRESHOLD: float = float(
    os.environ.get("FRIDAY_SPEAKER_THRESHOLD", "0.75")
)
SPEAKER_ENROLL_UTTERANCES: int = 10  # User decision (2026-08-24): 10 utterances


def is_disabled() -> bool:
    """True if the panic switch is engaged (file present or env var set)."""
    return PANIC_FILE.exists() or bool(os.environ.get(PANIC_ENV))


