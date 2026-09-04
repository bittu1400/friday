"""The one explicit environment every Friday subprocess runs under (FR-32, F4).

Invariant #3 says "argv list, shell=False, minimal explicit env, bounded
timeout. **No exceptions.**" Until 2026-09-04 there was exactly one compliant
call site — the executor's detached app launch — and five that inherited the
daemon's entire environment: `clipboard.read_clipboard`, `clipboard.set_clipboard`,
`typer` (wtype and ydotool) and `proactive.notifier.notify`. An invariant with
five unlabelled exceptions is a preference (audit F4).

This module holds the env those six now share. It was `registry._build_app_env`
and moved here unchanged; `registry._APP_ENV` is an alias so the ten call sites
that already used it did not move.

**What it deliberately does NOT carry**, and why the five clients still work:

- `YDOTOOL_SOCKET` — unset in the daemon's own environment (measured 2026-09-04
  against `/proc/<MainPID>/environ`), so ydotool has always used its compiled
  default and inherits nothing. `XDG_RUNTIME_DIR` is here, which is what the
  socket path is built from.
- Everything else the daemon holds — the Qt/GDK/SDL backend hints, `SHELL`,
  `JOURNAL_STREAM`, the systemd `WATCHDOG_*` and `NOTIFY_SOCKET` pair. The
  last two matter: a child that inherited `NOTIFY_SOCKET` can talk to systemd
  as if it were the service.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

_HOME = str(Path.home())


# Minimal explicit env (FR-32): PATH + HOME so the binary resolves and lands
# somewhere sane, plus the session/compositor addressing a GUI client needs:
#   WAYLAND_DISPLAY           the compositor socket name
#   XDG_RUNTIME_DIR           its directory
#   DISPLAY                   the X11 / XWayland display. Chromium and
#                             Electron apps default to the X11 Ozone backend
#                             here, and WITHOUT it Brave prints "Missing X
#                             server or $DISPLAY" and exits before a window
#                             ever appears — while the detached spawn still
#                             reports ok. Measured 2026-08-25: every
#                             "Opened Brave." Friday has ever spoken was a lie.
#   DBUS_SESSION_BUS_ADDRESS  the session bus — a single-instance app (Brave/
#                             Chromium) reaches its already-running instance
#                             over it, hands off, and exits 0. WITHOUT it the
#                             handoff exits non-zero and the launcher misreads
#                             a successful open as a failure ("That didn't
#                             work.") while a window still opened (ADR-043
#                             amendment; the "broken braves" symptom). It is
#                             also how `notify-send` reaches the notification
#                             daemon at all.
# PATH is copied from the daemon's own environment (falling back to a sane
# default) so the spawned child resolves a binary the SAME way the which()
# preflight in the executor does — otherwise preflight and exec can disagree
# (brave lives in /opt/…, not /usr/bin). Nothing else is inherited.
#
# We spawn the app binary DIRECTLY, not through `hyprctl dispatch exec`
# (ADR-043): Hyprland 0.56 turned `hyprctl dispatch` into a Lua shorthand and
# the old `dispatch exec <app>` form no longer parses (`')' expected near
# '<app>'`). A direct detached spawn is compositor- and CLI-version-independent
# and matches hyprctl's old fire-and-forget semantics. All copied vars are
# session addressing from the daemon's own environment, never built from
# params, so the env stays explicit and minimal.
def _build_subprocess_env() -> Mapping[str, str]:
    env = {"PATH": os.environ.get("PATH") or "/usr/bin:/bin", "HOME": _HOME}
    for key in (
        "WAYLAND_DISPLAY",
        "XDG_RUNTIME_DIR",
        "DBUS_SESSION_BUS_ADDRESS",
        "DISPLAY",
        # Without this hyprctl cannot find the compositor at all — it prints
        # "HYPRLAND_INSTANCE_SIGNATURE not set! (is hyprland running?)" and
        # exits 1, which the executor swallowed until ADR-073. Both Hyprland
        # tools had therefore never worked (OQ-38). The systemd unit already
        # passes it through; the env copy simply never listed it.
        "HYPRLAND_INSTANCE_SIGNATURE",
    ):
        val = os.environ.get(key)
        if val:
            env[key] = val
    # A UTF-8 locale. Without LANG a console program inherits the "C" locale
    # and btop exits 1 immediately; `foot` exits with its child, so the
    # detached launch reported ok while no window ever appeared — measured
    # 2026-09-02 against the real executor, the ADR-043 shape again (ADR-097).
    # Code-owned constant fallback, never param-derived.
    env["LANG"] = os.environ.get("LANG") or "C.UTF-8"
    return MappingProxyType(env)


SUBPROCESS_ENV: Mapping[str, str] = _build_subprocess_env()
