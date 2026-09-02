"""Tests for systemd watchdog and notification (F11, ADR-107)."""

from __future__ import annotations

import asyncio
import os
import socket
from pathlib import Path
import pytest

from friday.watchdog import (
    get_watchdog_interval_s,
    notify,
    notify_ready,
    notify_stopping,
    notify_watchdog,
    watchdog_task,
)


def test_notify_noop_when_no_socket(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
    assert notify("READY=1") is False
    assert notify_ready() is False
    assert notify_watchdog() is False
    assert notify_stopping() is False


def test_notify_delivers_to_unix_dgram_socket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sock_path = str(tmp_path / "notify.sock")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    srv.bind(sock_path)
    srv.setblocking(False)

    try:
        monkeypatch.setenv("NOTIFY_SOCKET", sock_path)

        assert notify_ready() is True
        data, _ = srv.recvfrom(1024)
        assert data == b"READY=1\n"

        assert notify_watchdog() is True
        data, _ = srv.recvfrom(1024)
        assert data == b"WATCHDOG=1\n"

        assert notify_stopping() is True
        data, _ = srv.recvfrom(1024)
        assert data == b"STOPPING=1\n"
    finally:
        srv.close()


def test_get_watchdog_interval(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("WATCHDOG_USEC", raising=False)
    assert get_watchdog_interval_s() is None

    # 10s timeout -> 5s ping interval
    monkeypatch.setenv("WATCHDOG_USEC", "10000000")
    assert get_watchdog_interval_s() == 5.0

    # 1s timeout -> minimum 0.5s ping interval
    monkeypatch.setenv("WATCHDOG_USEC", "1000000")
    assert get_watchdog_interval_s() == 0.5

    # Invalid values
    monkeypatch.setenv("WATCHDOG_USEC", "-500")
    assert get_watchdog_interval_s() is None

    monkeypatch.setenv("WATCHDOG_USEC", "not_a_number")
    assert get_watchdog_interval_s() is None


def test_watchdog_task_periodic_pings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sock_path = str(tmp_path / "watchdog.sock")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    srv.bind(sock_path)
    srv.setblocking(False)

    monkeypatch.setenv("NOTIFY_SOCKET", sock_path)

    async def runner():
        task = asyncio.create_task(watchdog_task(interval_s=0.05))
        await asyncio.sleep(0.12)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    try:
        asyncio.run(runner())
        # Should have received at least 2 WATCHDOG=1 pings
        received = []
        while True:
            try:
                data, _ = srv.recvfrom(1024)
                received.append(data)
            except BlockingIOError:
                break
        assert len(received) >= 2
        assert all(msg == b"WATCHDOG=1\n" for msg in received)
    finally:
        srv.close()
