"""The single-writer SQLite connection (FR-50/51/52/53).

One `Database` owns one connection guarded by one lock, so every write is
serialized whether it arrives from the sync CLI or from the async turn loop
(via `awrite`). That is the whole of "one writer" (FR-51): there is no
second connection that could see `database is locked`.

Guarantees:
    - WAL + `busy_timeout=5000` set on connect
    - file mode 0600, directory mode 0700 enforced on open (FR-50)
    - forward-only versioned migrations applied at startup (FR-53)
    - parameterized SQL only — this module never builds SQL from f-strings,
      and `tests/test_no_fstring_sql.py` greps the whole store/ tree (FR-52)
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _load_migrations() -> list[tuple[int, str]]:
    """Every `NNN_*.sql` file, as (version, sql), ascending. Forward-only:
    the number in the filename is the schema version it brings the DB to."""
    out: list[tuple[int, str]] = []
    for p in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        version = int(p.name.split("_", 1)[0])
        out.append((version, p.read_text()))
    return out


class Database:
    """A single serialized SQLite connection.

    The lock is a plain `threading.Lock`: async callers reach it through
    `asyncio.to_thread`, sync callers (the CLI, tests) take it directly, and
    both therefore serialize against the same mutex.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        # Perms BEFORE anything is written (FR-50). Directory 0700, db 0600.
        path.parent.chmod(0o700)
        # check_same_thread=False because to_thread may run the write on a
        # worker thread; the lock is what actually keeps access serialized.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        # The file exists now; lock it down.
        path.chmod(0o600)
        self._migrate()

    # -- schema ------------------------------------------------------------

    def _current_version(self) -> int:
        row = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        ).fetchone()
        if row is None:
            return 0
        v = self._conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        return int(v["v"]) if v and v["v"] is not None else 0

    def _migrate(self) -> None:
        with self._lock:
            have = self._current_version()
            for version, sql in _load_migrations():
                if version <= have:
                    continue
                self._conn.executescript(sql)
                # Version row written in code, not in the .sql, so the schema
                # file stays pure DDL and the counter cannot drift from it.
                self._conn.execute(
                    "INSERT INTO schema_version(version) VALUES(?)", (version,)
                )
                self._conn.commit()

    @property
    def version(self) -> int:
        with self._lock:
            return self._current_version()

    # -- access ------------------------------------------------------------

    def write(self, sql: str, params: tuple = ()) -> int:
        """Run one parameterized write, commit, return affected row count."""
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur.rowcount

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    async def awrite(self, sql: str, params: tuple = ()) -> int:
        return await asyncio.to_thread(self.write, sql, params)

    async def aquery(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return await asyncio.to_thread(self.query, sql, params)

    def close(self) -> None:
        with self._lock:
            self._conn.close()
