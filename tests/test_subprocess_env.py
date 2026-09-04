"""Invariant #3, fourth clause: "minimal explicit env. No exceptions." (F4)

Until 2026-09-04 exactly ONE subprocess call site passed `env=`. The other five
— `clipboard` x2, `typer` x2 (wtype and ydotool) and `proactive.notifier` —
inherited the daemon's entire environment, `NOTIFY_SOCKET` and the systemd
`WATCHDOG_*` pair included. An invariant with five unlabelled exceptions is a
preference.

The executor's own env has had a test since ADR-117/M4
(`test_executor.py::test_subprocess_gets_the_minimal_explicit_env_only`).
This file is that test for the other five, and it is written the same way: it
captures the kwargs actually handed to `subprocess.run` and asserts the env is
`SUBPROCESS_ENV` itself, so deleting any one `env=` line turns it red.
"""

from __future__ import annotations

import subprocess

import pytest

from friday.proactive import notifier
from friday.tools import clipboard, typer
from friday.tools.env import SUBPROCESS_ENV


class _Recorder:
    """Stands in for `subprocess.run` and remembers how it was called."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: bytes = b""):
        self.calls: list[dict] = []
        self._rc, self._out, self._err = returncode, stdout, stderr

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": argv, **kwargs})
        return subprocess.CompletedProcess(
            argv, self._rc, stdout=self._out, stderr=self._err
        )

    @property
    def env(self):
        assert self.calls, "subprocess.run was never called"
        return self.calls[-1].get("env")


def _run_and_capture(monkeypatch, module, which_returns: str, call) -> _Recorder:
    rec = _Recorder()
    monkeypatch.setattr(module.shutil, "which", lambda _name: which_returns)
    monkeypatch.setattr(module.subprocess, "run", rec)
    call()
    return rec


def test_clipboard_read_uses_the_one_explicit_env(monkeypatch):
    rec = _run_and_capture(
        monkeypatch, clipboard, "/usr/bin/wl-paste", clipboard.read_clipboard
    )
    assert rec.env is SUBPROCESS_ENV


def test_clipboard_write_uses_the_one_explicit_env(monkeypatch):
    rec = _run_and_capture(
        monkeypatch, clipboard, "/usr/bin/wl-copy", lambda: clipboard.set_clipboard("x")
    )
    assert rec.env is SUBPROCESS_ENV


def test_wtype_uses_the_one_explicit_env(monkeypatch):
    # `which` answers for wtype, so the first branch runs and returns on rc 0.
    rec = _run_and_capture(
        monkeypatch, typer, "/usr/bin/wtype", lambda: typer.type_text("hello")
    )
    assert rec.calls[0]["argv"][0] == "/usr/bin/wtype"
    assert rec.env is SUBPROCESS_ENV


def test_ydotool_uses_the_one_explicit_env(monkeypatch):
    # No wtype on this machine (measured 2026-08-30), so answer `which` only for
    # ydotool and the second branch is the one that runs.
    rec = _Recorder()
    monkeypatch.setattr(
        typer.shutil, "which", lambda name: "/usr/bin/ydotool" if name == "ydotool" else None
    )
    monkeypatch.setattr(typer.subprocess, "run", rec)
    typer.type_text("hello")
    assert rec.calls[0]["argv"][0] == "/usr/bin/ydotool"
    assert rec.env is SUBPROCESS_ENV


def test_notify_uses_the_one_explicit_env(monkeypatch):
    # conftest stubs `notifier.notify` autouse so no test can pop a real toast.
    # This one needs the real function, so it goes through `__wrapped__`-free
    # access to the module attribute captured before the stub: re-import it.
    import importlib

    real = importlib.reload(notifier)
    rec = _Recorder()
    monkeypatch.setattr(real.shutil, "which", lambda _n: "/usr/bin/notify-send")
    monkeypatch.setattr(real.subprocess, "run", rec)
    real.notify("title", "message")
    assert rec.env is SUBPROCESS_ENV


def test_the_explicit_env_is_minimal_and_carries_no_systemd_handles(monkeypatch):
    """The point of an explicit env is what it LEAVES OUT. A child that inherits
    `NOTIFY_SOCKET` can talk to systemd as if it were `friday.service`, and one
    that inherits `JOURNAL_STREAM` trips H8's disclosure guard."""
    for leaked in ("NOTIFY_SOCKET", "JOURNAL_STREAM", "WATCHDOG_PID", "WATCHDOG_USEC",
                   "INVOCATION_ID", "MANAGERPID", "SHELL"):
        assert leaked not in SUBPROCESS_ENV

    assert set(SUBPROCESS_ENV) <= {
        "PATH", "HOME", "LANG", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR",
        "DBUS_SESSION_BUS_ADDRESS", "DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE",
    }
