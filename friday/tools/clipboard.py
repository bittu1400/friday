"""Wayland clipboard read/write via wl-clipboard (G12).

`clipboard_read` and `clipboard_set` act on the Wayland selection through
`wl-paste` / `wl-copy`. Text is passed to `wl-copy` on STDIN, never as an argv
element — so arbitrary clipboard content (pipes, semicolons, backticks) is
copied verbatim and never parsed as a command. subprocess is argv-list,
shell=False, bounded timeout (invariant #3).
"""

from __future__ import annotations

import logging
import shutil
import subprocess

from .. import config

log = logging.getLogger(__name__)


def read_clipboard(timeout_s: float = 2.0) -> str | None:
    """Return the current clipboard text, or None if unavailable/empty-tool."""
    if config.is_disabled():
        return None
    cmd = shutil.which("wl-paste")
    if not cmd:
        return None
    try:
        res = subprocess.run(
            [cmd, "--no-newline"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        return res.stdout
    except Exception as exc:
        log.debug("wl-paste failed: %s", exc)
        return None


def set_clipboard(text: str, timeout_s: float = 2.0) -> bool:
    """Copy `text` into the Wayland clipboard. Text goes on STDIN, not argv."""
    if config.is_disabled():
        return False
    cmd = shutil.which("wl-copy")
    if not cmd:
        log.debug("wl-copy not found; clipboard write dropped")
        return False
    try:
        res = subprocess.run(
            [cmd],
            input=text.encode("utf-8"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout_s,
            check=False,
        )
        return res.returncode == 0
    except Exception as exc:
        log.debug("wl-copy failed: %s", exc)
        return False
