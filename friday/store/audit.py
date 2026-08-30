"""Dispatch audit (FR-58) and retention (FR-59).

One row per dispatch: request_id, tool_id, redacted args, policy decision,
outcome, duration, timestamp. Args are redacted BEFORE they are stored —
absolute home paths never reach disk (FR-57): the tool params seen here are
enum ids and short query text, but redaction is belt-and-braces so a future
tool that carries a path cannot leak one into the audit log.

Retention purges audit rows and session summaries only (ADR-038); it never
touches preferences.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Mapping

from .db import Database

_HOME = str(Path.home())
# Any absolute home path -> "~". Two forms: this user's real home, and the
# generic /home/<name>/... shape, so the redaction holds on another machine.
_HOME_RE = re.compile(re.escape(_HOME))
_GENERIC_HOME_RE = re.compile(r"/home/[^/\s\"']+")


def redact(text: str) -> str:
    """Replace absolute home paths with `~` (FR-57)."""
    text = _HOME_RE.sub("~", text)
    return _GENERIC_HOME_RE.sub("~", text)


def redact_args(params: Mapping[str, str]) -> str:
    """Serialize + redact tool params for the audit row."""
    return redact(json.dumps(dict(params), ensure_ascii=False, sort_keys=True))


class AuditLog:
    def __init__(self, db: Database) -> None:
        self._db = db

    def record(
        self,
        *,
        request_id: str,
        tool_id: str,
        params: Mapping[str, str],
        policy_decision: str,
        outcome: str,
        duration_ms: int,
    ) -> None:
        self._db.write(
            # Plain INSERT, never OR REPLACE: `request_id` is the primary key
            # and a colliding id must raise rather than destroy history
            # (D2/ADR-076 — a per-run `v{n}` counter made restarts eat rows).
            "INSERT INTO action_audit"
            "(request_id, tool_id, args_redacted, policy_decision, outcome, "
            " duration_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                request_id,
                tool_id,
                redact_args(params),
                policy_decision,
                outcome,
                duration_ms,
                int(time.time()),
            ),
        )

    async def arecord(self, **kw: object) -> None:
        import asyncio

        await asyncio.to_thread(lambda: self.record(**kw))  # type: ignore[arg-type]


def sweep_retention(db: Database, *, retention_days: int = 90) -> int:
    """Purge machine exhaust older than the cutoff (ADR-038, ADR-068b).

    Swept: audit rows, session summaries, and reminders in a TERMINAL state
    (`fired`/`cancelled`) — once a timer has gone off it is of no further
    interest, and M-T9 found `reminders` growing without bound on a long-lived
    install.

    Never swept, at any age: preferences, notes, and **active** reminders.
    Notes and preferences are content the user authored and expects to still be
    there; an active reminder has not happened yet. Deleting either would be
    the "spoke success while doing nothing" failure aimed at the user's own
    data. Returns rows deleted.
    """
    cutoff = int(time.time()) - retention_days * 86400
    deleted = db.write("DELETE FROM action_audit WHERE created_at < ?", (cutoff,))
    deleted += db.write(
        "DELETE FROM session_summaries WHERE created_at < ?", (cutoff,)
    )
    # `reminders.created_at` is a REAL epoch (DST-immune, ADR-056), not the
    # INTEGER the other two tables use; the comparison is numeric either way.
    deleted += db.write(
        "DELETE FROM reminders WHERE state IN ('fired', 'cancelled') "
        "AND created_at < ?",
        (cutoff,),
    )
    return deleted
