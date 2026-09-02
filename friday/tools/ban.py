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

BANNED_SUBSTRINGS: frozenset[str] = frozenset(
    {
        "rm -", "rmdir", "mkfs.", "dd if=", ">", "|", "&&", ";", "`", "$("
    }
)


def assert_not_banned(argv: Sequence[str]) -> None:
    """Assert that the given argv does not contain banned binaries or destructive verbs."""
    if not argv:
        raise PolicyRejected("Empty argv")

    binary_path = argv[0]
    binary_name = Path(binary_path).name.lower()

    if binary_name in BANNED_BINARIES:
        raise PolicyRejected(f"Banned binary: {binary_name}")

    full_cmd = " ".join(argv).lower()
    for sub in BANNED_SUBSTRINGS:
        if sub in full_cmd:
            raise PolicyRejected(f"Banned command pattern: {sub}")
