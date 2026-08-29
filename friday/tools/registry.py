"""The static tool registry (ADR-007): a frozen map from tool_id to a
ToolSpec. The model emits an opaque tool_id from a closed enum and typed
params; CODE in this file — never the model — builds the argv. Adding a
capability is a code change plus a test, by design (that friction is the
feature).

Only tools that dispatch a *subprocess* live here: the launch tools. The
memory tools (`remember_preference`/`forget_preference`) act on the SQLite
store, not a subprocess, so they are handled in the turn loop (G4), not
through this registry. `web_search` (needs SearXNG, G7) is a valid plan
action with no entry yet — the caller shows it as not-yet-wired.

Risk classes are `read_only`, `reversible`, `irreversible`. Phase 1 ships
only the first two (FR-33); a registry test asserts no irreversible entry
exists.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Literal, Mapping
from urllib.parse import quote_plus, urlparse

from ..errors import PolicyRejected
from .apps import APPS

_BROWSER = APPS["browser"].argv[0]  # youtube opens in the browser (brave)
_HOME = str(Path.home())


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    risk: Literal["read_only", "reversible", "irreversible"]
    build_argv: Callable[[Mapping[str, str]], list[str]]
    target_binary: Callable[[Mapping[str, str]], str]  # for the which() preflight
    display: Callable[[Mapping[str, str]], str]  # for the outcome template
    cwd: str
    env: Mapping[str, str]
    timeout_s: float
    # A LAUNCH (GUI app) must outlive the turn, so it is fire-and-forget and
    # its exit code is not a verdict (ADR-043). A COMMAND exits, and its exit
    # code IS the verdict — it is waited on and bounded by timeout_s (ADR-073).
    detach: bool = False


# --- youtube query hardening (ADR-027, FR-39x) -----------------------------
# THE single audited exception to "the model never supplies a string that
# reaches a command". Five cheap layers. Reject, never strip — stripping
# turns hostile input into plausible input.
_ALLOWED = re.compile(r"^[A-Za-z0-9 \-'&,.]{1,100}$")


def youtube_url(query: str) -> str:
    q = unicodedata.normalize("NFKC", query)  # AS-9-style confusables fold here
    if not _ALLOWED.fullmatch(q):  # AS-13 metachars, AS-14 length
        raise PolicyRejected()
    url = "https://www.youtube.com/results?search_query=" + quote_plus(q)
    parsed = urlparse(url)  # AS-16: re-assert after construction
    if parsed.scheme != "https" or parsed.netloc != "www.youtube.com":
        raise PolicyRejected()
    return url


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
#                             amendment; the "broken braves" symptom).
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
def _build_app_env() -> Mapping[str, str]:
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
    return MappingProxyType(env)


_APP_ENV = _build_app_env()


# These three used to fall back to a default on an unrecognized value, which
# meant an off-vocabulary param did the WRONG thing instead of nothing: volume
# went UP for any direction that wasn't "down"/"mute"/"unmute", brightness went
# DOWN for anything that wasn't exactly "up", and media fell back to play-pause.
# The spoken outcome still named what the user asked for, so it reported an
# action that never happened (ADR-009). The schema enum is the first gate; these
# raise instead of guessing, because invariant #5 requires BOTH layers.
def _build_volume_argv(p: Mapping[str, str]) -> list[str]:
    d = p.get("direction", "").lower()
    if d == "up":
        return ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%+"]
    elif d == "down":
        return ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%-"]
    elif d in ("mute", "toggle_mute"):
        return ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"]
    elif d == "unmute":
        return ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"]
    raise PolicyRejected(f"Unknown volume direction: {d!r}")


def _build_brightness_argv(p: Mapping[str, str]) -> list[str]:
    d = p.get("direction", "").lower()
    if d == "up":
        return ["brightnessctl", "set", "+5%"]
    elif d == "down":
        return ["brightnessctl", "set", "5%-"]
    raise PolicyRejected(f"Unknown brightness direction: {d!r}")


def _build_media_argv(p: Mapping[str, str]) -> list[str]:
    ctrl = p.get("action", "").lower()
    mapping = {
        "play_pause": "play-pause",
        "play": "play",
        "pause": "pause",
        "next": "next",
        "previous": "previous",
        "stop": "stop",
    }
    if ctrl not in mapping:
        raise PolicyRejected(f"Unknown media action: {ctrl!r}")
    return ["playerctl", mapping[ctrl]]


def _build_wifi_argv(p: Mapping[str, str]) -> list[str]:
    state = p.get("state", "on").lower()
    if state not in ("on", "off"):
        raise PolicyRejected("Invalid wifi state")
    return ["nmcli", "radio", "wifi", state]


# Hyprland 0.56 routes `hyprctl dispatch` through Lua: the old positional form
# (`dispatch workspace 2`) is parsed as Lua and dies with "')' expected near
# '2'". The comment above already recorded this for `dispatch exec`; the two
# tools below used the same broken form and nobody swept for siblings (OQ-38).
#
# An argv element is therefore now a small Lua program, which is exactly the
# thing invariant #2 exists to prevent — so no parameter is ever formatted into
# one. Every reachable dispatch string is built HERE, at import, from code-owned
# literals, and a param can only SELECT one. A value outside the closed set is
# rejected; it cannot be interpolated, escaped, or "sanitized". See ADR-074.
_LUA_DISPATCH: Mapping[str, str] = MappingProxyType(
    {
        **{f"workspace:{i}": f"hl.dsp.focus{{workspace={i}}}" for i in range(1, 11)},
        # `hl.dsp.focus` names directions in full: it rejects anything but
        # left/right/up/down ("invalid direction \"zzz\"", measured 2026-08-29).
        "focus_left": 'hl.dsp.focus{direction="left"}',
        "focus_right": 'hl.dsp.focus{direction="right"}',
        "focus_up": 'hl.dsp.focus{direction="up"}',
        "focus_down": 'hl.dsp.focus{direction="down"}',
        "fullscreen": "hl.dsp.window.fullscreen{}",
        "close": "hl.dsp.window.close{}",
    }
)


def _build_workspace_argv(p: Mapping[str, str]) -> list[str]:
    dispatch = _LUA_DISPATCH.get(f"workspace:{p.get('workspace', '1')}")
    if dispatch is None:  # fail CLOSED: not a member of the closed set
        raise PolicyRejected("Invalid workspace number")
    return ["hyprctl", "dispatch", dispatch]


def _build_window_argv(p: Mapping[str, str]) -> list[str]:
    action = p.get("action", "fullscreen").lower()
    dispatch = _LUA_DISPATCH.get(action)
    # `hl.dsp.window.close{}` is the Lua form of the old `killactive`: it closes
    # the FOCUSED window and takes no selector. (`closewindow` needs a regex or
    # address; "active" is not one and silently matched nothing.)
    if dispatch is None or action.startswith("workspace:"):
        raise PolicyRejected(f"Unknown window action: {action}")
    return ["hyprctl", "dispatch", dispatch]


# User file placeholders (agreed 2026-08-24). Can be overridden on demand.
FILE_REGISTRY: dict[str, str] = {
    "notes": str(Path.home() / "notes.md"),
    "config": str(Path.home() / ".config" / "hypr" / "hyprland.conf"),
    "todo": str(Path.home() / "todo.md"),
}


def _build_file_argv(p: Mapping[str, str]) -> list[str]:
    # The planner passes phrasings ("my config", "my todo"), not bare keys, so
    # match the one closed-registry key the phrase names. Fail CLOSED on a miss
    # (invariant #2, manifest A11): an unregistered alias is not openable — it
    # must never silently fall back to notes.md and open the wrong file.
    raw = p.get("alias", "").lower()
    key = next((k for k in FILE_REGISTRY if k in raw), None)
    if key is None:
        raise PolicyRejected(f"Unknown file alias: {raw!r}")
    return [APPS["editor"].argv[0], FILE_REGISTRY[key]]


REGISTRY: Mapping[str, ToolSpec] = MappingProxyType(
    {
        "open_app": ToolSpec(
            tool_id="open_app",
            risk="reversible",
            build_argv=lambda p: list(APPS[p["app"]].argv),
            target_binary=lambda p: APPS[p["app"]].argv[0],
            display=lambda p: APPS[p["app"]].display,
            cwd=_HOME,
            env=_APP_ENV,
            timeout_s=5.0,
            detach=True,  # GUI launch: fire-and-forget (ADR-043)
        ),
        "open_youtube": ToolSpec(
            tool_id="open_youtube",
            risk="reversible",
            build_argv=lambda p: [_BROWSER, "https://www.youtube.com"],
            target_binary=lambda p: _BROWSER,
            display=lambda p: "YouTube",
            cwd=_HOME,
            env=_APP_ENV,
            timeout_s=5.0,
            detach=True,  # GUI launch: fire-and-forget (ADR-043)
        ),
        "youtube_search": ToolSpec(  # ADR-027, THE exception
            tool_id="youtube_search",
            risk="reversible",
            build_argv=lambda p: [_BROWSER, youtube_url(p["query"])],
            target_binary=lambda p: _BROWSER,
            display=lambda p: f"YouTube for {' '.join(p['query'].split())[:40]}",
            cwd=_HOME,
            env=_APP_ENV,
            timeout_s=5.0,
            detach=True,  # GUI launch: fire-and-forget (ADR-043)
        ),
        "system_volume": ToolSpec(
            tool_id="system_volume",
            risk="reversible",
            build_argv=_build_volume_argv,
            target_binary=lambda p: "wpctl",
            display=lambda p: f"volume {p.get('direction', 'changed')}",
            cwd=_HOME,
            env=_APP_ENV,
            timeout_s=3.0,
        ),
        "system_brightness": ToolSpec(
            tool_id="system_brightness",
            risk="reversible",
            build_argv=_build_brightness_argv,
            target_binary=lambda p: "brightnessctl",
            display=lambda p: f"brightness {p.get('direction', 'changed')}",
            cwd=_HOME,
            env=_APP_ENV,
            timeout_s=3.0,
        ),
        "system_media": ToolSpec(
            tool_id="system_media",
            risk="reversible",
            build_argv=_build_media_argv,
            target_binary=lambda p: "playerctl",
            display=lambda p: f"media {p.get('action', 'playback')}",
            cwd=_HOME,
            env=_APP_ENV,
            timeout_s=3.0,
        ),
        "system_wifi": ToolSpec(
            tool_id="system_wifi",
            risk="reversible",
            build_argv=_build_wifi_argv,
            target_binary=lambda p: "nmcli",
            display=lambda p: f"Wi-Fi {p.get('state', 'changed')}",
            cwd=_HOME,
            env=_APP_ENV,
            timeout_s=4.0,
        ),
        "hypr_workspace": ToolSpec(
            tool_id="hypr_workspace",
            risk="reversible",
            build_argv=_build_workspace_argv,
            target_binary=lambda p: "hyprctl",
            display=lambda p: f"workspace {p.get('workspace', '1')}",
            cwd=_HOME,
            env=_APP_ENV,
            timeout_s=3.0,
        ),
        "hypr_window": ToolSpec(
            tool_id="hypr_window",
            risk="reversible",
            build_argv=_build_window_argv,
            target_binary=lambda p: "hyprctl",
            display=lambda p: f"window {p.get('action', 'action')}",
            cwd=_HOME,
            env=_APP_ENV,
            timeout_s=3.0,
        ),
        "file_open": ToolSpec(
            tool_id="file_open",
            risk="reversible",
            build_argv=_build_file_argv,
            target_binary=lambda p: APPS["editor"].argv[0],
            display=lambda p: f"file {p.get('alias', 'document')}",
            cwd=_HOME,
            env=_APP_ENV,
            timeout_s=5.0,
            detach=True,  # GUI launch: fire-and-forget (ADR-043)
        ),
    }
)

NOT_YET_WIRED: Mapping[str, str] = MappingProxyType({})

