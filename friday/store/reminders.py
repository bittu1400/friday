"""SQLite reminder & timer store (G11, ADR-056).

Persists user timers and reminders across daemon restarts in SQLite.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
import uuid

from .db import Database


@dataclass(frozen=True)
class Reminder:
    id: str
    created_at: float
    fire_at: float
    kind: str
    message: str
    state: str


class ReminderStore:
    """Store for scheduling and tracking active/fired timers and reminders."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, seconds: float, message: str, kind: str = "timer") -> Reminder:
        now = time.time()
        rid = f"rem_{uuid.uuid4().hex[:8]}"
        fire_at = now + max(0.01, float(seconds))
        kind_clean = "reminder" if kind == "reminder" else "timer"
        msg_clean = message.strip() or "Timer up"

        self._db.write(
            "INSERT INTO reminders(id, created_at, fire_at, kind, message, state) "
            "VALUES (?, ?, ?, ?, ?, 'active')",
            (rid, now, fire_at, kind_clean, msg_clean),
        )
        return Reminder(
            id=rid,
            created_at=now,
            fire_at=fire_at,
            kind=kind_clean,
            message=msg_clean,
            state="active",
        )

    def get_due(self, now: float | None = None) -> list[Reminder]:
        ts = time.time() if now is None else now
        rows = self._db.query(
            "SELECT id, created_at, fire_at, kind, message, state FROM reminders "
            "WHERE state = 'active' AND fire_at <= ? ORDER BY fire_at ASC",
            (ts,),
        )
        return [
            Reminder(
                id=r["id"],
                created_at=r["created_at"],
                fire_at=r["fire_at"],
                kind=r["kind"],
                message=r["message"],
                state=r["state"],
            )
            for r in rows
        ]

    def mark_fired(self, reminder_id: str) -> None:
        self._db.write(
            "UPDATE reminders SET state = 'fired' WHERE id = ?",
            (reminder_id,),
        )

    def list_active(self) -> list[Reminder]:
        rows = self._db.query(
            "SELECT id, created_at, fire_at, kind, message, state FROM reminders "
            "WHERE state = 'active' ORDER BY fire_at ASC"
        )
        return [
            Reminder(
                id=r["id"],
                created_at=r["created_at"],
                fire_at=r["fire_at"],
                kind=r["kind"],
                message=r["message"],
                state=r["state"],
            )
            for r in rows
        ]

    def cancel(self, reminder_id: str) -> bool:
        count = self._db.write(
            "UPDATE reminders SET state = 'cancelled' WHERE id = ? AND state = 'active'",
            (reminder_id,),
        )
        return count > 0

    async def acreate(self, seconds: float, message: str, kind: str = "timer") -> Reminder:
        return await asyncio.to_thread(self.create, seconds, message, kind)

    async def aget_due(self, now: float | None = None) -> list[Reminder]:
        return await asyncio.to_thread(self.get_due, now)

    async def amark_fired(self, reminder_id: str) -> None:
        await asyncio.to_thread(self.mark_fired, reminder_id)

    async def alist_active(self) -> list[Reminder]:
        return await asyncio.to_thread(self.list_active)

    async def acancel(self, reminder_id: str) -> bool:
        return await asyncio.to_thread(self.cancel, reminder_id)
