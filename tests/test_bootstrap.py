"""Tests for scripts/bootstrap.py (ADR-107, §10)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from scripts.bootstrap import (
    ModelSpec,
    check_llama_binary,
    check_or_fetch_model,
    check_python_version,
    check_systemd_units,
    compute_sha256,
)


def test_compute_sha256(tmp_path: Path):
    f = tmp_path / "test.bin"
    content = b"hello world 12345"
    f.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()
    assert compute_sha256(f) == expected


def test_check_python_version():
    assert check_python_version() is True


def test_model_check_only_fails_on_missing(tmp_path: Path):
    missing_path = tmp_path / "nonexistent.bin"
    spec = ModelSpec(
        name="Test Model",
        path=missing_path,
        sha256="abc123",
        url="http://example.com/model.bin",
    )
    assert check_or_fetch_model(spec, check_only=True) is False


def test_model_check_only_fails_on_corrupt_hash(tmp_path: Path):
    corrupt_path = tmp_path / "corrupt.bin"
    corrupt_path.write_bytes(b"corrupt contents")
    spec = ModelSpec(
        name="Test Model",
        path=corrupt_path,
        sha256="0000000000000000000000000000000000000000000000000000000000000000",
        url="http://example.com/model.bin",
    )
    assert check_or_fetch_model(spec, check_only=True) is False


def test_model_check_only_passes_on_valid_hash(tmp_path: Path):
    valid_path = tmp_path / "valid.bin"
    content = b"exact model weights binary blob"
    valid_path.write_bytes(content)
    actual_hash = hashlib.sha256(content).hexdigest()

    spec = ModelSpec(
        name="Test Model",
        path=valid_path,
        sha256=actual_hash,
        url="http://example.com/model.bin",
    )
    assert check_or_fetch_model(spec, check_only=True) is True


def test_check_systemd_units():
    assert check_systemd_units() is True


def test_check_llama_binary(tmp_path: Path):
    with patch("scripts.bootstrap.Path") as mock_path:
        fake_binary = MagicMock()
        fake_binary.exists.return_value = False
        mock_path.return_value = fake_binary
        assert check_llama_binary() is False
