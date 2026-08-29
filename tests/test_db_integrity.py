"""Database perms, migration atomicity, and retention scope
(audit M-T2, M-T3, M-T9 / ADR-068b).

All three are startup-path or long-lived-install defects: they do not show up
in a fresh test DB used for one assertion, which is why 328 green tests never
touched them.
"""

import os
import sqlite3
import time

import pytest

from friday.store import db as db_mod
from friday.store.audit import AuditLog, sweep_retention
from friday.store.db import Database, _split_statements
from friday.store.notes import NoteStore
from friday.store.reminders import ReminderStore

_DAY = 86400


# --- M-T2: the WAL sidecars are as sensitive as the database ---------------


def _mode(p):
    return p.stat().st_mode & 0o777


@pytest.fixture
def loose_umask():
    """A permissive umask is the condition under which M-T2 actually leaks."""
    old = os.umask(0o000)
    yield
    os.umask(old)


def test_wal_sidecars_are_not_world_readable(tmp_path, loose_umask):
    """The WAL holds preferences, notes and reminder text in flight, so it is
    exactly as sensitive as the database (FR-50).

    Note on M-T2 as the audit stated it: `PRAGMA journal_mode=WAL` does NOT
    create the sidecars on this machine — SQLite creates them at the first
    write transaction, which is `_migrate`, i.e. already after the chmod. So
    the leak the audit described is not reachable by that route here. Measured
    2026-08-29 under `umask 000`: both sidecars come out 0600 with or without
    the reordering. The fix stands on the reachable case below and on not
    depending on SQLite's lazy-creation timing for a security property.
    """
    path = tmp_path / "memory.db"
    db = Database(path)
    db.write("INSERT INTO notes(id, created_at, content) VALUES(?, ?, ?)",
             ("n1", time.time(), "a private note"))

    sidecars = [path.with_name(path.name + s) for s in ("-wal", "-shm")]
    assert all(s.exists() for s in sidecars), "no sidecars: the check is vacuous"
    assert _mode(path) == 0o600
    for side in sidecars:
        assert _mode(side) == 0o600, f"{side.name} is {oct(_mode(side))}"
    db.close()


def test_opening_repairs_a_loose_sidecar_left_by_a_crash(tmp_path):
    """The reachable M-T2 case, and the one this project actually hits.

    A clean close checkpoints the WAL away, so a leftover `-wal` only survives
    an UNCLEAN shutdown — which `friday.service` has by design: `Restart=always`
    means a SIGKILLed daemon is back within seconds. If anything ever leaves
    that WAL world-readable, nothing used to look at it again and it stayed
    readable for the life of the install. Verified by hand 2026-08-29: after a
    `kill -9`, a `-wal` chmod-ed to 0644 was still 0644 after reopening on the
    pre-fix code, and is 0600 now.
    """
    path = tmp_path / "memory.db"
    db = Database(path)
    db.write("INSERT INTO notes(id, created_at, content) VALUES(?, ?, ?)",
             ("n1", time.time(), "secret"))
    # Abandon the connection without closing it, then drop our reference: the
    # sidecars stay on disk exactly as a killed process would leave them.
    wal = path.with_name(path.name + "-wal")
    assert wal.exists()
    del db

    wal.chmod(0o644)
    reopened = Database(path)
    assert _mode(wal) == 0o600, "a leftover loose WAL was left readable"
    reopened.close()


def test_selftest_checks_the_sidecar_perms(tmp_path, loose_umask):
    """The check must be able to FAIL, or it is worth nothing (session rule)."""
    from friday.selftest import Status, check_database

    path = tmp_path / "memory.db"
    tmp_path.chmod(0o700)
    Database(path).close()

    wal = path.with_name(path.name + "-wal")
    if not wal.exists():  # WAL was checkpointed away on close; recreate it
        con = sqlite3.connect(path)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("INSERT INTO notes(id, created_at, content) VALUES('x', 1, 'y')")
        con.commit()
        assert wal.exists()

    assert check_database(path).status is Status.PASS

    wal.chmod(0o644)
    result = check_database(path)
    assert result.status is Status.FAIL
    assert "-wal" in result.message


# --- M-T3: a half-applied migration must not become a crash loop -----------


def test_migration_and_version_bump_are_one_transaction(tmp_path, monkeypatch):
    """M-T3: `executescript` implicitly COMMITs, so the DDL and the version row
    landed separately. A crash between them left tables created and the version
    unrecorded; `Restart=always` then re-ran CREATE TABLE and died on
    OperationalError, forever."""
    path = tmp_path / "memory.db"
    real = db_mod._load_migrations()

    # A migration whose LAST statement fails, mid-script.
    broken = real[:1] + [(99, "CREATE TABLE IF NOT EXISTS half (a INT);\n"
                              "CREATE TABLE half (a INT);\n")]
    monkeypatch.setattr(db_mod, "_load_migrations", lambda: broken)

    with pytest.raises(sqlite3.Error):
        Database(path)

    con = sqlite3.connect(path)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "half" not in tables, "a failed migration left a partial schema behind"
    version = con.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    assert version == 1, "the version must not advance past what applied"
    con.close()


