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
