"""Desktop notification adapter via notify-send (G11, ADR-056).

Sends desktop notifications to Hyprland/mako/dunst fail-soft.
"""

from __future__ import annotations

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
