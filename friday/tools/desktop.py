"""XDG desktop-entry scan: the machine's installed applications, turned into
launchable ids (ADR-097).

This is the one place in the project where a file NOT written by us decides
what Friday can launch, so every rule here fails CLOSED — an entry that
cannot be proven safe is never offered, rather than offered and rejected at
execution. The model still only ever emits a key from a closed set and CODE
builds the argv (invariant #2); the only thing that changed is that the set
is now derived from the system instead of typed by hand (five apps, ADR-032).

Three skip rules, all chosen by the user 2026-09-02:

  1. root-escalating Exec  — `pkexec gparted` pops a polkit password prompt,
     so a misheard command becomes "type your root password".
  2. shell Exec            — `Exec=sh -c "..."` cannot become an argv list
     without either dropping the shell (changing semantics) or running a
     shell string (breaking invariant #3).
  3. Settings panels       — NOT skipped: flagged `confirm`, so they keep
     working behind the handshake ADR-057 already built.

Rules 1 and 2 delegate to `ban.assert_not_banned`, the same gate the executor
uses, so a banned binary cannot be banned in one place and launchable in the
other. On this machine today neither rule matches any of the 150 installed
entries — they are prophylactic, and cost nothing until a package ships one.

Stdlib only: `configparser` reads the INI-ish entry format, `shlex` splits
Exec. No `pyxdg`; it would be a dependency for ~60 lines (rule 7).
"""

from __future__ import annotations

import configparser
import logging
import re
import shlex
import shutil
from pathlib import Path
from typing import Final, NamedTuple, Sequence

from ..errors import PolicyRejected
from .ban import assert_not_banned

log = logging.getLogger(__name__)


class DesktopApp(NamedTuple):
    argv: tuple[str, ...]
    display: str
    # Categories name a Settings panel: launchable, but only after an explicit
    # yes. The user's call — refusing outright would mean Bluetooth and input
    # settings could never be opened by voice at all.
    confirm: bool = False
    # Terminal=true: the binary has no window of its own. apps.py wraps it in
    # the terminal emulator it already owns rather than spawning it headless,
    # which is the ADR-043 "reported ok, nothing appeared" shape.
    needs_terminal: bool = False


# Launcher placeholders (freedesktop Exec key). A literal "%u" left in argv is
# passed to the binary as an argument.
_FIELD_CODE: Final = re.compile(r"^%[a-zA-Z]$")
_NON_KEY: Final = re.compile(r"[^a-z0-9]+")


def app_key(name: str) -> str:
    return _NON_KEY.sub("_", name.strip().casefold()).strip("_")


def _is_settings(categories: str) -> bool:
    # "Settings", "HardwareSettings", "X-GNOME-SystemSettings" — every panel on
    # this machine (gufw, blueman, cups, fcitx5) carries one of these tokens.
    return any(t == "Settings" or t.endswith("Settings") for t in categories.split(";"))


def _parse(path: Path) -> tuple[str, DesktopApp] | None:
    """One `.desktop` file -> (desktop id, entry), or None if it is skipped."""
    cp = configparser.RawConfigParser(strict=False)  # dup keys are common; no %-interp
    cp.read_string(path.read_text(encoding="utf-8", errors="replace"))
    # ONLY the [Desktop Entry] section. firefox.desktop carries three Exec
    # lines; the other two belong to [Desktop Action ...] right-click entries.
    if not cp.has_section("Desktop Entry"):
        return None
    sec = cp["Desktop Entry"]

    if sec.get("Type", "").strip() != "Application":
        return None
    if sec.get("NoDisplay", "").strip().lower() == "true":
        return None
    if sec.get("Hidden", "").strip().lower() == "true":
        return None

    try_exec = sec.get("TryExec", "").strip()
    if try_exec and shutil.which(try_exec) is None and not Path(try_exec).exists():
        return None

    exec_line = sec.get("Exec", "").strip()
    if not exec_line:
        return None
    argv = [t for t in shlex.split(exec_line) if not _FIELD_CODE.fullmatch(t)]
    if not argv:
        return None

    try:
        assert_not_banned(argv)  # skip rules 1 and 2, via the executor's own gate
    except PolicyRejected as exc:
        log.debug("desktop entry %s skipped: %s", path.name, exc)
        return None

    name = sec.get("Name", "").strip() or path.stem
    key = app_key(name) or app_key(path.stem)
    if not key:
        return None
    return key, DesktopApp(
        argv=tuple(argv),
        display=name,
        confirm=_is_settings(sec.get("Categories", "")),
        needs_terminal=sec.get("Terminal", "").strip().lower() == "true",
    )


def scan(dirs: Sequence[Path]) -> dict[str, DesktopApp]:
    """Scan `dirs` in ascending precedence — a later directory's entry replaces
    an earlier one with the same file name, which is how XDG makes
    `~/.local/share/applications` override `/usr/share/applications`.
    """
    by_id: dict[str, tuple[str, DesktopApp]] = {}
    for d in dirs:
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.desktop")):
            try:
                parsed = _parse(path)
            except Exception as exc:  # noqa: BLE001 — a bad file on this machine
                # must not take the daemon down at import time. One entry lost,
                # logged, scan continues.
                log.debug("desktop entry %s unreadable: %s", path.name, exc)
                continue
            if parsed is not None:
                by_id[path.name] = parsed

    apps: dict[str, DesktopApp] = {}
    for _, (key, entry) in sorted(by_id.items()):
        apps.setdefault(key, entry)  # first wins; two Names can normalise alike
    return apps


def default_dirs() -> list[Path]:
    """XDG application directories, ascending precedence (user last)."""
    import os

    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    roots = [*reversed(data_dirs.split(":")), home]
    return [Path(r) / "applications" for r in roots if r]
