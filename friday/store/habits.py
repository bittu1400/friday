"""Habit-driven suggestions mining (G8 Stage 2, ADR-049).

Mines user activity patterns from the local SQLite `action_audit` table
(redacted parameters, already on disk per FR-57/58).

Two classes of habits:
1. Sequential transitions (Action A -> Action B within 30 minutes).
2. Time-of-day affinities (sunrise/early morning: 05-08, morning: 08-12,
   afternoon: 12-17, sunset/early evening: 17-20, evening: 20-23, late night: 23-05).

Invariants preserved:
- Invariant #7: No raw transcripts or audio on disk.
- Invariant #1 / #4: Suggestions are purely conversational speech (ADR-048),
  never automatic or unprompted side effects.
- Lightweight & fast: Pure SQLite query executed in <2 ms.
"""

from __future__ import annotations

import datetime
import json
import time
from collections import Counter
from typing import Mapping

from .db import Database

# App display names for human-readable summaries
_APP_NAMES: Mapping[str, str] = {
    "browser": "Brave",
    "editor": "VS Code",
    "terminal": "the terminal",
    "video": "mpv",
    "vlc": "VLC",
}


def time_of_day_slot(ts: int) -> str:
    """Map a unix timestamp to a natural, granular time-of-day slot."""
    dt = datetime.datetime.fromtimestamp(ts)
    hour = dt.hour
    if 5 <= hour < 8:
        return "around sunrise / early morning"
    elif 8 <= hour < 12:
        return "in the morning"
    elif 12 <= hour < 17:
        return "in the afternoon"
    elif 17 <= hour < 20:
        return "around sunset / early evening"
    elif 20 <= hour < 23:
        return "in the evening"
    else:
        return "late at night"


def describe_action(tool_id: str, args_redacted_json: str, *, gerund: bool = False) -> str | None:
    """Return a plain-English description of a tool action."""
    try:
        args = json.loads(args_redacted_json) if args_redacted_json else {}
    except Exception:
        args = {}

    if tool_id == "open_app":
        app_key = args.get("app", "")
        display = _APP_NAMES.get(app_key, f"app '{app_key}'" if app_key else "an app")
        return f"opening {display}" if gerund else f"open {display}"

    elif tool_id == "open_youtube":
        return "opening YouTube" if gerund else "open YouTube"

    elif tool_id == "youtube_search":
        q = args.get("query", "")
        if q:
            return f"searching YouTube for '{q}'" if gerund else f"search YouTube for '{q}'"
        return "searching YouTube" if gerund else "search YouTube"

    elif tool_id == "web_search":
        q = args.get("query", "")
        if q:
            return f"searching the web for '{q}'" if gerund else f"search the web for '{q}'"
        return "searching the web" if gerund else "search the web"

    elif tool_id == "remember_preference":
        k = args.get("key", "")
        return f"remembering preference '{k}'" if (gerund and k) else (f"remember preference '{k}'" if k else ("remembering a preference" if gerund else "remember a preference"))

    elif tool_id == "forget_preference":
        k = args.get("key", "")
        return f"forgetting preference '{k}'" if (gerund and k) else (f"forget preference '{k}'" if k else ("forgetting a preference" if gerund else "forget a preference"))

    elif tool_id == "set_reminder":
        return "setting a timer" if gerund else "set a timer"

    elif tool_id == "list_reminders":
        return "checking timers" if gerund else "check timers"

    elif tool_id == "cancel_reminder":
        return "cancelling a timer" if gerund else "cancel a timer"

    elif tool_id == "set_dnd":
        return "enabling quiet mode" if gerund else "enable quiet mode"

    elif tool_id == "resume_dnd":
        return "disabling quiet mode" if gerund else "disable quiet mode"

    elif tool_id == "system_volume":
        d = args.get("direction", "")
        return f"adjusting volume ({d})" if (gerund and d) else (f"adjust volume ({d})" if d else ("adjusting volume" if gerund else "adjust volume"))

    elif tool_id == "system_brightness":
        d = args.get("direction", "")
        return f"adjusting brightness ({d})" if (gerund and d) else (f"adjust brightness ({d})" if d else ("adjusting brightness" if gerund else "adjust brightness"))

    elif tool_id == "system_media":
        return "controlling media playback" if gerund else "control media playback"

    elif tool_id == "system_wifi":
        s = args.get("state", "")
        return f"turning Wi-Fi {s}" if (gerund and s) else (f"turn Wi-Fi {s}" if s else ("toggling Wi-Fi" if gerund else "toggle Wi-Fi"))

    elif tool_id == "hypr_workspace":
        w = args.get("workspace", "")
        return f"switching to workspace {w}" if (gerund and w) else (f"switch to workspace {w}" if w else ("switching workspaces" if gerund else "switch workspaces"))

    elif tool_id == "hypr_window":
        a = args.get("action", "")
        return f"managing window ({a})" if (gerund and a) else (f"manage window ({a})" if a else ("managing windows" if gerund else "manage windows"))

    elif tool_id == "file_open":
        a = args.get("alias", "")
        return f"opening file '{a}'" if (gerund and a) else (f"open file '{a}'" if a else ("opening a file" if gerund else "open a file"))

    elif tool_id == "create_note":
        return "saving a note" if gerund else "save a note"

    elif tool_id == "read_notes":
        return "reading notes" if gerund else "read notes"

    elif tool_id == "clipboard_read":
        return "reading the clipboard" if gerund else "read the clipboard"

    elif tool_id == "clipboard_set":
        return "copying to clipboard" if gerund else "copy to clipboard"

    elif tool_id == "dictation_mode":
        return "toggling dictation mode" if gerund else "toggle dictation mode"

    elif tool_id == "dictation_type":
        return "typing dictation" if gerund else "type dictation"

    return None


