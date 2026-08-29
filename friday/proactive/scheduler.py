"""Proactive scheduler & turn arbiter (G11, ADR-056).

Polls due reminders and coordinates with the turn FSM to deliver notifications
and spoken alerts without violating FR-5 (one turn in flight).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
import logging
import time
from typing import Any

from friday.store.reminders import Reminder, ReminderStore
from .dnd import DndManager
from .notifier import anotify

log = logging.getLogger(__name__)


class Scheduler:
    """Background scheduler for proactive events (reminders, timers, briefings)."""

    def __init__(
        self,
        *,
        store: ReminderStore,
        dnd: DndManager,
        is_idle: Callable[[], bool],
        on_event: Callable[[str, str], Coroutine[Any, Any, None]],
        poll_interval_s: float = 1.0,
    ) -> None:
        self._store = store
        self._dnd = dnd
        self._is_idle = is_idle
        self._on_event = on_event
        self._poll_interval = poll_interval_s
        self._running = False
        self._stop_event = asyncio.Event()

    def stop(self) -> None:
        """Signal scheduler loop to stop."""
        self._running = False
        self._stop_event.set()

    async def run(self) -> None:
        """Run scheduler loop polling for due events."""
        self._running = True
        self._stop_event.clear()

        while self._running:
            try:
                await self._poll_step()
            except Exception as exc:
                log.debug("Scheduler poll error (%s)", exc)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval)
                break
            except asyncio.TimeoutError:
                pass

    async def _poll_step(self) -> None:
        now = time.time()
        due = await self._store.aget_due(now=now)

        for rem in due:
            await self._store.amark_fired(rem.id)
            log.info("Reminder triggered: %s (%s)", rem.id, rem.message)

            # Send desktop notification, off the loop (H6): a blocking
            # `notify-send` here delayed every later due reminder in the same
            # burst by up to 2 s each.
            await anotify(f"Friday {rem.kind.capitalize()}", rem.message)

            # Enqueue proactive speech event
            # Per user decision (2026-08-24): Timers & reminders fire anyway during DND
            try:
                await self._on_event(f"Friday {rem.kind.capitalize()}", rem.message)
            except Exception as exc:
                log.debug("Error delivering proactive event (%s)", exc)
