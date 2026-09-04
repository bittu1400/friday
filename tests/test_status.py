"""Tests for friday.tools.status (Phase 4a, ADR-129)."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from friday.tools import status


def test_get_battery_live_or_fallback():
    msg = status.get_battery()
    assert isinstance(msg, str)
    assert "battery" in msg.lower() or "percent" in msg.lower()


def test_get_battery_mocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bat_dir = tmp_path / "BAT0"
    bat_dir.mkdir()
    (bat_dir / "capacity").write_text("85\n")
    (bat_dir / "status").write_text("Discharging\n")

    monkeypatch.setattr(status, "Path", lambda p: tmp_path if p == "/sys/class/power_supply" else Path(p))
    msg = status.get_battery()
    assert msg == "Battery is at 85 percent, Discharging."


def test_get_disk():
    msg = status.get_disk()
    assert "gigabytes free" in msg
    assert "on root" in msg


def test_get_ram_live():
    msg = status.get_ram()
    assert "gigabytes available" in msg
    assert "RAM" in msg


def test_get_ram_mocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       16384000 kB\nMemFree:         2048000 kB\nMemAvailable:    8192000 kB\n")

    monkeypatch.setattr(status, "Path", lambda p: meminfo if p == "/proc/meminfo" else Path(p))
    msg = status.get_ram()
    assert "7.8 gigabytes available out of 15.6 gigabytes RAM." in msg


def test_get_network_mocked(monkeypatch: pytest.MonkeyPatch):
    class FakeProc:
        returncode = 0
        stdout = "wifi:connected:MyHomeWiFi\nethernet:unavailable:\n"

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeProc())
    msg = status.get_network()
    assert msg == "Wi-Fi connected to MyHomeWiFi."


def test_get_network_disconnected(monkeypatch: pytest.MonkeyPatch):
    class FakeProc:
        returncode = 0
        stdout = "wifi:disconnected:\n"

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeProc())
    msg = status.get_network()
    assert msg == "Network is disconnected."


def test_get_window_mocked(monkeypatch: pytest.MonkeyPatch):
    class FakeProc:
        returncode = 0
        stdout = '{"mapped": true, "class": "firefox", "title": "Mozilla Firefox"}'

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeProc())
    msg = status.get_window()
    assert "Active window is firefox with title Mozilla Firefox." in msg


def test_get_media_mocked(monkeypatch: pytest.MonkeyPatch):
    class FakeProc:
        returncode = 0
        stdout = "Queen - Bohemian Rhapsody\n"

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeProc())
    msg = status.get_media()
    assert msg == "Now playing: Queen - Bohemian Rhapsody."


def test_query_status_targets():
    for target in ("battery", "disk", "ram", "network", "window", "media", "all"):
        res = status.query_status(target)
        assert isinstance(res, str)
        assert len(res) > 0
