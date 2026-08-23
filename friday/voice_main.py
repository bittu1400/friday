"""Voice-in entrypoint: `uv run python -m friday.voice_main` (or `just voice`).

Wires the daemon (G6): DB + prefs + audit (G4), llama client (G3), Kokoro
speaker (G5), the mic recorder + faster-whisper transcriber (G6), and the
PTT socket. Everything audio fail-softs: no model or no device leaves that
capability off rather than crashing, so the daemon still answers PTT and
reports what it can.

The Hyprland bind that drives it (OQ-03; the venv python, since the project
ships no console script — ADR: `package = false`):

    bind        = SUPER SHIFT, XF86Assistant, exec, <venv>/bin/python -m friday.ptt_cli press
    bindrelease = SUPER SHIFT, XF86Assistant, exec, <venv>/bin/python -m friday.ptt_cli release
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
import urllib.request

from . import config
from .audio.capture import Recorder
from .audio.stt import FasterWhisperBackend, Transcriber
from .audio.tts import Speaker
from .daemon import Daemon
from .llm.client import LlamaClient
from .logging_config import setup_logging
from .store.audit import AuditLog, sweep_retention
from .store.db import Database
from .store.prefs import PrefStore


def wait_for_llm(base_url: str, timeout_s: float = 30.0, poll_interval_s: float = 1.0) -> bool:
    """Tolerantly wait for llama-server during startup to avoid crash-looping under systemd (G9)."""
    url = f"{base_url.rstrip('/')}/health"
    start = time.monotonic()
    log = logging.getLogger("friday.startup")

    while time.monotonic() - start < timeout_s:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "friday-health/1.0"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("status") in ("ok", "loading model"):
                        log.info("llama-server is ready at %s (status=%s)", base_url, data.get("status"))
                        return True
        except urllib.error.HTTPError as exc:
            if exc.code == 503:
                try:
                    data = json.loads(exc.read().decode("utf-8"))
                    if data.get("status") == "loading model":
                        log.info("llama-server is loading model at %s...", base_url)
                except Exception:
                    pass
        except Exception:
            pass
        log.info("waiting for llama-server at %s...", base_url)
        time.sleep(poll_interval_s)

    log.warning("llama-server at %s not ready within %.1fs; continuing in degraded mode", base_url, timeout_s)
    return False


def _build(args) -> tuple[Daemon, Database]:  # noqa: ANN001
    db = Database(config.MEMORY_DB)
    sweep_retention(db, retention_days=config.RETENTION_DAYS)
    prefs, audit = PrefStore(db), AuditLog(db)

    speaker = None
    if not args.no_voice:
        speaker = Speaker.create(
            config.KOKORO_MODEL, config.KOKORO_VOICES,
            voice=config.KOKORO_VOICE, fallback=config.KOKORO_VOICE_FALLBACK,
            threads=config.KOKORO_THREADS,
        )
    if speaker is None:
        logging.getLogger("friday").warning("no TTS: outcomes will be silent")

    backend = FasterWhisperBackend.create(
        config.STT_MODEL, compute_type=config.STT_COMPUTE, threads=config.STT_THREADS,
        beam=config.STT_BEAM, hotwords=config.STT_HOTWORDS,
    )
    transcriber = Transcriber(backend) if backend is not None else None
    if transcriber is None:
        logging.getLogger("friday").warning("no STT: voice input disabled")

    state_holder: dict[str, Daemon] = {}
    recorder = Recorder(gate=lambda: state_holder["d"].state.mic_open)
    connected = config.SEARCH_CONNECTED_DEFAULT and not args.local
    d = Daemon(
        client=LlamaClient(base_url=args.base_url), recorder=recorder,
        transcriber=transcriber, speaker=speaker, prefs=prefs, audit=audit,
        dry_run=args.dry_run, connected=connected,
    )
    state_holder["d"] = d  # close the gate closure over the built daemon
    return d, db


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="friday-voice")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-voice", action="store_true", help="do not load Kokoro")
    ap.add_argument(
        "--local",
        action="store_true",
        help="start in local mode: web_search refuses (no egress). ADR-046",
    )
    ap.add_argument("--base-url", default=config.LLAMA_BASE_URL)
    ap.add_argument("--log", default="INFO")
    ap.add_argument(
        "--startup-timeout",
        type=float,
        default=30.0,
        help="seconds to wait for llama-server at startup before starting in degraded mode",
    )
    args = ap.parse_args(argv)
    setup_logging(level=args.log)

    # Startup health wait — tolerates llama-server cold start (G9)
    wait_for_llm(args.base_url, timeout_s=args.startup_timeout)

    d, db = _build(args)
    try:
        asyncio.run(d.run())
    except KeyboardInterrupt:
        pass
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
