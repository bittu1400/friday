"""The two unit directives that decide whether a launched app actually runs.

Both were found the same evening, both by asking systemd rather than reading
the file, and both are the kind of line a later "harden the service" pass would
put back without knowing what it costs.

D29 (ADR-114): children inherit the service cgroup, so KillMode=control-group
SIGKILLed every app Friday launched whenever the daemon stopped or restarted.

D30 (ADR-115): PrivateTmp=yes gave the daemon a private empty /tmp. Chromium
keeps its singleton SOCKET in /tmp and only a symlink to it in the profile under
$HOME, so a Brave launched by the daemon saw the shared lock, failed to reach
the socket, and exited 0 in ~50 ms with no window — reported as a successful
launch. It also hid /tmp/.X11-unix.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

UNIT = Path(__file__).resolve().parents[1] / "deploy" / "systemd" / "friday.service"


def _directives() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in UNIT.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "[")):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def test_unit_file_exists() -> None:
    assert UNIT.is_file(), f"the deployed unit is a symlink to {UNIT}"


def test_private_tmp_is_not_enabled() -> None:
    """D30. A GUI app's session IPC lives in /tmp; a private one breaks it."""
    d = _directives()
    assert d.get("PrivateTmp", "no").lower() not in {"yes", "true", "1", "on"}, (
        "PrivateTmp gives the daemon an empty /tmp, so a Brave it launches "
        "cannot reach the singleton socket the user's running Brave created "
        "there. It exits 0 with no window and the launch is reported OK "
        "(ADR-115). Setting this back re-breaks every browser launch."
    )


def test_tmp_is_writable_by_the_service() -> None:
    """D30, second half. Removing PrivateTmp made /tmp visible but READ-ONLY,
    because ProtectSystem=strict mounts everything not in ReadWritePaths
    read-only and PrivateTmp had been supplying the only writable /tmp.

    That is not enough: connecting to a unix socket needs write access to it,
    and Chromium creates its own /tmp/org.chromium.Chromium.* when it is the
    first instance. It also pushed `tempfile.gettempdir()` down its fallback
    chain to the WorkingDirectory, so every daemon start dropped two
    `tmp*/libespeak-ng.so` directories into the repo.
    """
    d = _directives()
    if d.get("ProtectSystem") == "strict":
        assert "/tmp" in d.get("ReadWritePaths", "").split(), (
            "ProtectSystem=strict without /tmp in ReadWritePaths leaves the "
            "daemon a read-only /tmp, which breaks the Chromium singleton "
            "handoff and sends tempfile into the working directory (ADR-115)"
        )


def test_kill_mode_is_process() -> None:
    """D29. Otherwise a restart SIGKILLs every app Friday ever launched."""
    assert _directives().get("KillMode") == "process", (
        "systemd's default is control-group, which kills the whole cgroup — "
        "and launched apps are in it, because a fork cannot leave a cgroup "
        "(ADR-114)"
    )


def test_watchdog_and_notify_stay_paired() -> None:
    """WatchdogSec does nothing under Type=simple, and that shipped once."""
    d = _directives()
    if "WatchdogSec" in d:
        assert d.get("Type") == "notify", "WatchdogSec requires Type=notify"


def test_ort_telemetry_is_disabled_in_the_unit() -> None:
    """ADR-112: onnxruntime transmits on import unless this is set first."""
    body = UNIT.read_text()
    assert re.search(r"^Environment=ORT_DISABLE_TELEMETRY=1$", body, re.M)
