"""Wayland typer using ydotool or wtype (G12, ADR-058).

Types text into the currently focused window on Hyprland/Wayland.

**Why the timeout is computed and not a constant (D22, ADR-091).** ydotool types
one key at a time: `--key-delay` between keys plus `--key-hold` between each
key's down and up. At the defaults (20 + 20) that is a measured **40.2 ms per
character**, dead linear. A fixed `timeout=3.0` therefore truncated every
dictation longer than **74 characters** — and `subprocess.run` enforces a
timeout with SIGKILL, so it killed ydotool *between a key down and its key up*.
`ydotoold` owns the uinput device and outlives the client, so the key stayed
held and the compositor auto-repeated it forever. One fixed constant produced
both "dictation stops mid-sentence" and "it types the last letter for ever".

So: the rate is pinned explicitly rather than inherited from ydotool's
defaults, and the timeout is derived from the text length with a wide margin.
The timeout now only fires on a genuine hang, never on a long sentence.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

from .. import config

log = logging.getLogger(__name__)


# Pinned, not inherited. Measured on this machine: 20/20 = 40.1 ms/char,
# 12/12 = 24.3, 8/8 = 16.3. 8 ms is ~2.5x faster than stock and still five
# times slower than the compositor's own repeat rate, which is the margin
# that keeps characters from being dropped.
_KEY_DELAY_MS = 8
_KEY_HOLD_MS = 8

# Budget per character for the timeout: ~3x the measured 16.3 ms/char cost, so
# a slow machine or a loaded event loop cannot trip it. Plus a fixed floor for
# process startup and the uinput round-trip.
_MS_PER_CHAR_BUDGET = 50
_TIMEOUT_FLOOR_S = 5.0


def _timeout_for(text: str) -> float:
    return _TIMEOUT_FLOOR_S + len(text) * _MS_PER_CHAR_BUDGET / 1000.0


def type_text(text: str) -> bool:
    """Type text verbatim into the focused Wayland window."""
    if config.is_disabled():
        log.debug("panic switch engaged; typing dropped")
        return False
    if not text:
        return True

    timeout_s = _timeout_for(text)
    tried: list[str] = []

    # 1. wtype. Not installed on this machine as of 2026-08-30, so this branch
    #    is dormant here — but keep it correct: `--` stops wtype parsing a
    #    transcript that happens to start with "-" as its own options (D11).
    wtype = shutil.which("wtype")
    if wtype:
        tried.append("wtype")
        try:
            res = subprocess.run(
                [wtype, "--", text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout_s,
                check=False,
            )
            if res.returncode == 0:
                return True
            log.warning("wtype exited %d for %d chars", res.returncode, len(text))
        except subprocess.TimeoutExpired:
            # Killed mid-type: a key may be left held down. Say so plainly —
            # the old message blamed a missing binary for this exact case.
            log.error(
                "wtype timed out after %.1fs on %d chars and was killed; "
                "a key may be stuck down",
                timeout_s, len(text),
            )
        except OSError as exc:
            log.warning("wtype failed: %s", exc)

    # 2. ydotool. Needs ydotoold running; it owns the uinput device.
    ydotool = shutil.which("ydotool")
    if ydotool:
        tried.append("ydotool")
        try:
            res = subprocess.run(
                [
                    ydotool, "type",
                    "--key-delay", str(_KEY_DELAY_MS),
                    "--key-hold", str(_KEY_HOLD_MS),
                    "--file", "-",
                ],
                input=text.encode("utf-8"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=timeout_s,
                check=False,
            )
            if res.returncode == 0:
                return True
            log.warning(
                "ydotool exited %d for %d chars: %s",
                res.returncode, len(text), res.stderr.decode("utf-8", "replace")[:200],
            )
        except subprocess.TimeoutExpired:
            log.error(
                "ydotool timed out after %.1fs on %d chars and was killed; "
                "a key may be stuck down (is ydotoold running?)",
                timeout_s, len(text),
            )
        except OSError as exc:
            log.warning("ydotool failed: %s", exc)

    if not tried:
        log.warning("No Wayland typer installed (need wtype or ydotool)")
    else:
        log.warning("Wayland typer(s) %s present but none succeeded", ", ".join(tried))
    return False
