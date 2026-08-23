"""Tests for the self-test verification suite (friday.md G9, architecture.md §7)."""

import json
from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from friday import config
from friday.selftest import (
    CheckResult,
    Status,
    check_audio_devices,
    check_database,
    check_gpu_arch,
    check_llama_server,
    check_panic_switch,
    check_searxng,
    check_socket_binds,
    run_all_checks,
    run_selftest,
)
from friday.store.db import Database


def test_check_llama_server_pass():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({"status": "ok"}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = check_llama_server("http://127.0.0.1:8080")
        assert res.status is Status.PASS
        assert "Reachable" in res.message


def test_check_llama_server_fail():
    with patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
        res = check_llama_server("http://127.0.0.1:8080")
        assert res.status is Status.FAIL
        assert "Cannot connect" in res.message


def test_check_searxng_pass():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = check_searxng("http://127.0.0.1:8888")
        assert res.status is Status.PASS


def test_check_searxng_fail():
    with patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
        res = check_searxng("http://127.0.0.1:8888")
        assert res.status is Status.FAIL


def test_check_gpu_arch_pass():
    mock_proc = MagicMock()
    mock_proc.stdout = "NVIDIA GeForce RTX 5070 Laptop GPU, 12.0\n"

    with patch("shutil.which", return_value="/usr/bin/nvidia-smi"), patch(
        "subprocess.run", return_value=mock_proc
    ):
        res = check_gpu_arch()
        assert res.status is Status.PASS
        assert "sm_120 verified" in res.message


def test_check_gpu_arch_older_gen():
    mock_proc = MagicMock()
    mock_proc.stdout = "NVIDIA GeForce RTX 4070, 8.9\n"

    with patch("shutil.which", return_value="/usr/bin/nvidia-smi"), patch(
        "subprocess.run", return_value=mock_proc
    ):
        res = check_gpu_arch()
        assert res.status is Status.WARN
        assert "compute 8.9 < 12.0" in res.message


def test_check_database_valid(tmp_path: Path):
    state_dir = tmp_path / "friday_state"
    state_dir.mkdir(mode=0o700)
    db_file = state_dir / "memory.db"
    db = Database(db_file)
    db.close()

    res = check_database(db_file)
    assert res.status is Status.PASS
    assert "schema v1" in res.message


def test_check_database_bad_perms(tmp_path: Path):
    state_dir = tmp_path / "open_dir"
    state_dir.mkdir(mode=0o777)
    db_file = state_dir / "memory.db"
    db = Database(db_file)
    db.close()
    state_dir.chmod(0o777)

    res = check_database(db_file)
    assert res.status is Status.FAIL
    assert "0700" in res.message


def test_check_panic_switch_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "PANIC_FILE", tmp_path / "DISABLED")
    monkeypatch.delenv("FRIDAY_DISABLED", raising=False)

    res = check_panic_switch()
    assert res.status is Status.PASS
    assert "Disarmed" in res.message


def test_check_panic_switch_engaged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    panic_file = tmp_path / "DISABLED"
    panic_file.touch()
    monkeypatch.setattr(config, "PANIC_FILE", panic_file)

    res = check_panic_switch()
    assert res.status is Status.WARN
    assert "PANIC SWITCH ENGAGED" in res.message


def test_check_socket_binds_clean():
    mock_proc = MagicMock()
    mock_proc.stdout = (
        "LISTEN 0 512 127.0.0.1:8080 0.0.0.0:*\n"
        "LISTEN 0 4096 127.0.0.1:8888 0.0.0.0:*\n"
    )

    with patch("shutil.which", return_value="/usr/bin/ss"), patch(
        "subprocess.run", return_value=mock_proc
    ):
        res = check_socket_binds()
        assert res.status is Status.PASS


def test_check_socket_binds_wildcard_fails():
    mock_proc = MagicMock()
    mock_proc.stdout = "LISTEN 0 512 0.0.0.0:8080 0.0.0.0:*\n"

    with patch("shutil.which", return_value="/usr/bin/ss"), patch(
        "subprocess.run", return_value=mock_proc
    ):
        res = check_socket_binds()
        assert res.status is Status.FAIL
        assert "Wildcard bind detected" in res.message


def test_run_selftest_overall(capsys):
    with patch("friday.selftest.check_llama_server", return_value=CheckResult("llama", Status.PASS, "ok")), \
         patch("friday.selftest.check_searxng", return_value=CheckResult("searxng", Status.PASS, "ok")), \
         patch("friday.selftest.check_gpu_arch", return_value=CheckResult("gpu", Status.PASS, "ok")), \
         patch("friday.selftest.check_database", return_value=CheckResult("db", Status.PASS, "ok")), \
         patch("friday.selftest.check_audio_devices", return_value=CheckResult("audio", Status.PASS, "ok")), \
         patch("friday.selftest.check_panic_switch", return_value=CheckResult("panic", Status.PASS, "ok")), \
         patch("friday.selftest.check_socket_binds", return_value=CheckResult("sockets", Status.PASS, "ok")):
        code = run_selftest()
        assert code == 0
        captured = capsys.readouterr()
        assert "[PASSED]" in captured.out
