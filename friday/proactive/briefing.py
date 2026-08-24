"""Startup briefings and session sign-off close summaries (G11, ADR-056).

Generates startup briefings from active reminders and long-term memory,
and detects voice sign-off triggers ("goodnight", "bye") to deliver a close summary.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from friday.store.db import Database

log = logging.getLogger(__name__)

_SIGNOFF_PATTERNS = [
    r"\bgood\s*night\b",
    r"\bbye\b",
    r"\bgoodbye\b",
    r"\bsee you later\b",
    r"\bcatch you later\b",
    r"\bhave a good night\b",
]


def is_signoff_phrase(text: str) -> bool:
    """True if text is a voice sign-off trigger."""
    norm = text.lower().strip()
    return any(re.search(pat, norm) for pat in _SIGNOFF_PATTERNS)


def generate_startup_briefing(db: Database) -> str:
    """Generate a concise startup greeting and status line."""
    try:
        from friday.store.reminders import ReminderStore
        from friday.store.summarizer import get_recent_session_summaries

        store = ReminderStore(db)
        active = store.list_active()
        summaries = get_recent_session_summaries(db, limit=1)

        parts = ["Good day."]
        if active:
            n = len(active)
            parts.append(f"You have {n} active {'timer' if n == 1 else 'timers'}.")
        if summaries:
            parts.append("Systems online and ready.")
        else:
            parts.append("Friday is ready.")
        return " ".join(parts)
    except Exception as exc:
        log.debug("Failed to generate startup briefing (%s)", exc)
        return "Friday is online and ready."


def generate_signoff_summary(dialogue: str, client: Any) -> str:
    """Generate a concise close-summary on voice sign-off."""
    try:
        from friday.store.summarizer import distill_dialogue

        summary = distill_dialogue(client, dialogue)
        if summary:
            return f"Goodnight. {summary}"
    except Exception as exc:
        log.debug("Failed to generate signoff summary (%s)", exc)
    return "Goodnight. Systems standing by."
