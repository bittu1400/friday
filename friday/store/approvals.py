"""The first-use allowlist (Phase 3, criterion 3.9; design §3.3).

`Risk.FIRST_USE` means "ask once per subject, then remember". This module is
the "remember" half — without it the tier is a promise, which is why criterion
3.9 is ordered BEFORE 3.5, the derived gate that consumes it.

Two rules make it safe, and each is a test in `tests/test_approvals.py`:

- **The subject is a closed-enum id**, never a phrase and never a path. It is
  the same value the validator already exact-matched against the enum, so
  nothing the planner invents can reach this table.
- **The approval is keyed to the argv, not just the id.** `desktop.app_key`
  resolves a collision with `setdefault` — first wins — so two applications can
  normalise to one id, and an uninstall-then-install can silently rebind an id
  to a different binary. An approval whose fingerprint no longer matches does
  not apply and Friday asks again.

Approvals are user intent, like preferences: `sweep_retention` never touches
them at any age.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from typing import Sequence

from .db import Database


def fingerprint(argv: Sequence[str]) -> str:
    """A stable hash of the exact argv that was approved.

    The separator is `\\x00`, which cannot occur in an argv element, so
    `("foo bar",)` and `("foo", "bar")` cannot collide — the ambiguity a
    space-joined string would have.
    """
    return hashlib.sha256("\x00".join(argv).encode()).hexdigest()


@dataclass(frozen=True)
class Approval:
    kind: str
    subject: str
    argv_sha256: str
    approved_at: int


class ApprovalStore:
    """Grants recorded by a completed confirm handshake. Voice grants; only
    the keyboard revokes (`forget` / `reset` have no voice caller)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def is_approved(self, kind: str, subject: str, argv_sha256: str) -> bool:
        """True only if this subject was approved AND the argv still matches.

        A stored row whose fingerprint has changed is deliberately NOT deleted
        here: reading is not the place to write, and the row is replaced by the
        next completed handshake.
        """
        rows = self._db.query(
            "SELECT argv_sha256 FROM approvals WHERE kind = ? AND subject = ?",
            (kind, subject),
        )
        return bool(rows) and rows[0]["argv_sha256"] == argv_sha256

    def approve(self, kind: str, subject: str, argv_sha256: str) -> None:
        """Record a grant. Called ONLY from a completed confirm handshake.

        `INSERT OR REPLACE` because re-approving after the argv changed is the
        whole point of the fingerprint — the new binary replaces the old grant
        rather than accumulating a second row the primary key forbids anyway.
        """
        self._db.write(
            "INSERT OR REPLACE INTO approvals"
            "(kind, subject, argv_sha256, approved_at) VALUES (?, ?, ?, ?)",
            (kind, subject, argv_sha256, int(time.time())),
        )

    def list_approvals(self) -> list[Approval]:
        rows = self._db.query(
            "SELECT kind, subject, argv_sha256, approved_at FROM approvals "
            "ORDER BY approved_at DESC",
            (),
        )
        return [Approval(**dict(r)) for r in rows]

    def forget(self, kind: str, subject: str) -> int:
        return self._db.write(
            "DELETE FROM approvals WHERE kind = ? AND subject = ?", (kind, subject)
        )

    def reset(self) -> int:
        return self._db.write("DELETE FROM approvals", ())

    async def ais_approved(self, kind: str, subject: str, argv_sha256: str) -> bool:
        return await asyncio.to_thread(self.is_approved, kind, subject, argv_sha256)

    async def aapprove(self, kind: str, subject: str, argv_sha256: str) -> None:
        await asyncio.to_thread(self.approve, kind, subject, argv_sha256)

