"""Tests for session summarization and long-term memory (G8 Stage 3, ADR-050)."""

import time
from pathlib import Path

from friday.store.db import Database
from friday.store.summarizer import (
    distill_dialogue,
    get_recent_session_summaries,
    render_summaries_digest,
    save_session_summary,
)


def _init_db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test.db")


class _MockLlamaClient:
    def __init__(self, reply: str = "User worked on Python scripts and opened VS Code.") -> None:
        self.reply = reply
        self.seen_system = ""
        self.seen_user = ""

    def complete(self, *, system, user, grammar="", **kw):
        self.seen_system = system
        self.seen_user = user
        return self.reply


def test_distill_dialogue_empty():
    client = _MockLlamaClient()
    assert distill_dialogue(client, "") == ""
    assert distill_dialogue(client, "   ") == ""


def test_distill_dialogue_calls_client():
    client = _MockLlamaClient("User was coding in Python.")
    dialogue = "You: open my editor\nFriday: Opened VS Code."
    summary = distill_dialogue(client, dialogue)
    assert summary == "User was coding in Python."
    assert "Conversation:\n" in client.seen_user
    assert "summarizer" in client.seen_system.lower()


def test_save_and_get_session_summaries(tmp_path):
    db = _init_db(tmp_path)
    save_session_summary(db, "s1", "First session summary")
    time.sleep(0.01)
    save_session_summary(db, "s2", "Second session summary")
    time.sleep(0.01)
    save_session_summary(db, "s3", "Third session summary")

    # Limit 2 should return the 2 most recent summaries (s3, s2)
    recent = get_recent_session_summaries(db, limit=2)
    assert len(recent) == 2
    assert recent[0] == "Third session summary"
    assert recent[1] == "Second session summary"


def test_render_summaries_digest():
    summaries = [
        "User worked on Python in VS Code.",
        "User listened to lo-fi music.",
    ]
    digest = render_summaries_digest(summaries)
    assert digest.startswith("<past_sessions>\n")
    assert digest.endswith("\n</past_sessions>")
    assert "- User worked on Python in VS Code." in digest
    assert "- User listened to lo-fi music." in digest


def test_render_summaries_digest_empty():
    assert render_summaries_digest([]) == ""