def test_reopening_after_a_lost_version_row_recovers(tmp_path):
    """The exact crash-loop shape: schema present, version row missing. IF NOT
    EXISTS makes the re-run a no-op instead of an OperationalError."""
    path = tmp_path / "memory.db"
    Database(path).close()

    con = sqlite3.connect(path)
    con.execute("DELETE FROM schema_version")  # simulate the crash window
    con.commit()
    con.close()

    db = Database(path)  # must not raise
    assert db.version == max(v for v, _ in db_mod._load_migrations())
    db.close()


def test_every_migration_creates_idempotently():
    """The second belt: a future migration that forgets IF NOT EXISTS
    reintroduces the crash loop, so fail here instead of in production."""
    for _version, sql in db_mod._load_migrations():
        for stmt in _split_statements(sql):
            head = stmt.upper()
            if head.startswith("CREATE TABLE") or head.startswith("CREATE INDEX"):
                assert "IF NOT EXISTS" in head, f"not idempotent: {stmt.splitlines()[0]}"


def test_statement_splitter_respects_semicolons_inside_strings():
    stmts = _split_statements(
        "CREATE TABLE t (a TEXT DEFAULT 'x;y');\nINSERT INTO t VALUES('p;q');\n"
    )
    assert len(stmts) == 2
    assert stmts[0].startswith("CREATE TABLE")
    assert stmts[1].startswith("INSERT")


# --- ADR-068b / M-T9: what retention may and may not eat ------------------


def test_retention_sweeps_terminal_reminders_only(tmp_path):
    db = Database(tmp_path / "memory.db")
    rs = ReminderStore(db)
    old = time.time() - 100 * _DAY

    def _add(rid, state):
        db.write(
            "INSERT INTO reminders(id, created_at, fire_at, kind, message, state) "
            "VALUES(?, ?, ?, 'timer', ?, ?)",
            (rid, old, old + 60, f"msg {rid}", state),
        )

    _add("r_fired", "fired")
    _add("r_cancelled", "cancelled")
    _add("r_active", "active")
    fresh = rs.create(3600, "today's timer")
    db.write("UPDATE reminders SET state='fired' WHERE id=?", (fresh.id,))

    sweep_retention(db, retention_days=90)

    left = {r["id"] for r in db.query("SELECT id FROM reminders")}
    assert "r_fired" not in left and "r_cancelled" not in left
    assert "r_active" in left, "an active reminder is never pruned, at any age"
    assert fresh.id in left, "a recent fired reminder is inside the window"
    db.close()


def test_retention_never_touches_notes_or_preferences(tmp_path):
    """ADR-068b: notes are user-authored content. Silently eating them is the
    'spoke success while doing nothing' failure aimed at the user's own data."""
    db = Database(tmp_path / "memory.db")
    old = time.time() - 100 * _DAY
    db.write("INSERT INTO notes(id, created_at, content) VALUES(?, ?, ?)",
             ("n_old", old, "a note from three months ago"))
    NoteStore(db).create("a note from today")
    db.write(
        "INSERT INTO preferences(key, value_json, source, updated_at) "
        "VALUES(?, ?, ?, ?)",
        ("name", '"Subham"', "user_confirmed", int(old)),
    )

    sweep_retention(db, retention_days=90)

    assert len(db.query("SELECT id FROM notes")) == 2
    assert len(db.query("SELECT key FROM preferences")) == 1
    db.close()


def test_retention_still_sweeps_audit_and_summaries(tmp_path):
    """Regression guard on what retention is FOR (ADR-038)."""
    db = Database(tmp_path / "memory.db")
    audit = AuditLog(db)
    audit.record(request_id="old", tool_id="open_app", params={"app": "browser"},
                 policy_decision="allowed", outcome="ok", duration_ms=1)
    old = int(time.time() - 100 * _DAY)
    db.write("UPDATE action_audit SET created_at=? WHERE request_id='old'", (old,))
    db.write(
        "INSERT INTO session_summaries(session_id, summary, created_at) VALUES(?, ?, ?)",
        ("s1", "old summary", old),
    )

    deleted = sweep_retention(db, retention_days=90)

    assert deleted == 2
    assert db.query("SELECT request_id FROM action_audit") == []
    assert db.query("SELECT session_id FROM session_summaries") == []
    db.close()
