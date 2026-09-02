"""Systemd notification and watchdog integration (F11, architecture.md §8).

Provides readiness and periodic heartbeat pings via `$NOTIFY_SOCKET` / `$WATCHDOG_USEC`
so that systemd can detect and recover from a wedged event loop, deadlocked callback,
or stuck state machine.

If NOTIFY_SOCKET is not set (e.g. running standalone or in tests), notifications
safely no-op.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from typing import Optional

log = logging.getLogger("friday.watchdog")


def notify(state: str) -> bool:
    """Send a notification string to systemd via NOTIFY_SOCKET."""
    sock_path = os.environ.get("NOTIFY_SOCKET")
    if not sock_path:
        return False

    # Abstract socket addresses in Linux start with '@'
    if sock_path.startswith("@"):
        sock_path = "\0" + sock_path[1:]

    payload = state.encode("utf-8") if isinstance(state, str) else state
    if not payload.endswith(b"\n"):
        payload += b"\n"

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(sock_path)
            sock.sendall(payload)
            return True
    except Exception as exc:
        log.debug("Failed to send systemd notification (%s): %s", state.strip(), exc)
        return False


def notify_ready() -> bool:
    """Signal READY=1 to systemd (service startup complete)."""
    return notify("READY=1")


def notify_watchdog() -> bool:
    """Signal WATCHDOG=1 heartbeat ping to systemd."""
    return notify("WATCHDOG=1")


def notify_stopping() -> bool:
    """Signal STOPPING=1 to systemd (clean shutdown underway)."""
    return notify("STOPPING=1")


def get_watchdog_interval_s() -> Optional[float]:
    """Get watchdog ping interval in seconds (half of WATCHDOG_USEC), or None if unset."""
    raw = os.environ.get("WATCHDOG_USEC")
    if not raw:
        return None
    try:
        usec = float(raw)
        if usec <= 0:
            return None
        # Ping at half the watchdog deadline
        return max(0.5, (usec / 1_000_000.0) / 2.0)
    except ValueError:
        return None


async def watchdog_task(interval_s: Optional[float] = None) -> None:
    """Async background task that periodically pings the systemd watchdog."""
    interval = interval_s if interval_s is not None else get_watchdog_interval_s()
    if interval is None:
        return

    log.debug("Starting systemd watchdog task (ping interval: %.2fs)", interval)
    try:
        while True:
            await asyncio.sleep(interval)
            notify_watchdog()
    except asyncio.CancelledError:
        log.debug("Systemd watchdog task stopped")
        raise
