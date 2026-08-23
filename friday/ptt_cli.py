"""`friday-ptt press|release|cancel` — the client the Hyprland bind runs.

Deliberately tiny and dependency-free on the hot path: a keypress must not
pay import cost or block the compositor. Sends one line to the daemon's unix
socket and exits. If the daemon is down, it exits 0 quietly — a dead PTT key
is not an error worth logging on every press.
"""

from __future__ import annotations

import sys

from . import config
from .audio import ptt


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in ptt.COMMANDS:
        print(f"usage: friday-ptt {{{'|'.join(sorted(ptt.COMMANDS))}}}", file=sys.stderr)
        return 2
    ptt.send(config.PTT_SOCKET, args[0])  # quiet no-op if daemon is down
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
