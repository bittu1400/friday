"""`prefs` CLI (FR-56): list, export, forget, reset.

The keyboard surface for preferences. Per ADR-036 the split is here: a bare
`prefs forget <key>` soft-expires (same as the voice tool), and only the
explicit `--hard` / `reset --yes` hard-deletes. `list`/`export` are
read-only.

    uv run python -m friday.prefs_cli list
    uv run python -m friday.prefs_cli export
    uv run python -m friday.prefs_cli forget <key> [--hard]
    uv run python -m friday.prefs_cli reset --yes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config
from .store.db import Database
from .store.prefs import PrefStore


def _store(db_path: Path) -> PrefStore:
    return PrefStore(Database(db_path))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="prefs")
    ap.add_argument("--db", type=Path, default=config.MEMORY_DB)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="show active preferences")
    sub.add_parser("export", help="print active preferences as JSON")

    p_forget = sub.add_parser("forget", help="forget one preference")
    p_forget.add_argument("key")
    p_forget.add_argument(
        "--hard", action="store_true", help="delete the row (irreversible)"
    )

    p_reset = sub.add_parser("reset", help="clear all preferences")
    p_reset.add_argument("--yes", action="store_true", help="required to confirm")

    args = ap.parse_args(argv)
    store = _store(args.db)

    if args.cmd == "list":
        active = store.active()
        if not active:
            print("(no preferences)")
        for k, v in active.items():
            print(f"{k}={v}")
        return 0

    if args.cmd == "export":
        sys.stdout.write(store.export())
        return 0

    if args.cmd == "forget":
        if args.hard:
            n = store.forget_hard(args.key)
            verb = "deleted"
        else:
            n = store.forget_soft(args.key)
            verb = "forgotten (soft)"
        print(f"{verb}: {args.key}" if n else f"no such preference: {args.key}")
        return 0 if n else 1

    if args.cmd == "reset":
        if not args.yes:
            print("refusing to reset without --yes", file=sys.stderr)
            return 2
        n = store.reset_hard()
        print(f"reset: {n} preference(s) cleared")
        return 0

    return 2  # unreachable: subparser is required


if __name__ == "__main__":
    raise SystemExit(main())
