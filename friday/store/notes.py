"""Notes storage in SQLite (G12, ADR-057).

Stores quick notes and reminders as pure data in SQLite (never executed).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
import uuid

from .db import Database


@dataclass(frozen=True)
class Note:
    id: str
    created_at: float
    content: str


class NoteStore:
    """Store for capturing and reading notes in SQLite."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, content: str) -> Note:
        now = time.time()
        nid = f"note_{uuid.uuid4().hex[:8]}"
        clean = content.strip()
        self._db.write(
            "INSERT INTO notes(id, created_at, content) VALUES (?, ?, ?)",
            (nid, now, clean),
        )
        return Note(id=nid, created_at=now, content=clean)

    def list_notes(self, limit: int = 10) -> list[Note]:
        rows = self._db.query(
            "SELECT id, created_at, content FROM notes ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [
            Note(id=r["id"], created_at=r["created_at"], content=r["content"])
            for r in rows
        ]

    async def acreate(self, content: str) -> Note:
        return await asyncio.to_thread(self.create, content)

    async def alist_notes(self, limit: int = 10) -> list[Note]:
        return await asyncio.to_thread(self.list_notes, limit)
