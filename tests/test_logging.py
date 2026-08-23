"""Tests for structured JSON logging and redaction (FR-43, architecture.md §7)."""

import json
import logging
from pathlib import Path
import pytest

from friday.logging_config import RedactingJsonFormatter, setup_logging


def test_redaction_removes_home_paths(tmp_path: Path):
    log_file = tmp_path / "test.log"
    setup_logging(log_file=log_file, level="INFO", console=False)
    log = logging.getLogger("test.redaction")

    log.info("Loaded file from /home/someuser/secret/project/data.json")
    log.info("Error in /home/bittusah/Projects/Personal/Intern/friday/turn.py:42")

    content = log_file.read_text(encoding="utf-8")
    assert "/home/" not in content
    assert "~/secret/project/data.json" in content or "~" in content


def test_structured_fields_in_json(tmp_path: Path):
    log_file = tmp_path / "test.log"
    setup_logging(log_file=log_file, level="INFO", console=False)
    log = logging.getLogger("test.structured")

    log.info(
        "Planned action",
        extra={
            "rid": "req_12345",
            "stage": "plan",
            "ms": 842,
            "tool": "open_app",
            "decision": "allow",
        },
    )

    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["rid"] == "req_12345"
    assert data["stage"] == "plan"
    assert data["ms"] == 842
    assert data["tool"] == "open_app"
    assert data["decision"] == "allow"
    assert data["lvl"] == "info"
    assert "ts" in data


def test_log_rotation(tmp_path: Path):
    log_file = tmp_path / "rotate.log"
    # Set small max_bytes so rotation triggers quickly
    setup_logging(log_file=log_file, level="INFO", max_bytes=200, backup_count=3, console=False)
    log = logging.getLogger("test.rotate")

    for i in range(20):
        log.info(f"Message number {i:03d} to trigger size-based rotation of log files")

    # Check that backup files were generated
    backups = list(tmp_path.glob("rotate.log*"))
    assert len(backups) > 1
    assert any(b.name == "rotate.log.1" for b in backups)


def test_fr43_log_scrape_no_home_anywhere(tmp_path: Path):
    """FR-43: Raw exception text, stack traces, and paths are never logged unredacted.
    Log scrape test finds no `/home/` in friday.log."""
    log_file = tmp_path / "friday.log"
    setup_logging(log_file=log_file, level="INFO", console=False)
    log = logging.getLogger("test.fr43")

    try:
        raise ValueError("Crash while reading /home/bittusah/.config/app.conf")
    except Exception:
        log.exception("Handled unexpected failure")

    log.warning("Config path is /home/alice/data/test.yml")
    log.error("Fatal error loading /home/bob/models/qwen.gguf")

    content = log_file.read_text(encoding="utf-8")
    assert "/home/" not in content
