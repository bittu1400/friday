"""Observability & structured logging (architecture.md §7, FR-43).

Structured JSON lines to `~/.local/state/friday/friday.log`, rotated at 10 MB,
5 files. Every line carries request_id / stage information when available.

Redaction filter (FR-43):
    - Absolute /home/ paths are replaced with `~`
    - Raw transcripts, thoughts, and sensitive values are never logged unredacted
"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import sys
import time
from typing import Any

from . import config
from .store.audit import redact

_STRUCTURED_FIELDS = (
    "rid",
    "request_id",
    "stage",
    "ms",
    "tool",
    "decision",
    "outcome",
    "duration_ms",
)


class NoDiskFilter(logging.Filter):
    """Drops records marked `extra={"no_disk": True}`.

    Invariant #7 / FR-26/57: raw transcripts, model output and search payloads
    are NEVER written to disk. FRIDAY_DEBUG echoes the transcript so a live
    session can be watched, and the redaction filter only rewrites /home/ paths
    — it does not know the message body IS the transcript. Attached to the file
    handler only, so debug lines reach the console and stop there.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return not getattr(record, "no_disk", False)


class RedactingJsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects with path redaction (FR-43)."""

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "lvl": record.levelname.lower(),
            "name": record.name,
            "msg": record.getMessage(),
        }

        # Include structured extra fields if present
        for field in _STRUCTURED_FIELDS:
            if hasattr(record, field):
                data[field] = getattr(record, field)
        if "request_id" in data and "rid" not in data:
            data["rid"] = data.pop("request_id")

        if record.exc_info and record.exc_text:
            data["exc"] = record.exc_text
        elif record.exc_info:
            data["exc"] = self.formatException(record.exc_info)

        # Convert to JSON and run redaction across the entire formatted string
        line = json.dumps(data, ensure_ascii=False)
        return redact(line)


def setup_logging(
    log_file: Path | str | None = None,
    *,
    level: str | int = "INFO",
    max_bytes: int = config.LOG_MAX_BYTES,
    backup_count: int = config.LOG_BACKUP_COUNT,
    console: bool = True,
) -> logging.Logger:
    """Configure structured JSON logging to file + optional console output.

    Enforces 0700 dir / 0600 file permissions on the log file.
    """
    root = logging.getLogger()
    
    # Avoid duplicate handlers if setup_logging is called multiple times
    for h in list(root.handlers):
        root.removeHandler(h)

    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(level)

    if log_file is None:
        log_file = config.LOG_FILE
    target_path = Path(log_file)

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.parent.chmod(0o700)
    except Exception:
        pass

    # File handler: structured JSON lines with rotation
    file_handler = RotatingFileHandler(
        target_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(RedactingJsonFormatter())
    file_handler.setLevel(level)
    file_handler.addFilter(NoDiskFilter())  # invariant #7: transcripts never hit disk
    root.addHandler(file_handler)

    # Secure file permissions (0600)
    if target_path.exists():
        try:
            target_path.chmod(0o600)
        except Exception:
            pass

    # Console handler: human-readable or structured
    if console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
        console_handler.setLevel(level)
        root.addHandler(console_handler)

    return root
