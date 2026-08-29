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


def _split_statements(script: str) -> list[str]:
    """Split a migration script into individual statements.

    `sqlite3.executescript` cannot be used inside a transaction — it issues an
    implicit COMMIT first — so the statements are executed one at a time
    instead (M-T3). Splitting uses `sqlite3.complete_statement`, which
    understands semicolons inside string literals, rather than a naive
    `split(";")`.
    """
    out: list[str] = []
    buf = ""
    for line in script.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            stmt = buf.strip()
            buf = ""
            if stmt and stmt != ";":
                out.append(stmt)
    if buf.strip():  # a trailing statement with no terminating semicolon
        out.append(buf.strip())
    return out


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
        # Lock the file down IMMEDIATELY after connect, before any pragma
        # (M-T2). The audit said `journal_mode=WAL` creates the `-wal`/`-shm`
        # sidecars, so a later chmod left them world-readable. Measured
        # 2026-08-29 under `umask 000`: it does NOT — SQLite creates them at the
        # first write transaction (`_migrate`, below), by which point the main
        # file is already 0600 and they inherit it. The ordering stays anyway,
        # because a security property must not depend on when SQLite happens to
        # create a file.
        path.chmod(0o600)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        # The reachable exposure is a sidecar left behind by an UNCLEAN
        # shutdown: a clean close checkpoints the WAL away, but `friday.service`
        # is `Restart=always`, so a SIGKILLed daemon leaves one and comes
        # straight back. Pre-fix, a `-wal` chmod-ed to 0644 after `kill -9`
        # stayed 0644 across every restart, forever.
        self._secure_sidecars()
        self._migrate()

    def _secure_sidecars(self) -> None:
        """Force 0600 on the `-wal`/`-shm` files if they exist (FR-50)."""
        for suffix in ("-wal", "-shm"):
            side = self._path.with_name(self._path.name + suffix)
            try:
                if side.exists():
                    side.chmod(0o600)
            except OSError:  # fail soft: a perms repair must not stop startup
                pass

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
        """Apply pending migrations, each atomically with its version row.

        M-T3: this used to run `executescript(sql)` and then INSERT the version
        as a separate transaction. `executescript` issues an implicit COMMIT
        before it runs and commits its own work, so a crash between the two
        left the tables created and the version unrecorded. `Restart=always`
        then brought the daemon straight back, it re-ran `CREATE TABLE` against
        tables that already existed, and died on OperationalError — forever.

        So the script is split into statements and driven inside ONE explicit
        transaction together with the version bump: schema and counter move
        together or not at all. The DDL also carries IF NOT EXISTS as a second
        belt, in case a future migration is ever applied outside this path.
        """
        with self._lock:
            have = self._current_version()
            for version, sql in _load_migrations():
                if version <= have:
                    continue
                try:
                    self._conn.execute("BEGIN")
                    for stmt in _split_statements(sql):
                        self._conn.execute(stmt)
                    # Version row written in code, not in the .sql, so the
                    # schema file stays pure DDL and the counter cannot drift.
                    self._conn.execute(
                        "INSERT INTO schema_version(version) VALUES(?)", (version,)
                    )
                    self._conn.commit()
                except Exception:
                    self._conn.rollback()
                    raise

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
