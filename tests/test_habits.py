"""Tests for habit mining from action audit log (G8 Stage 2, ADR-049)."""

import time
from pathlib import Path

from friday.store.audit import AuditLog
from friday.store.db import Database
from friday.store.habits import (
    describe_action,
    mine_habits,
    render_habits_digest,
    time_of_day_slot,
)


def _init_db(tmp_path: Path) -> Database:
    db_path = tmp_path / "test.db"
    return Database(db_path)


def test_time_of_day_slot():
    # Helper to create timestamps for specific local hours
    import datetime
    now = datetime.datetime.now()
    
    def ts_for_hour(h: int) -> int:
        dt = now.replace(hour=h, minute=30, second=0, microsecond=0)
        return int(dt.timestamp())

    assert time_of_day_slot(ts_for_hour(6)) == "around sunrise / early morning"
    assert time_of_day_slot(ts_for_hour(9)) == "in the morning"
    assert time_of_day_slot(ts_for_hour(14)) == "in the afternoon"
    assert time_of_day_slot(ts_for_hour(18)) == "around sunset / early evening"
    assert time_of_day_slot(ts_for_hour(21)) == "in the evening"
    assert time_of_day_slot(ts_for_hour(23)) == "late at night"
    assert time_of_day_slot(ts_for_hour(2)) == "late at night"


def test_describe_action():
    assert describe_action("open_app", '{"app": "browser"}', gerund=False) == "open Brave"
    assert describe_action("open_app", '{"app": "browser"}', gerund=True) == "opening Brave"
    assert describe_action("open_app", '{"app": "editor"}', gerund=False) == "open VS Code"
    assert describe_action("open_youtube", "{}", gerund=False) == "open YouTube"
    assert describe_action("youtube_search", '{"query": "lo-fi"}', gerund=False) == "search YouTube for 'lo-fi'"
    assert describe_action("youtube_search", '{"query": "lo-fi"}', gerund=True) == "searching YouTube for 'lo-fi'"
    assert describe_action("web_search", '{"query": "weather"}', gerund=False) == "search the web for 'weather'"


def test_mine_habits_empty_db(tmp_path):
    db = _init_db(tmp_path)
    habits = mine_habits(db)
    assert habits == []
    assert render_habits_digest(habits) == ""


def test_mine_sequence_habits(tmp_path):
    db = _init_db(tmp_path)
    audit = AuditLog(db)
    base_ts = int(time.time()) - 10000

    # Sequence: Brave -> Code (happens 2 times within 10 minutes)
    # Occurrence 1:
    audit.record(
        request_id="r1", tool_id="open_app", params={"app": "browser"},
        policy_decision="allowed", outcome="ok", duration_ms=50
    )
    db.write("UPDATE action_audit SET created_at = ? WHERE request_id = ?", (base_ts, "r1"))

    audit.record(
        request_id="r2", tool_id="open_app", params={"app": "editor"},
        policy_decision="allowed", outcome="ok", duration_ms=50
    )
    db.write("UPDATE action_audit SET created_at = ? WHERE request_id = ?", (base_ts + 300, "r2"))

    # Occurrence 2:
    audit.record(
        request_id="r3", tool_id="open_app", params={"app": "browser"},
        policy_decision="allowed", outcome="ok", duration_ms=50
    )
    db.write("UPDATE action_audit SET created_at = ? WHERE request_id = ?", (base_ts + 2000, "r3"))

    audit.record(
        request_id="r4", tool_id="open_app", params={"app": "editor"},
        policy_decision="allowed", outcome="ok", duration_ms=50
    )
    db.write("UPDATE action_audit SET created_at = ? WHERE request_id = ?", (base_ts + 2300, "r4"))

    habits = mine_habits(db, min_count=2)
    assert any("After opening Brave, you often open VS Code" in h for h in habits)


def test_mine_time_of_day_habits(tmp_path):
    db = _init_db(tmp_path)
    audit = AuditLog(db)
    import datetime
    now = datetime.datetime.now()

    # Create 2 late night youtube search actions
    dt1 = now.replace(hour=23, minute=30, second=0, microsecond=0)
    dt2 = dt1 - datetime.timedelta(days=1)

    audit.record(
        request_id="r10", tool_id="youtube_search", params={"query": "lo-fi"},
        policy_decision="allowed", outcome="ok", duration_ms=50
    )
    db.write("UPDATE action_audit SET created_at = ? WHERE request_id = ?", (int(dt1.timestamp()), "r10"))

    audit.record(
        request_id="r11", tool_id="youtube_search", params={"query": "lo-fi"},
        policy_decision="allowed", outcome="ok", duration_ms=50
    )
    db.write("UPDATE action_audit SET created_at = ? WHERE request_id = ?", (int(dt2.timestamp()), "r11"))

    habits = mine_habits(db, min_count=2)
    assert any("Late at night, you often search YouTube for 'lo-fi'" in h for h in habits)


def test_render_habits_digest():
    habits = [
        "After opening Brave, you often open VS Code.",
        "Late at night, you often search YouTube for 'lo-fi'.",
    ]
    rendered = render_habits_digest(habits)
    assert rendered.startswith("<user_habits>\n")
    assert rendered.endswith("\n</user_habits>")
    assert "- After opening Brave, you often open VS Code." in rendered
    assert "- Late at night, you often search YouTube for 'lo-fi'." in rendered


def test_describe_action_covers_all_schema_actions():
    """F21: describe_action must return a non-empty string for every schema action."""
    from friday.llm.schema import PARAM_SCHEMA

    for tool_id in PARAM_SCHEMA:
        if tool_id in ("chat", "none"):
            continue
        desc = describe_action(tool_id, "{}", gerund=False)
        assert desc is not None, f"describe_action returned None for tool_id={tool_id}"
        assert len(desc) > 0

        desc_gerund = describe_action(tool_id, "{}", gerund=True)
        assert desc_gerund is not None, f"describe_action(gerund=True) returned None for tool_id={tool_id}"
        assert len(desc_gerund) > 0
