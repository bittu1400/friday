"""The single-writer store: migrations, permissions, and concurrency (FR-50/51/53)."""

from __future__ import annotations

import asyncio
import stat

from friday.store.db import Database


def test_fresh_db_reaches_version_1(tmp_path) -> None:
    db = Database(tmp_path / "memory.db")
    assert db.version == 1


def test_existing_db_reaches_same_version(tmp_path) -> None:
    p = tmp_path / "memory.db"
    Database(p).close()
    # Reopen: migrations already applied, version stays 1 (forward-only, FR-53).
    assert Database(p).version == 1


def test_migration_creates_all_tables(tmp_path) -> None:
    db = Database(tmp_path / "memory.db")
    names = {
        r["name"]
        for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"schema_version", "preferences", "action_audit", "session_summaries"} <= names


def test_permissions_enforced(tmp_path) -> None:
    p = tmp_path / "memory.db"
    Database(p)
    assert stat.S_IMODE(p.stat().st_mode) == 0o600  # FR-50 file
    assert stat.S_IMODE(p.parent.stat().st_mode) == 0o700  # FR-50 dir


def test_wal_mode(tmp_path) -> None:
    db = Database(tmp_path / "memory.db")
    mode = db.query("PRAGMA journal_mode")[0][0]
    assert mode.lower() == "wal"


def test_100_parallel_writes_no_lock(tmp_path) -> None:
    """FR-51: one writer, one connection — 100 concurrent writes, zero
    `database is locked`."""
    db = Database(tmp_path / "memory.db")

    async def go() -> None:
        await asyncio.gather(
            *[
                db.awrite(
                    "INSERT INTO action_audit(request_id, tool_id, args_redacted, "
                    "policy_decision, outcome, duration_ms, created_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (f"r{i}", "open_app", "{}", "allowed", "ok", 1, 0),
                )
                for i in range(100)
            ]
        )

    asyncio.run(go())
    assert db.query("SELECT COUNT(*) AS n FROM action_audit")[0]["n"] == 100
