"""Latency and TTFA statistics reporter (`just stats` / `friday --stats`).

Queries `action_audit` from SQLite memory database and computes empirical
latency metrics (p50, p95, mean, min, max) broken down by action class:
  - Commands (system controls, workspace, notes, reminders, clipboard)
  - Launches (GUI application launches: open_app, youtube)
  - Search (web_search)
  - Preferences (remember_preference, forget_preference)
  - Intercepts (dictation, conversational DND, sign-off)

Consequences of ADR-107 & FR-128:
Reporting latency broken down by action class prevents a single metric from
obscuring the 400 ms launch-grace delta between commands and GUI apps.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import config
from .store.db import Database


ACTION_CLASSES: dict[str, str] = {
    # Commands
    "system_volume": "commands",
    "system_brightness": "commands",
    "system_media": "commands",
    "system_wifi": "commands",
    "hypr_workspace": "commands",
    "hypr_window": "commands",
    "set_reminder": "commands",
    "cancel_reminder": "commands",
    "create_note": "commands",
    "read_notes": "commands",
    "list_reminders": "commands",
    "clipboard_set": "commands",
    "clipboard_read": "commands",
    # Launches
    "open_app": "launches",
    "open_youtube": "launches",
    "youtube_search": "launches",
    # Search
    "web_search": "search",
    # Preferences
    "remember_preference": "preferences",
    "forget_preference": "preferences",
    # Intercepts
    "dictation_mode": "intercepts",
    "dictation_type": "intercepts",
    "set_dnd": "intercepts",
    "resume_dnd": "intercepts",
    "signoff_summary": "intercepts",
}


def classify_tool(tool_id: str) -> str:
    """Map tool_id to action class."""
    return ACTION_CLASSES.get(tool_id, "other")


def percentile(values: Sequence[float | int], p: float) -> float:
    """Compute empirical percentile using linear interpolation."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    idx = (len(s) - 1) * (p / 100.0)
    low = int(math.floor(idx))
    high = int(math.ceil(idx))
    if low == high:
        return float(s[low])
    weight = idx - low
    return float(s[low] * (1.0 - weight) + s[high] * weight)


def compute_metrics(durations: list[int]) -> dict[str, Any]:
    """Calculate summary statistics for a list of duration_ms values."""
    if not durations:
        return {
            "count": 0,
            "min_ms": 0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "mean_ms": 0.0,
            "max_ms": 0,
        }
    return {
        "count": len(durations),
        "min_ms": min(durations),
        "p50_ms": round(percentile(durations, 50), 1),
        "p95_ms": round(percentile(durations, 95), 1),
        "mean_ms": round(sum(durations) / len(durations), 1),
        "max_ms": max(durations),
    }


def query_audit_stats(
    db: Database,
    *,
    days: int = 30,
) -> dict[str, Any]:
    """Query action_audit rows from SQLite within `days` window and aggregate stats."""
    cutoff = int(time.time()) - days * 86400
    rows = db.query(
        "SELECT tool_id, outcome, duration_ms, created_at "
        "FROM action_audit "
        "WHERE created_at >= ? "
        "ORDER BY created_at ASC",
        (cutoff,),
    )

    by_class: dict[str, list[int]] = {
        "commands": [],
        "launches": [],
        "search": [],
        "preferences": [],
        "intercepts": [],
        "other": [],
    }
    by_tool: dict[str, list[int]] = {}

    for r in rows:
        tid = r["tool_id"] if "tool_id" in r.keys() else "unknown"
        dur = int(r["duration_ms"]) if "duration_ms" in r.keys() else 0
        cls_name = classify_tool(tid)
        by_class[cls_name].append(dur)
        by_tool.setdefault(tid, []).append(dur)

    class_stats = {
        cname: compute_metrics(durs)
        for cname, durs in by_class.items()
        if durs
    }
    tool_stats = {
        tname: compute_metrics(durs)
        for tname, durs in sorted(by_tool.items())
    }
    all_durs = [int(r["duration_ms"]) for r in rows if "duration_ms" in r.keys()]
    total_stats = compute_metrics(all_durs)

    return {
        "days": days,
        "total_events": len(rows),
        "overall": total_stats,
        "by_class": class_stats,
        "by_tool": tool_stats,
    }


def render_table(data: dict[str, Any], *, show_tools: bool = False) -> str:
    """Render structured ASCII summary table of latency metrics."""
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append(f"  Friday Latency & TTFA Metrics (Last {data['days']} Days)")
    lines.append("=" * 70)

    if data["total_events"] == 0:
        lines.append("  No action audit records found in the specified time window.")
        lines.append("=" * 70)
        return "\n".join(lines)

    lines.append(f"  Total actions audited: {data['total_events']}")
    lines.append("-" * 70)
    lines.append(f"  {'Action Class':<18} {'Count':>6} {'Min(ms)':>9} {'p50(ms)':>9} {'p95(ms)':>9} {'Mean(ms)':>9} {'Max(ms)':>7}")
    lines.append("-" * 70)

    for cls_name, m in sorted(data["by_class"].items()):
        lines.append(
            f"  {cls_name:<18} {m['count']:>6} {m['min_ms']:>9} {m['p50_ms']:>9.1f} {m['p95_ms']:>9.1f} {m['mean_ms']:>9.1f} {m['max_ms']:>7}"
        )

    lines.append("-" * 70)
    ov = data["overall"]
    lines.append(
        f"  {'ALL ACTIONS':<18} {ov['count']:>6} {ov['min_ms']:>9} {ov['p50_ms']:>9.1f} {ov['p95_ms']:>9.1f} {ov['mean_ms']:>9.1f} {ov['max_ms']:>7}"
    )

    if show_tools and data["by_tool"]:
        lines.append("\n" + "-" * 70)
        lines.append(f"  {'Tool Breakdown':<22} {'Count':>6} {'p50(ms)':>9} {'p95(ms)':>9} {'Mean(ms)':>9}")
        lines.append("-" * 70)
        for tid, m in sorted(data["by_tool"].items()):
            lines.append(
                f"  {tid:<22} {m['count']:>6} {m['p50_ms']:>9.1f} {m['p95_ms']:>9.1f} {m['mean_ms']:>9.1f}"
            )

    lines.append("=" * 70)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="friday-stats", description="Inspect latency and TTFA metrics by action class.")
    ap.add_argument("--db", type=Path, default=config.MEMORY_DB, help="Path to SQLite memory database")
    ap.add_argument("--days", type=int, default=30, help="Days of history to analyze (default: 30)")
    ap.add_argument("--tools", action="store_true", help="Include per-tool breakdown")
    ap.add_argument("--json", action="store_true", help="Output results as JSON")
    args = ap.parse_args(argv)

    if not args.db.exists():
        if args.json:
            print(json.dumps({"error": f"Database {args.db} does not exist", "total_events": 0}))
        else:
            print(f"Database {args.db} does not exist. Run Friday to populate actions.")
        return 0

    db = Database(args.db)
    try:
        data = query_audit_stats(db, days=args.days)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(render_table(data, show_tools=args.tools))
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
