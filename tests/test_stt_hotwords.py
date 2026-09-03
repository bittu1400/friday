"""The hotword list must track the app enum, not Phase 1 — D31.

Twice now a Phase-1 vocabulary list has been left behind by a later gate and
the cost was paid at a microphone. D26: `STT_HOTWORDS` had no G12 words, so
"wifi" came back as wife / weapon / way / life on four consecutive turns.
D31: ADR-097 widened the app enum from 5 ids to every installed desktop entry
and left this list at the same five apps, so for a month the only application
names Whisper was biased toward were the only five that had ever been
dispatched — `action_audit` has no other `open_app` row in the life of the
project.

This test is the D24 coverage test's shape, applied to a parameter VALUE set
rather than to action names. It does not check WHICH apps are listed — that is
the owner's call and it moves — only that the list did not fall back to Phase 1.
"""

from __future__ import annotations

import re

from friday import config
from friday.llm import schema

# Owner's call 2026-09-03: twenty app names now, the remaining ~145 once the
# cost of these twenty is measured (OQ-68). Seven names matched before, so this
# floor fails on a revert to Phase 1 without pinning the exact list.
_MIN_APP_HOTWORDS = 20


def _slug(word: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", word.lower()).strip("_")


def test_hotwords_cover_installed_applications_not_just_the_curated_five():
    enum = set(schema.PARAM_SCHEMA["open_app"]["app"]["values"])
    matched = {
        _slug(w) for w in config.STT_HOTWORDS.split(",") if _slug(w) in enum
    }
    assert len(matched) >= _MIN_APP_HOTWORDS, (
        f"only {len(matched)} hotwords name an app in the enum "
        f"({sorted(matched)}) — a word the user must SAY to reach a capability "
        "belongs in STT_HOTWORDS (D26, D31)"
    )


def test_hotwords_still_carry_the_g12_control_vocabulary():
    """D26's own regression: the words that select an action, not an app."""

    low = config.STT_HOTWORDS.lower()
    for word in ("wifi", "brightness", "clipboard", "dictation", "workspace"):
        assert word in low, f"{word!r} missing from STT_HOTWORDS (D26)"
