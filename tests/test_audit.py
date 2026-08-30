"""Audit redaction (FR-57/58) and retention scope (FR-59 / ADR-038)."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from friday.store.audit import AuditLog, redact, redact_args, sweep_retention
from friday.store.db import Database
from friday.store.prefs import PrefStore, resolve


def test_redact_home_paths() -> None:
    assert redact(f"{Path.home()}/secret") == "~/secret"
    assert redact("/home/someoneelse/file") == "~/file"


def test_redact_args_leaves_no_home() -> None:
    out = redact_args({"path": f"{Path.home()}/x", "q": "weather"})
    assert "/home/" not in out and str(Path.home()) not in out


def test_record_writes_one_row(tmp_path) -> None:
    db = Database(tmp_path / "memory.db")
    AuditLog(db).record(
        request_id="r1",
        tool_id="open_app",
        params={"app": "browser"},
        policy_decision="allowed",
        outcome="ok",
        duration_ms=12,
    )
    rows = db.query("SELECT * FROM action_audit")
    assert len(rows) == 1 and rows[0]["tool_id"] == "open_app"


def test_retention_purges_logs_only(tmp_path) -> None:
    """Old audit + summary rows go; preferences never age out (ADR-038)."""
    db = Database(tmp_path / "memory.db")
    old = int(time.time()) - 200 * 86400
    db.write(
        "INSERT INTO action_audit(request_id, tool_id, args_redacted, "
        "policy_decision, outcome, duration_ms, created_at) VALUES (?,?,?,?,?,?,?)",
        ("old", "open_app", "{}", "allowed", "ok", 1, old),
    )
    db.write(
        "INSERT INTO session_summaries(session_id, summary, created_at) "
        "VALUES (?,?,?)",
        ("s1", "a summary", old),
    )
    PrefStore(db).put(resolve("name", "Subham"))

    deleted = sweep_retention(db, retention_days=90)

    assert deleted == 2
    assert db.query("SELECT COUNT(*) AS n FROM action_audit")[0]["n"] == 0
    assert db.query("SELECT COUNT(*) AS n FROM session_summaries")[0]["n"] == 0
    assert PrefStore(db).active() == {"name": "Subham"}  # untouched


def test_retention_keeps_recent(tmp_path) -> None:
    db = Database(tmp_path / "memory.db")
    AuditLog(db).record(
        request_id="r1",
        tool_id="open_app",
        params={"app": "browser"},
        policy_decision="allowed",
        outcome="ok",
        duration_ms=1,
    )
    assert sweep_retention(db, retention_days=90) == 0
    assert db.query("SELECT COUNT(*) AS n FROM action_audit")[0]["n"] == 1


def test_colliding_request_id_never_replaces_a_row(tmp_path) -> None:
    """D2 / FR-86: the write is a plain INSERT.

    It was `INSERT OR REPLACE` keyed on a `v{n}` counter the daemon reset at
    every start, so run 2's `v3` silently destroyed run 1's `v3`. A collision
    must now raise loudly instead of eating history.
    """
    db = Database(tmp_path / "memory.db")
    audit = AuditLog(db)
    kw = dict(params={}, policy_decision="allowed", outcome="ok", duration_ms=1)
    audit.record(request_id="v3", tool_id="web_search", **kw)
    with pytest.raises(sqlite3.IntegrityError):
        audit.record(request_id="v3", tool_id="open_app", **kw)
    assert [r["tool_id"] for r in db.query("SELECT tool_id FROM action_audit")] == [
        "web_search"
    ]
