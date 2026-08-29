"""Invariant #7: raw transcripts / model output never reach disk.

FRIDAY_DEBUG echoes what was heard so a live session can be watched. The
redaction filter only rewrites /home/ paths — it cannot know the message body
IS the transcript — so the file handler must drop these records outright.
"""
import json
import logging

from friday.logging_config import NoDiskFilter, setup_logging


def test_no_disk_records_are_dropped_from_the_log_file(tmp_path):
    log_file = tmp_path / "friday.log"
    root = setup_logging(level="INFO", log_file=str(log_file), console=False)
    log = logging.getLogger("friday.test")

    log.info("[debug] v1 heard=%r", "my bank password is hunter2",
             extra={"no_disk": True})
    log.info("ordinary operational line")
    for h in root.handlers:
        h.flush()

    written = log_file.read_text()
    assert "hunter2" not in written
    assert "heard=" not in written
    assert "ordinary operational line" in written  # normal logging still works
    for line in written.splitlines():
        json.loads(line)  # still valid JSON lines


def test_filter_predicate():
    f = NoDiskFilter()
    rec = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
    assert f.filter(rec) is True
    rec.no_disk = True
    assert f.filter(rec) is False


def test_no_disk_records_are_dropped_from_stderr_under_journald(tmp_path, monkeypatch, capsys):
    """H8: under systemd, stderr IS journald, and journald persists to disk.

    The file handler was the only guarded sink, so the documented debug
    workflow (`FRIDAY_DEBUG=1` under systemd) wrote every transcript to
    /var/log/journal — invariant #7 broken by the very tool built to watch it.
    """
    monkeypatch.setenv("JOURNAL_STREAM", "8:1234567")
    try:
        setup_logging(level="INFO", log_file=str(tmp_path / "friday.log"), console=True)
        logging.getLogger("friday.test").info(
            "[debug] v1 heard=%r", "my bank password is hunter2",
            extra={"no_disk": True},
        )
        logging.getLogger("friday.test").info("ordinary operational line")
        err = capsys.readouterr().err
        assert "hunter2" not in err
        assert "heard=" not in err
        assert "ordinary operational line" in err  # normal console logging survives
    finally:
        logging.getLogger().handlers.clear()


def test_no_disk_records_still_reach_a_plain_terminal(tmp_path, monkeypatch, capsys):
    """Foreground debugging must keep working — the leak is journald, not stderr."""
    monkeypatch.delenv("JOURNAL_STREAM", raising=False)
    try:
        setup_logging(level="INFO", log_file=str(tmp_path / "friday.log"), console=True)
        logging.getLogger("friday.test").info(
            "[debug] v1 heard=%r", "open my browser", extra={"no_disk": True}
        )
        assert "open my browser" in capsys.readouterr().err
    finally:
        logging.getLogger().handlers.clear()


def test_debug_under_journald_warns_that_transcripts_are_suppressed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JOURNAL_STREAM", "8:1234567")
    monkeypatch.setattr("friday.config.DEBUG", True)
    try:
        setup_logging(level="INFO", log_file=str(tmp_path / "friday.log"), console=True)
        assert "FRIDAY_DEBUG is on under systemd" in capsys.readouterr().err
    finally:
        logging.getLogger().handlers.clear()
