"""Desktop notification adapter via notify-send (G11, ADR-056).

Sends desktop notifications to Hyprland/mako/dunst fail-soft.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess

log = logging.getLogger(__name__)


def notify(title: str, message: str, urgency: str = "normal") -> bool:
    """Send a desktop notification using notify-send."""
    cmd = shutil.which("notify-send")
    if not cmd:
        log.debug("notify-send not found; notification dropped")
        return False

    urgency_clean = urgency if urgency in ("low", "normal", "critical") else "normal"
    argv = [cmd, "-u", urgency_clean, "-a", "Friday", title, message]

    try:
        res = subprocess.run(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
            check=False,
        )
        return res.returncode == 0
    except Exception as exc:
        log.debug("Failed to invoke notify-send (%s)", exc)
        return False


async def anotify(title: str, message: str, urgency: str = "normal") -> bool:
    """`notify` off the event loop (audit H6).

    `subprocess.run(..., timeout=2)` blocks for as long as the notification
    daemon takes to answer — up to two whole seconds. Both callers are places
    where the loop must stay responsive: the FR-5 rejection path, which by
    definition fires while a turn is already running and can burst, and the
    scheduler's poll loop, where it delayed every later due reminder.

    Looks `notify` up through the module namespace at call time, so the suite's
    autouse stub (tests/conftest.py) still intercepts it.
    """
    return await asyncio.to_thread(notify, title, message, urgency)
