"""The static tool registry (ADR-007): a frozen map from tool_id to a
ToolSpec. The model emits an opaque tool_id from a closed enum and typed
params; CODE in this file — never the model — builds the argv. Adding a
capability is a code change plus a test, by design (that friction is the
feature).

Only tools that actually *execute* at G3 live here: the launch tools.
`web_search` (needs SearXNG, G7) and the memory tools (need the DB, G4) are
valid plan actions but have no registry entry yet — the caller shows them
as not-yet-wired rather than dispatching.

Risk classes are `read_only`, `reversible`, `irreversible`. Phase 1 ships
only the first two (FR-33); a registry test asserts no irreversible entry
exists.
"""

from __future__ import annotations

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


# Minimal explicit env (FR-32): PATH so hyprctl and the target resolve, HOME
# so a launched terminal/editor lands somewhere sane. Nothing inherited.
_HYPR_ENV = MappingProxyType({"PATH": "/usr/bin:/bin", "HOME": _HOME})


def _hypr(*args: str) -> list[str]:
    return ["hyprctl", "dispatch", "exec", *args]


REGISTRY: Mapping[str, ToolSpec] = MappingProxyType(
    {
        "open_app": ToolSpec(
            tool_id="open_app",
            risk="reversible",
            build_argv=lambda p: _hypr(*APPS[p["app"]].argv),
            target_binary=lambda p: APPS[p["app"]].argv[0],
            display=lambda p: APPS[p["app"]].display,
            cwd=_HOME,
            env=_HYPR_ENV,
            timeout_s=5.0,
        ),
        "open_youtube": ToolSpec(
            tool_id="open_youtube",
            risk="reversible",
            build_argv=lambda p: _hypr(_BROWSER, "https://www.youtube.com"),
            target_binary=lambda p: _BROWSER,
            display=lambda p: "YouTube",
            cwd=_HOME,
            env=_HYPR_ENV,
            timeout_s=5.0,
        ),
        "youtube_search": ToolSpec(  # ADR-027, THE exception
            tool_id="youtube_search",
            risk="reversible",
            build_argv=lambda p: _hypr(_BROWSER, youtube_url(p["query"])),
            target_binary=lambda p: _BROWSER,
            display=lambda p: "YouTube",
            cwd=_HOME,
            env=_HYPR_ENV,
            timeout_s=5.0,
        ),
    }
)

# Plan actions that are valid but not executable yet (wired at later gates).
NOT_YET_WIRED: Mapping[str, str] = MappingProxyType(
    {
        "web_search": "web search arrives at G7",
        "remember_preference": "memory arrives at G4",
        "forget_preference": "memory arrives at G4",
    }
)
