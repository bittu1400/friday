"""Semantic app id -> (argv, human name). The model only ever emits a
semantic key from the closed enum; this table — written by hand, never by
the model — is where a key becomes a real binary (ADR-007, ADR-032).

Brand resolution lives here and only here: the eval fixtures and the schema
speak in semantic keys ("browser"), so swapping the browser brand is a
one-line change here plus a fixture, not a rewrite (ADR-033).
"""

from __future__ import annotations

from types import MappingProxyType
from typing import NamedTuple


class App(NamedTuple):
    argv: tuple[str, ...]  # the binary + fixed args; NEVER model-supplied
    display: str  # for the outcome template ("Opened {display}.")


# Five apps (ADR-032). All five binaries verified present on this machine.
APPS = MappingProxyType(
    {
        "browser": App(("brave",), "Brave"),
        "terminal": App(("foot",), "the terminal"),
        "editor": App(("code",), "VS Code"),
        "video": App(("mpv",), "mpv"),
        "vlc": App(("vlc",), "VLC"),
    }
)
