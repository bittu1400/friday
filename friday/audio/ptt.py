"""Push-to-talk over a unix socket (FR-3, ADR-013).

The bind path, not evdev: a Hyprland `bind`/`bindrelease` runs `friday-ptt
press|release`, which connects to this socket and sends one line. The daemon
never observes the keyboard — the compositor tells it a key moved. No
`input` group, no `grab()`, no keylogging risk (ADR-013).

    bind        = SUPER SHIFT, XF86Assistant, exec, friday-ptt press
    bindrelease = SUPER SHIFT, XF86Assistant, exec, friday-ptt release

The wire protocol is one lowercase command per connection, newline optional.
Only the closed set below is honoured; anything else is ignored (fail
closed) — the socket lives in the 0700 per-user runtime dir, but a control
channel still validates its input.
"""

from __future__ import annotations

import asyncio
import os
import socket
from collections.abc import Awaitable, Callable
from pathlib import Path

COMMANDS = frozenset({"press", "release", "cancel"})


def parse_command(raw: bytes) -> str | None:
    """Return the command, or None if it is not in the closed set."""
    cmd = raw.decode("ascii", "replace").strip().lower()
    return cmd if cmd in COMMANDS else None


async def serve(
    path: Path, on_event: Callable[[str], Awaitable[None]]
) -> asyncio.AbstractServer:
    """Bind the PTT socket and dispatch each valid command to `on_event`.

    Returns the running server (caller keeps it alive / closes it). The socket
    is created user-only (0700 dir + a fresh bind); a stale socket file from a
    crashed run is removed first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    if path.exists():
        path.unlink()  # stale socket from a previous run

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout=1.0)
            cmd = parse_command(raw)
            if cmd is not None:
                await on_event(cmd)
        except (asyncio.TimeoutError, ConnectionError):
            pass
        finally:
            writer.close()

    old = os.umask(0o177)  # socket file -> 0600
    try:
        server = await asyncio.start_unix_server(handle, path=str(path))
    finally:
        os.umask(old)
    return server


def send(path: Path, command: str) -> bool:
    """Client side (`friday-ptt <command>`): fire one command, don't wait for
    a reply. Returns False if the daemon isn't listening — a PTT press with no
    daemon should be a quiet no-op, not a traceback in the compositor log."""
    if command not in COMMANDS:
        raise ValueError(f"unknown ptt command: {command!r}")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(str(path))
            s.sendall(command.encode("ascii") + b"\n")
        return True
    except OSError:
        return False
