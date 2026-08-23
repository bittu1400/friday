"""Entrypoint for text mode: `uv run python -m friday` (or `just run`).

Audio, service wiring, and the FSM arrive at later gates; G3 wires just the
text turn loop behind the TUI.
"""

from __future__ import annotations

import argparse

from . import config
from .llm.client import LlamaClient
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

    client = LlamaClient(base_url=args.base_url)
    FridayTUI(client, dry_run=args.dry_run).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
