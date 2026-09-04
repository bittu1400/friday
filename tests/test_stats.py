"""Tests for friday.stats_cli (ADR-107, FR-128)."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from friday.stats_cli import (
    classify_tool,
    compute_metrics,
    percentile,
    query_audit_stats,
    render_table,
    main,
)
from friday.store.audit import AuditLog
from friday.store.db import Database


def test_percentile_computation():
    assert percentile([], 50) == 0.0
    assert percentile([10], 50) == 10.0
    assert percentile([10, 20, 30, 40, 50], 50) == 30.0
    assert percentile([10, 20, 30, 40, 50], 95) == 48.0
    assert percentile([100, 200], 50) == 150.0


def test_classify_tool():
    assert classify_tool("open_app") == "launches"
    assert classify_tool("open_youtube") == "launches"
    assert classify_tool("system_volume") == "commands"
    assert classify_tool("set_reminder") == "commands"
    assert classify_tool("web_search") == "search"
    assert classify_tool("remember_preference") == "preferences"
    assert classify_tool("dictation_mode") == "intercepts"
    assert classify_tool("unknown_custom_tool") == "other"
    # D37: chat is its own class, not "other" — it is the SLOWEST turn class
    # and burying it with genuinely-unknown tools is F29's mistake again.
    assert classify_tool("chat") == "chat"
    # `detach=True` in the registry, so it pays the launch grace. It was in no
    # class at all until 2026-09-04, with four live rows already recorded.
    assert classify_tool("file_open") == "launches"


def test_every_capability_that_can_be_audited_has_a_class():
    """`ACTION_CLASSES` is one more hand-written list that names capabilities,
    and every one of those has gone stale at least once — `STT_HOTWORDS` (D26,
    D31), the planner prompt (D31), the chat persona (D24, F2). This one had
    too: `file_open` shipped with G12 and never had a class.

    `none` is excluded because it is not an action and writes no row.
    """
    from friday.capabilities import CAPABILITIES
    from friday.stats_cli import ACTION_CLASSES

    missing = [c for c in CAPABILITIES if c != "none" and c not in ACTION_CLASSES]
    assert missing == [], (
        f"capabilities with no stats class: {missing}. `just stats` would "
        f"bucket them as 'other', which is where a latency class goes to hide."
    )


def test_stats_survives_a_class_that_is_not_in_the_hardcoded_bucket_list(tmp_path):
    """`by_class` used to be a hand-listed dict that `query_audit_stats` indexes
    directly, so a new class raised KeyError on its first row — the latency tool
    crashing on the class it was just extended to measure. It is derived now."""
    db = Database(tmp_path / "memory.db")
    AuditLog(db).record(
        request_id="c1", tool_id="chat", params={},
        policy_decision="allowed", outcome="ok", duration_ms=1496,
    )
    data = query_audit_stats(db, days=30)
    assert data["by_class"]["chat"]["count"] == 1
    assert data["by_class"]["chat"]["p50_ms"] == 1496.0
    assert "chat" not in data.get("by_class", {}).get("other", {}), "not 'other'"
    render_table(data, show_tools=True)  # must not raise


def test_compute_metrics_empty():
    m = compute_metrics([])
    assert m["count"] == 0
    assert m["p50_ms"] == 0.0
    assert m["mean_ms"] == 0.0


def test_compute_metrics_values():
    m = compute_metrics([10, 20, 30, 40, 50])
    assert m["count"] == 5
    assert m["min_ms"] == 10
    assert m["max_ms"] == 50
    assert m["mean_ms"] == 30.0
    assert m["p50_ms"] == 30.0


def test_query_audit_stats_with_data(tmp_path: Path):
    db_path = tmp_path / "test_stats.db"
    db = Database(db_path)
    audit = AuditLog(db)

    # Insert sample rows
    audit.record(
        request_id="req1",
        tool_id="system_volume",
        params={"level": "50"},
        policy_decision="allowed",
        outcome="ok",
        duration_ms=5,
    )
    audit.record(
        request_id="req2",
        tool_id="open_app",
        params={"app": "browser"},
        policy_decision="allowed",
        outcome="ok",
        duration_ms=402,
    )
    audit.record(
        request_id="req3",
        tool_id="web_search",
        params={"query": "weather"},
        policy_decision="allowed",
        outcome="ok",
        duration_ms=850,
    )

    stats = query_audit_stats(db, days=30)
    assert stats["total_events"] == 3
    assert "commands" in stats["by_class"]
    assert "launches" in stats["by_class"]
    assert "search" in stats["by_class"]

    assert stats["by_class"]["commands"]["count"] == 1
    assert stats["by_class"]["commands"]["p50_ms"] == 5.0

    assert stats["by_class"]["launches"]["count"] == 1
    assert stats["by_class"]["launches"]["p50_ms"] == 402.0

    assert stats["by_class"]["search"]["count"] == 1
    assert stats["by_class"]["search"]["p50_ms"] == 850.0

    table = render_table(stats, show_tools=True)
    assert "commands" in table
    assert "launches" in table
    assert "search" in table


def test_stats_cli_main_json(tmp_path: Path, capsys: pytest.CaptureFixture):
    db_path = tmp_path / "cli_test.db"
    db = Database(db_path)
    AuditLog(db).record(
        request_id="req-cli-1",
        tool_id="open_app",
        params={"app": "terminal"},
        policy_decision="allowed",
        outcome="ok",
        duration_ms=400,
    )
    db.close()

    exit_code = main(["--db", str(db_path), "--json"])
    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["total_events"] == 1
    assert data["by_class"]["launches"]["count"] == 1
    assert data["by_class"]["launches"]["p50_ms"] == 400.0
