"""Entrypoint for text mode: `uv run python -m friday` (or `just run`).

G4 wires the persistence store: the DB is opened (migrations applied,
permissions enforced), a retention sweep runs once at startup (ADR-038:
logs only), and the preference store + audit log are handed to the TUI.
Audio, service wiring, and the FSM arrive at later gates.
"""

from __future__ import annotations

import argparse

from . import config
from .audio.tts import Speaker
from .llm.client import LlamaClient
from .store.audit import AuditLog, sweep_retention
from .store.db import Database
from .store.prefs import PrefStore
from .ui.tui import FridayTUI


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="friday")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="print the argv a dispatch would run, without launching anything",
    )
    ap.add_argument(
        "--no-voice", action="store_true", help="text only; do not load Kokoro"
    )
    ap.add_argument(
        "--local",
        action="store_true",
        help="start in local mode: web_search refuses (no egress). ADR-046",
    )
    ap.add_argument("--base-url", default=config.LLAMA_BASE_URL)
    args = ap.parse_args(argv)

    db = Database(config.MEMORY_DB)
    sweep_retention(db, retention_days=config.RETENTION_DAYS)  # logs only
    prefs = PrefStore(db)
    audit = AuditLog(db)

    # Voice out (ADR-039/040). None if --no-voice, model missing, or no audio
    # device — the TUI then runs text-only rather than failing.
    speaker = None
    if not args.no_voice:
        speaker = Speaker.create(
            config.KOKORO_MODEL,
            config.KOKORO_VOICES,
            voice=config.KOKORO_VOICE,
            fallback=config.KOKORO_VOICE_FALLBACK,
            threads=config.KOKORO_THREADS,
        )

    # Connected by default (ADR-046); --local is the opt-out.
    connected = config.SEARCH_CONNECTED_DEFAULT and not args.local
    client = LlamaClient(base_url=args.base_url)
    FridayTUI(
        client, prefs=prefs, audit=audit, speaker=speaker,
        dry_run=args.dry_run, connected=connected,
    ).run()
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
