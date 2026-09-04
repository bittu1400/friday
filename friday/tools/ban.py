"""Hard ban on destructive commands & risk tiers (G12, ADR-057).

Permanent tool-layer denylist enforcing invariant #10. Any resolved argv
matching a banned binary or destructive verb is rejected before execution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from friday.errors import PolicyRejected


BANNED_BINARIES: frozenset[str] = frozenset(
    {
        "rm", "rmdir", "pacman", "yay", "paru", "dd", "mkfs", "fdisk", "parted",
        "sh", "bash", "zsh", "dash", "fish", "killall", "pkill", "sudo", "su",
        "shutdown", "reboot", "poweroff", "systemctl", "chmod", "chown",
        # Privilege escalators. `sudo`/`su` were here from G12; the graphical
        # ones were not, and `.desktop` files escalate through pkexec, not
        # sudo (`Exec=pkexec gparted`). Found 2026-09-02 by the desktop scan's
        # own test, which is why it is fixed HERE and not in the scanner: this
        # is the gate the executor uses too, so a binary banned for the
        # launcher must be banned for every dispatch (ADR-097).
        "pkexec", "gksu", "gksudo", "doas", "run0",
    }
)

# Binaries that execute an ARBITRARY following command. Only `argv[0]` was ever
# inspected, so every one of these walked straight through the denylist —
# measured 2026-09-02 (audit F5): `env python3 /tmp/x.py`, `flatpak run org.x.App`
# and `/usr/bin/distrobox-enter -n box -- bash` all PASSED while bare `bash` was
# banned. This is reachable from real files, not only in theory:
# `~/.local/share/applications` is user-writable and already holds an
# `env`-prefixed entry (`todoist`), so part of the argv Friday executes is
# determined by files this project does not write.
#
# Terminals are on this list because `-e` / `-x` is exactly the same escape:
# 15 of the 165 scanned ids are `foot -e <something>`, so `foot` is a wrapper
# in practice whatever its category says.
#
# The resolution is deliberately NOT a per-wrapper option grammar. `env` alone
# has NAME=VALUE assignments plus -i/-u/-C/-S, `timeout` takes a duration
# first, `nice` takes -n, `systemd-run` takes properties — five parsers, each
# able to be subtly wrong in the direction of letting something through. When
# the head is a wrapper we instead check EVERY remaining token, which needs no
# grammar and is strictly stronger. It can only false-positive when a wrapper
# is handed a banned NAME as data, which for a wrapper is the dangerous case
# anyway. Measured against the live enum on 2026-09-04: 0 of the 165 app argvs
# carry a banned token past index 0, so nothing on this machine changes.
WRAPPER_BINARIES: frozenset[str] = frozenset(
    {
        "env", "flatpak", "distrobox", "distrobox-enter", "toolbox", "toolbox-enter",
        "nohup", "setsid", "stdbuf", "nice", "ionice", "timeout", "xargs",
        "systemd-run", "dbus-run-session", "unshare", "chroot", "script",
        "ssh", "strace", "ltrace", "gdb", "valgrind", "watch",
        # terminal emulators: `-e` / `-x` runs the rest as a command
        "foot", "footclient", "kitty", "alacritty", "wezterm", "xterm", "urxvt",
        "st", "konsole", "gnome-terminal", "xfce4-terminal", "terminator",
        "tilix", "ghostty",
    }
)


BANNED_SUBSTRINGS: frozenset[str] = frozenset(
    {
        "rm -", "rmdir", "mkfs.", "dd if=", ">", "|", "&&", ";", "`", "$("
    }
)


def assert_not_banned(argv: Sequence[str]) -> None:
    """Assert that the given argv does not contain banned binaries or destructive verbs."""
    if not argv:
        raise PolicyRejected("Empty argv")

    binary_name = Path(argv[0]).name.lower()

    if binary_name in BANNED_BINARIES:
        raise PolicyRejected(f"Banned binary: {binary_name}")

    # F5: a wrapper at the head means the REAL command is further along, so the
    # check above proved nothing about what actually runs. Check the rest too.
    #
    # The `--opt=value` split is not cosmetic. `flatpak run --command=sh org.x.App`
    # runs a shell inside the sandbox and the bare-token form does not see it,
    # because the basename of "--command=sh" is "--command=sh". Measured against
    # the live table on 2026-09-04: 8 of the 165 argvs carry an `=` token
    # (`--ozone-platform-hint=auto`, `DESKTOPINTEGRATION=false`, `--idle=yes` …)
    # and none has a banned right-hand side, so splitting costs nothing here.
    if binary_name in WRAPPER_BINARIES:
        for token in argv[1:]:
            for part in (token, token.split("=", 1)[1] if "=" in token else token):
                wrapped = Path(part).name.lower()
                if wrapped in BANNED_BINARIES:
                    raise PolicyRejected(
                        f"Banned binary behind wrapper {binary_name}: {wrapped}"
                    )

    full_cmd = " ".join(argv).lower()
    for sub in BANNED_SUBSTRINGS:
        if sub in full_cmd:
            raise PolicyRejected(f"Banned command pattern: {sub}")