def mine_habits(
    db: Database,
    *,
    lookback_days: int = 30,
    min_count: int = 2,
    max_habits: int = 6,
) -> list[str]:
    """Analyze recent successful actions in `action_audit` and return top habit strings."""
    cutoff = int(time.time()) - (lookback_days * 86400)
    rows = db.query(
        "SELECT tool_id, args_redacted, created_at "
        "FROM action_audit "
        "WHERE outcome = 'ok' AND created_at >= ? "
        "ORDER BY created_at ASC",
        (cutoff,),
    )
    if not rows:
        return []

    habits: list[tuple[int, str]] = []

    # 1. Sequence patterns: A -> B within 30 min (1800 s)
    seq_counter: Counter[tuple[str, str]] = Counter()
    for i in range(len(rows) - 1):
        r1 = rows[i]
        r2 = rows[i + 1]
        dt = r2["created_at"] - r1["created_at"]
        if 0 < dt <= 1800:
            desc1 = describe_action(r1["tool_id"], r1["args_redacted"], gerund=True)
            desc2 = describe_action(r2["tool_id"], r2["args_redacted"], gerund=False)
            if desc1 and desc2 and desc1 != desc2:
                seq_counter[(desc1, desc2)] += 1

    for (d1, d2), count in seq_counter.items():
        if count >= min_count:
            habits.append((count, f"After {d1}, you often {d2}."))

    # 2. Time-of-day patterns
    tod_counter: Counter[tuple[str, str]] = Counter()
    for r in rows:
        slot = time_of_day_slot(r["created_at"])
        desc = describe_action(r["tool_id"], r["args_redacted"], gerund=False)
        if desc:
            tod_counter[(slot, desc)] += 1

    for (slot, desc), count in tod_counter.items():
        if count >= min_count:
            habits.append((count, f"{slot.capitalize()}, you often {desc}."))

    # Sort habits by frequency descending, then deduplicate
    habits.sort(key=lambda item: item[0], reverse=True)
    seen: set[str] = set()
    result: list[str] = []
    for _, habit_str in habits:
        if habit_str not in seen:
            seen.add(habit_str)
            result.append(habit_str)
        if len(result) >= max_habits:
            break

    return result


def render_habits_digest(habits: list[str]) -> str:
    """Render habit list into an inert data-framed block for the chat system prompt."""
    if not habits:
        return ""
    lines = ["<user_habits>"]
    for h in habits:
        # Sanitize: strip newlines/control chars, enforce 150-char line cap
        clean = " ".join(h.split())[:150].strip()
        lines.append(f"- {clean}")
    lines.append("</user_habits>")
    return "\n".join(lines)
