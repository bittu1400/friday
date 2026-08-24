"""Dictation mode manager (G12, ADR-058).

Explicit-toggle dictation mode. Transcripts are typed verbatim into the focused
window without passing through the planner, and wake detection is paused.
"""

from __future__ import annotations

import logging
import re
from friday.tools.typer import type_text

log = logging.getLogger(__name__)

_START_DICTATION = re.compile(r"\b(?:start|begin|enable)\s+dictation(?:\s+mode)?\b", re.IGNORECASE)
_STOP_DICTATION = re.compile(r"\b(?:stop|end|exit|disable)\s+dictation(?:\s+mode)?\b", re.IGNORECASE)

_PUNCT_MAP = [
    (re.compile(r"\bperiod\b", re.IGNORECASE), "."),
    (re.compile(r"\bcomma\b", re.IGNORECASE), ","),
    (re.compile(r"\bquestion mark\b", re.IGNORECASE), "?"),
    (re.compile(r"\bexclamation mark\b", re.IGNORECASE), "!"),
    (re.compile(r"\bnew line\b", re.IGNORECASE), "\n"),
    (re.compile(r"\bnewline\b", re.IGNORECASE), "\n"),
]


def is_start_dictation(text: str) -> bool:
    return bool(_START_DICTATION.search(text.strip()))


def is_stop_dictation(text: str) -> bool:
    return bool(_STOP_DICTATION.search(text.strip()))


def format_dictation(text: str) -> str:
    """Format spoken punctuation into symbols."""
    res = text
    for pattern, sym in _PUNCT_MAP:
        res = pattern.sub(sym, res)
    # Clean up spaces before punctuation and around newlines
    res = re.sub(r"\s+([.,?!])", r"\1", res)
    res = re.sub(r"[ \t]*\n[ \t]*", "\n", res)
    return res


class DictationManager:
    """Manages active dictation mode state and verbatim typing."""

    def __init__(self) -> None:
        self._active: bool = False

    @property
    def is_dictating(self) -> bool:
        return self._active

    def start(self) -> None:
        self._active = True

    def stop(self) -> None:
        self._active = False

    def handle_transcript(self, text: str) -> bool:
        """Format and type transcript into the focused window."""
        if not self._active or not text:
            return False
        formatted = format_dictation(text)
        return type_text(formatted + " ")
