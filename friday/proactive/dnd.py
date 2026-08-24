"""Conversational Do-Not-Disturb (DND) state machine (G11, ADR-056).

Quiet mode is governed by conversational cues ("let's talk later", "do not disturb"),
not a clock. Resumed automatically when the user addresses Friday with a question or command.
"""

from __future__ import annotations

import re

_HUSH_PATTERNS = [
    r"\blet'?s talk later\b",
    r"\bdo not disturb\b",
    r"\btalk later\b",
    r"\bbe quiet\b",
    r"\bquiet mode\b",
    r"\bshut up\b",
    r"\bhush\b",
    r"\bgo to sleep\b",
    r"\bsilence\b",
]

_RESUME_PATTERNS = [
    r"\bresume\b",
    r"\bdisable quiet mode\b",
    r"\bunmute\b",
    r"\btalk to me\b",
    r"\bwe can talk\b",
]


def is_hush_phrase(text: str) -> bool:
    """True if text contains a conversational DND hush trigger."""
    norm = text.lower().strip()
    return any(re.search(pat, norm) for pat in _HUSH_PATTERNS)


def is_resume_phrase(text: str) -> bool:
    """True if text explicitly asks to exit DND."""
    norm = text.lower().strip()
    return any(re.search(pat, norm) for pat in _RESUME_PATTERNS)


class DndManager:
    """In-memory manager for conversational DND state."""

    def __init__(self, initial_dnd: bool = False) -> None:
        self._dnd: bool = initial_dnd

    @property
    def is_dnd(self) -> bool:
        return self._dnd

    def set_dnd(self) -> None:
        self._dnd = True

    def clear_dnd(self) -> None:
        self._dnd = False
