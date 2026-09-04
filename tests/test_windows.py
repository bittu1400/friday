"""Tests for friday.tools.windows (Phase 4a, ADR-129)."""

from __future__ import annotations

import json
import subprocess

import pytest

from friday.tools import windows


def test_list_windows_empty(monkeypatch: pytest.MonkeyPatch):
    class FakeProc:
        returncode = 0
        stdout = "[]"

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeProc())
    assert windows.list_windows() == "No windows are open."


def test_list_windows_populated(monkeypatch: pytest.MonkeyPatch):
    clients = [
        {"mapped": True, "hidden": False, "class": "foot", "workspace": {"name": "1"}},
        {"mapped": True, "hidden": False, "class": "firefox", "workspace": {"name": "2"}},
    ]
    class FakeProc:
        returncode = 0
        stdout = json.dumps(clients)

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeProc())
    res = windows.list_windows()
    assert "You have 2 open windows: foot on workspace 1, and firefox on workspace 2." in res


def test_focus_app_found(monkeypatch: pytest.MonkeyPatch):
    clients = [
        {"mapped": True, "hidden": False, "class": "brave-browser", "address": "0x123", "title": "Brave"},
    ]
    dispatched = []

    def fake_run(argv, **kw):
        class FakeProc:
            returncode = 0
            stdout = json.dumps(clients) if "clients" in argv else "ok"
        if "dispatch" in argv:
            dispatched.append(argv)
        return FakeProc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    ok, spoken = windows.focus_app("browser")
    assert ok is True
    assert "Focused Brave." in spoken
    assert len(dispatched) == 1
    assert 'hl.dsp.focus{window="address:0x123"}' in dispatched[0][2]


def test_focus_app_not_found(monkeypatch: pytest.MonkeyPatch):
    clients = [
        {"mapped": True, "hidden": False, "class": "foot", "address": "0x123", "title": "Terminal"},
    ]
    dispatched = []

    def fake_run(argv, **kw):
        class FakeProc:
            returncode = 0
            stdout = json.dumps(clients) if "clients" in argv else "ok"
        if "dispatch" in argv:
            dispatched.append(argv)
        return FakeProc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    ok, spoken = windows.focus_app("discord")
    assert ok is False
    assert "No open window found for Discord." in spoken
    assert len(dispatched) == 0
