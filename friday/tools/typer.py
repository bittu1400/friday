"""Wayland typer using ydotool or wtype (G12, ADR-058).

Types text into the currently focused window on Hyprland/Wayland.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

log = logging.getLogger(__name__)


def type_text(text: str) -> bool:
    """Type text verbatim into the focused Wayland window."""
    if not text:
        return True

    # 1. Check wtype
    wtype = shutil.which("wtype")
    if wtype:
        try:
            res = subprocess.run(
                [wtype, text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3.0,
                check=False,
            )
            if res.returncode == 0:
                return True
        except Exception as exc:
            log.debug("wtype failed: %s", exc)

    # 2. Check ydotool
    ydotool = shutil.which("ydotool")
    if ydotool:
        try:
            res = subprocess.run(
                [ydotool, "type", "--file", "-"],
                input=text.encode("utf-8"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3.0,
                check=False,
            )
            if res.returncode == 0:
                return True
        except Exception as exc:
            log.debug("ydotool failed: %s", exc)

    log.warning("No working Wayland typer found (wtype or ydotool)")
    return False
