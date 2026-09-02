"""Semantic app id -> (argv, human name). The model only ever emits a
semantic key from the closed enum; this table — never the model — is where a
key becomes a real binary (ADR-007, ADR-032).

Brand resolution lives here and only here: the eval fixtures and the schema
speak in semantic keys ("browser"), so swapping the browser brand is a
one-line change here plus a fixture, not a rewrite (ADR-033).

**Widened 2026-09-02 (ADR-097).** The table was five hand-written apps; it is
now those five PLUS every installed XDG desktop entry that passes the scan in
`desktop.py`. What did NOT change is the shape of the contract: `app` is still
a closed enum, still exact-matched by the validator after NFKC, so a path
(`/bin/sh`), a command injection (`browser; rm -rf ~`) and a Cyrillic
confusable are rejected by the same gate as before (AS-7/AS-8/AS-9). Only the
way the set is *populated* changed — from typed by hand to read from the
machine. The grammar never enumerated param values, so ~100 more ids cost
zero prompt tokens (`prompt.py` lists the common ones and names the rule for
the rest).

The five curated ids always win a collision: they are what the eval fixtures,
the prompt and the habits miner speak.
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Mapping, NamedTuple

from . import desktop


class App(NamedTuple):
    argv: tuple[str, ...]  # the binary + fixed args; NEVER model-supplied
    display: str  # for the outcome template ("Opened {display}.")
    # A Settings panel (see desktop.py). Launchable, but only behind the
    # confirm handshake ADR-057 already built — decided 2026-09-02.
    confirm: bool = False


# The five originals (ADR-032). They keep their semantic ids because the eval
# fixtures, the prompt and the habits miner all speak them.
CURATED: Mapping[str, App] = MappingProxyType(
    {
        "browser": App(("brave",), "Brave"),
        "terminal": App(("foot",), "the terminal"),
        "editor": App(("code",), "VS Code"),
        # Bare `mpv` with no file prints its version and exits 0 (verified),
        # so a launch flashed nothing. --idle=yes keeps it running and
        # --force-window=yes shows an empty player ready for content.
        "video": App(("mpv", "--idle=yes", "--force-window=yes"), "mpv"),
        "vlc": App(("vlc",), "VLC"),
    }
)

# A console program has no window of its own, so spawning it detached would
# start a headless process while Friday says "Opened btop." — the ADR-043
# failure shape. Wrap it in the terminal this table already owns; the argv is
# still built here from code-owned literals, never from a param.
_TERM_WRAP: tuple[str, ...] = (*CURATED["terminal"].argv, "-e")

# Binaries that are wrappers, not applications. `Exec=env DESKTOPINTEGRATION=0
# anytype` is an AppImage idiom on this machine (anytype, todoist) — taking the
# binary name as a second id would make "open env" launch Anytype. The entry
# itself is kept; only the alias is suppressed.
_GENERIC_LAUNCHERS: frozenset[str] = frozenset(
    {"env", "xdg-open", "flatpak", "snap", "gio", "python", "python3", "java"}
)


def build_apps(scanned: Mapping[str, desktop.DesktopApp]) -> dict[str, App]:
    """Merge the scan into the curated table. Curated ids always win."""
    apps: dict[str, App] = {}
    for key, entry in scanned.items():
        argv = (*_TERM_WRAP, *entry.argv) if entry.needs_terminal else entry.argv
        apps[key] = App(argv, entry.display, entry.confirm)

    # A second id per app, taken from its binary's own name, so the spoken
    # word usually matches: "Visual Studio Code" is `code` on the command line
    # and that is what a user says. Never overwrites an existing id.
    for key, entry in list(scanned.items()):
        binary = Path(entry.argv[0]).name
        if binary in _GENERIC_LAUNCHERS:
            continue
        alias = desktop.app_key(binary)
        if alias and alias not in apps:
            apps[alias] = apps[key]

    apps.update(CURATED)  # last, so the five originals cannot be shadowed
    return apps


APPS: Mapping[str, App] = MappingProxyType(
    build_apps(desktop.scan(desktop.default_dirs()))
)
