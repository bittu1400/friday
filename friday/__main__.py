"""Entrypoint for text mode: `uv run python -m friday` (or `just run`).

G4 wires the persistence store: the DB is opened (migrations applied,
permissions enforced), a retention sweep runs once at startup (ADR-038:
logs only), and the preference store + audit log are handed to the TUI.
Audio, service wiring, and the FSM arrive at later gates.
"""

from __future__ import annotations

import argparse

from . import config
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
    ap.add_argument("--base-url", default=config.LLAMA_BASE_URL)
    args = ap.parse_args(argv)

    db = Database(config.MEMORY_DB)
    sweep_retention(db, retention_days=config.RETENTION_DAYS)  # logs only
    prefs = PrefStore(db)
    audit = AuditLog(db)

    client = LlamaClient(base_url=args.base_url)
    FridayTUI(client, prefs=prefs, audit=audit, dry_run=args.dry_run).run()
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
