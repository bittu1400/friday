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
# somewhere sane, plus the two variables a Wayland client needs to reach the
# compositor — WAYLAND_DISPLAY (the socket name) and XDG_RUNTIME_DIR (its dir).
# Nothing else is inherited. We spawn the app binary DIRECTLY, not through
# `hyprctl dispatch exec` (ADR-043): Hyprland 0.56 turned `hyprctl dispatch`
# into a Lua shorthand and the old `dispatch exec <app>` form no longer parses
# (`')' expected near '<app>'`). A direct detached spawn is compositor- and
# CLI-version-independent, and matches hyprctl's old fire-and-forget semantics
# (it never detected whether the app stayed up either). These vars are
# compositor addressing copied from the daemon's own environment, never built
# from params, so the env stays explicit and minimal.
def _build_app_env() -> Mapping[str, str]:
    env = {"PATH": "/usr/bin:/bin", "HOME": _HOME}
    for key in ("WAYLAND_DISPLAY", "XDG_RUNTIME_DIR"):
        val = os.environ.get(key)
        if val:
            env[key] = val
    return MappingProxyType(env)


_APP_ENV = _build_app_env()


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
        ),
        "youtube_search": ToolSpec(  # ADR-027, THE exception
            tool_id="youtube_search",
            risk="reversible",
            build_argv=lambda p: [_BROWSER, youtube_url(p["query"])],
            target_binary=lambda p: _BROWSER,
            display=lambda p: "YouTube",
            cwd=_HOME,
            env=_APP_ENV,
            timeout_s=5.0,
        ),
    }
)

# Plan actions that are valid but not executable yet (wired at later gates).
# Memory (remember/forget) is wired at G4 in the turn loop, so it is NOT here.
NOT_YET_WIRED: Mapping[str, str] = MappingProxyType(
    {
        "web_search": "web search arrives at G7",
    }
)
