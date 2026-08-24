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
from .audio import aec, vad, wake
from .audio.capture import Recorder
from .audio.state import State
from .audio.stt import FasterWhisperBackend, Transcriber
from .audio.tts import Speaker
from .audio.wake import FarEndRef, WakeCallbacks, WakeListener
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


def _build(args, loop_holder: dict[str, asyncio.AbstractEventLoop]) -> tuple[Daemon, Database]:  # noqa: ANN001
    db = Database(config.MEMORY_DB)
    sweep_retention(db, retention_days=config.RETENTION_DAYS)
    prefs, audit = PrefStore(db), AuditLog(db)

    far_ref = FarEndRef()

    speaker = None
    if not args.no_voice:
        speaker = Speaker.create(
            config.KOKORO_MODEL, config.KOKORO_VOICES,
            voice=config.KOKORO_VOICE, fallback=config.KOKORO_VOICE_FALLBACK,
            threads=config.KOKORO_THREADS,
            far_ref=far_ref,
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

    wake_listener = None
    if not args.no_wake and config.WAKE_ENABLED:
        aec_proc = aec.create(enabled=config.AEC_ENABLED, sample_rate=16000, frame_ms=config.AEC_FRAME_MS)
        vad_detector = vad.create(mode=config.VAD_AGGRESSIVENESS, sample_rate=16000)
        wake_det = wake.create_detector(config.WAKE_MODEL, threshold=config.WAKE_THRESHOLD)

        def _schedule(coro_fn):
            def cb() -> None:
                loop = loop_holder.get("loop")
                if loop is not None and loop.is_running():
                    asyncio.run_coroutine_threadsafe(coro_fn(), loop)
            return cb

        callbacks = WakeCallbacks(
            on_wake=_schedule(lambda: state_holder["d"].on_wake()),
            on_speech_end=_schedule(lambda: state_holder["d"].on_speech_end()),
            on_barge=_schedule(lambda: state_holder["d"].on_barge()),
        )
        wake_listener = WakeListener(
            detector=wake_det,
            vad=vad_detector,
            aec=aec_proc,
            callbacks=callbacks,
            far_ref=far_ref,
            threshold=config.WAKE_THRESHOLD,
            frame_len=(16000 * config.WAKE_FRAME_MS) // 1000,
            refractory_s=config.WAKE_REFRACTORY_S,
            is_idle=lambda: state_holder["d"].state.is_idle,
            is_speaking=lambda: state_holder["d"].state.state is State.SPEAKING,
        )

    d = Daemon(
        client=LlamaClient(base_url=args.base_url), recorder=recorder,
        transcriber=transcriber, speaker=speaker, prefs=prefs, audit=audit,
        dry_run=args.dry_run, connected=connected,
        wake_listener=wake_listener,
    )
    state_holder["d"] = d  # close the gate closure over the built daemon
    return d, db


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="friday-voice")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-voice", action="store_true", help="do not load Kokoro")
    ap.add_argument("--no-wake", action="store_true", help="disable hands-free wake word")
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

    loop_holder: dict[str, asyncio.AbstractEventLoop] = {}
    d, db = _build(args, loop_holder)

    async def _runner():
        loop_holder["loop"] = asyncio.get_running_loop()
        await d.run()

    try:
        asyncio.run(_runner())
    except KeyboardInterrupt:
        pass
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

