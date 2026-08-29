"""FR-58 contract: EVERY executed dispatch writes exactly one audit row.

Before this existed, FR-58 ("audit records everything") was enforced nowhere.
Five call sites happened to write rows; the confirmed dispatches — wifi off,
close the window, overwrite the clipboard, read it aloud — and every web search
wrote none at all (audit H1). Those are precisely the actions the audit exists
for, and they were the invisible ones.

This walks the plan schema rather than a hand-written list, so a tool added
later without an audit row fails here instead of shipping silent.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

import friday.tools.clipboard as clip
from friday.errors import Outcome
from friday.llm.schema import PARAM_SCHEMA
from friday.store.audit import AuditLog
from friday.store.db import Database
from friday.store.prefs import PendingPreference, PrefStore
from friday.tools import executor as ex
from friday.tools.executor import ToolResult
from friday.tools.registry import REGISTRY
from friday.turn import PendingAction, resolve_pending, run_turn

# Valid params per tool, drawn from the schema's own enums so a vocabulary
# change here fails loudly instead of silently skipping a tool.
_PARAMS: dict[str, dict[str, str]] = {
    "open_app": {"app": "browser"},
    "open_youtube": {},
    "youtube_search": {"query": "lofi"},
    "system_volume": {"direction": "up"},
    "system_brightness": {"direction": "up"},
    "system_media": {"action": "play_pause"},
    "system_wifi": {"state": "on"},
    "hypr_workspace": {"workspace": "3"},
    "hypr_window": {"action": "fullscreen"},
    "file_open": {"alias": "notes"},
}


@dataclass
class StubClient:
    reply: str

    def complete(self, *, system: str, user: str, grammar: str) -> str:
        return self.reply

    def health(self) -> bool:
        return True


def _plan_json(name: str, params: dict[str, str]) -> str:
    import json

    return json.dumps({"action": {"name": name, "params": params}})


@pytest.fixture
def store(tmp_path):
    db = Database(tmp_path / "memory.db")
    return db, AuditLog(db), PrefStore(db)


@pytest.fixture
def ok_executor(monkeypatch):
    async def fake_execute(spec, params, request_id, dry_run=False):
        return ToolResult(Outcome.OK, "thing", duration_ms=7)

    monkeypatch.setattr(ex, "execute", fake_execute)


def _rows(db):
    return db.query("SELECT tool_id, outcome FROM action_audit")


def test_registry_schema_and_params_table_agree():
    """The table above must cover every registry tool — otherwise this file
    silently stops testing a tool the moment one is added."""
    assert set(_PARAMS) == set(REGISTRY), (
        "add the new registry tool to _PARAMS so it is covered by the contract"
    )
    for name in _PARAMS:
        assert name in PARAM_SCHEMA


@pytest.mark.parametrize("tool_id", sorted(_PARAMS))
def test_every_registry_dispatch_writes_exactly_one_row(tool_id, store, ok_executor):
    db, audit, prefs = store
    r = asyncio.run(run_turn(
        "do the thing", StubClient(_plan_json(tool_id, _PARAMS[tool_id])),
        request_id=f"rid-{tool_id}", audit=audit, prefs=prefs,
    ))
    assert r.dispatched, f"{tool_id} did not dispatch; the case proves nothing"
    rows = _rows(db)
    assert len(rows) == 1, f"{tool_id} wrote {len(rows)} audit rows, expected 1"
    assert rows[0]["tool_id"] == tool_id


# --- the confirmed dispatches: H1's blind spot -----------------------------


def test_confirmed_registry_dispatch_writes_a_row(store, ok_executor):
    db, audit, _ = store
    pending = PendingAction("system_wifi", {"state": "off"}, "turn off Wi-Fi")
    asyncio.run(resolve_pending(
        pending, "yes", prefs=None, audit=audit, request_id="c1",
    ))
    rows = _rows(db)
    assert [(r["tool_id"], r["outcome"]) for r in rows] == [("system_wifi", "ok")]


def test_confirmed_clipboard_set_writes_a_row_without_the_text(store, monkeypatch):
    db, audit, _ = store
    monkeypatch.setattr(clip, "set_clipboard", lambda text, **kw: True)
    pending = PendingAction("clipboard_set", {"text": "swordfish"}, "overwrite clipboard")
    asyncio.run(resolve_pending(
        pending, "yes", prefs=None, audit=audit, request_id="c2",
    ))
    rows = db.query("SELECT tool_id, args_redacted FROM action_audit")
    assert len(rows) == 1 and rows[0]["tool_id"] == "clipboard_set"
    assert "swordfish" not in rows[0]["args_redacted"], "clipboard text reached disk"
    assert "9" in rows[0]["args_redacted"], "the length should be recorded"


def test_confirmed_clipboard_read_writes_a_row_without_the_contents(store, monkeypatch):
    db, audit, _ = store
    monkeypatch.setattr(clip, "read_clipboard", lambda: "hunter2-correct-horse")
    pending = PendingAction("clipboard_read", {}, "read the clipboard aloud")
    asyncio.run(resolve_pending(
        pending, "yes", prefs=None, audit=audit, request_id="c3",
    ))
    rows = db.query("SELECT tool_id, args_redacted FROM action_audit")
    assert len(rows) == 1 and rows[0]["tool_id"] == "clipboard_read"
    assert "hunter2" not in rows[0]["args_redacted"]


def test_declined_confirm_writes_a_declined_row(store, ok_executor):
    """ADR-072 (OQ-37, answered 2026-08-29): a decline is not a dispatch, and it
    is still recorded. "Friday proposed turning off Wi-Fi and I said no" is the
    more interesting half of that exchange and was invisible to every later
    read. The row must say plainly that nothing ran."""
    db, audit, _ = store
    pending = PendingAction("system_wifi", {"state": "off"}, "turn off Wi-Fi")
    asyncio.run(resolve_pending(
        pending, "no", prefs=None, audit=audit, request_id="c4",
    ))
    rows = db.query(
        "SELECT tool_id, outcome, policy_decision, duration_ms FROM action_audit"
    )
    assert len(rows) == 1
    assert rows[0]["tool_id"] == "system_wifi"
    assert rows[0]["outcome"] == "declined"
    assert rows[0]["policy_decision"] == "declined"
    assert rows[0]["duration_ms"] == 0, "nothing ran, so nothing took time"


def test_declined_confirm_dispatches_nothing(store, ok_executor):
    """The row must not be mistaken for evidence that something happened."""
    db, audit, _ = store
    pending = PendingAction("system_wifi", {"state": "off"}, "turn off Wi-Fi")
    asyncio.run(resolve_pending(
        pending, "no", prefs=None, audit=audit, request_id="c5",
    ))
    assert db.query("SELECT 1 FROM action_audit WHERE outcome = 'ok'") == []


def test_a_declined_action_never_becomes_a_habit(store, ok_executor):
    """`mine_habits` filters on `outcome='ok'`, so declined rows must not feed
    it — a refusal turning into a suggested habit would be the worst possible
    reading of this data (ADR-072)."""
    from friday.store.habits import mine_habits

    db, audit, _ = store
    pending = PendingAction("system_wifi", {"state": "off"}, "turn off Wi-Fi")
    for i in range(5):  # well past min_count
        asyncio.run(resolve_pending(
            pending, "no", prefs=None, audit=audit, request_id=f"d{i}",
        ))
    assert len(_rows(db)) == 5
    assert mine_habits(db) == []


def test_declined_confirm_records_no_user_content(store, monkeypatch):
    """The decline row obeys the same redaction rule as the executed one —
    `turn.audit_params` is the single place that rule lives (FR-26/FR-57)."""
    db, audit, _ = store
    asyncio.run(resolve_pending(
        PendingAction("clipboard_set", {"text": "swordfish"}, "overwrite clipboard"),
        "no", prefs=None, audit=audit, request_id="c6",
    ))
    args = db.query("SELECT args_redacted FROM action_audit")[0]["args_redacted"]
    assert "swordfish" not in args
    assert "9" in args, "the length is the whole record"


def test_declined_preference_is_recorded_by_key_only(store):
    db, audit, prefs = store
    asyncio.run(resolve_pending(
        PendingPreference(key="name", value="Subham"), "no",
        prefs=prefs, audit=audit, request_id="c7",
    ))
    rows = db.query("SELECT tool_id, outcome, args_redacted FROM action_audit")
    assert len(rows) == 1
    assert rows[0]["tool_id"] == "remember_preference"
    assert rows[0]["outcome"] == "declined"
    assert "Subham" not in rows[0]["args_redacted"], "the value is user data"
    assert "name" in rows[0]["args_redacted"]


def test_audit_params_is_the_only_place_the_redaction_rule_lives():
    """Executed and declined paths must describe a pending identically — the
    two-copies-of-one-rule shape is exactly what C1 was."""
    from friday.turn import audit_params

    assert audit_params(
        PendingAction("clipboard_set", {"text": "abcd"}, "d")) == {"chars": "4"}
    assert audit_params(PendingAction("clipboard_read", {}, "d")) == {}
    assert audit_params(
        PendingAction("system_wifi", {"state": "off"}, "d")) == {"state": "off"}
    assert audit_params(PendingPreference(key="name", value="Subham")) == {"key": "name"}


# --- web_search: audited on every outcome ----------------------------------


class _FakeSearch:
    def __init__(self, results):
        self._results = results

    def query(self, q):
        from friday.tools.search import SearchUnavailable

        if self._results is None:
            raise SearchUnavailable("down")
        return self._results


_DEFAULT_RESULTS = object()


def _search_turn(audit, *, connected=True, results=_DEFAULT_RESULTS, client=None):
    from friday.tools.search import SearchResult

    if results is _DEFAULT_RESULTS:
        results = [SearchResult("T", "https://x.test/a", "a body with words in it")]
    return asyncio.run(run_turn(
        "who won", client or StubClient(_plan_json("web_search", {"query": "who won"})),
        request_id="s1", audit=audit, connected=connected,
        search_client=_FakeSearch(results),
    ))


def test_web_search_audits_a_successful_search(store, monkeypatch):
    db, audit, _ = store
    from friday.llm import grounding

    monkeypatch.setattr(grounding, "ground", lambda c, q, b: "Team A won.")
    _search_turn(audit)
    rows = _rows(db)
    assert [(r["tool_id"], r["outcome"]) for r in rows] == [("web_search", "ok")]


def test_web_search_audits_the_refused_and_failed_paths(store):
    db, audit, _ = store
    _search_turn(audit, connected=False)
    assert [(r["tool_id"], r["outcome"]) for r in _rows(db)] == [("web_search", "disabled")]

    db.write("DELETE FROM action_audit", ())
    _search_turn(audit, results=None)
    assert [(r["tool_id"], r["outcome"]) for r in _rows(db)] == [("web_search", "net_down")]


def test_web_search_query_is_capped_in_the_audit_row(store):
    db, audit, _ = store
    long_q = "x" * 300
    asyncio.run(run_turn(
        "q", StubClient(_plan_json("web_search", {"query": long_q})),
        request_id="s2", audit=audit, connected=False,
        search_client=_FakeSearch([]),
    ))
    args = db.query("SELECT args_redacted FROM action_audit")[0]["args_redacted"]
    assert "x" * 80 in args and "x" * 81 not in args


def test_web_search_rows_make_the_habits_branch_reachable(store, monkeypatch):
    """H1's knock-on: `habits.describe_action`'s web_search branch mined a table
    nothing was writing to, so it was permanently unreachable dead logic."""
    db, audit, _ = store
    from friday.llm import grounding
    from friday.store.habits import describe_action

    monkeypatch.setattr(grounding, "ground", lambda c, q, b: "Team A won.")
    _search_turn(audit)
    row = db.query("SELECT tool_id, args_redacted FROM action_audit")[0]
    assert describe_action(row["tool_id"], row["args_redacted"]) == (
        "search the web for 'who won'"
    )


# --- cancel_reminder dispatches, so it audits too --------------------------


def test_cancel_reminder_dispatch_writes_a_row(store):
    db, audit, prefs = store
    from friday.store.reminders import ReminderStore

    ReminderStore(db).create(60, "pasta")
    r = asyncio.run(run_turn(
        "cancel my timer", StubClient(_plan_json("cancel_reminder", {})),
        request_id="r1", audit=audit, prefs=prefs,
    ))
    assert r.dispatched
    assert [(x["tool_id"], x["outcome"]) for x in _rows(db)] == [("cancel_reminder", "ok")]


def test_cancel_reminder_picks_the_most_recently_created(store):
    """H7: `alist_active` orders by fire_at ASC, so the old `active[-1]` cancelled
    the reminder firing FARTHEST in the future. With a 10-minute pasta timer and
    a 3-hour meeting reminder outstanding, "cancel my timer" killed the meeting
    and said only "Cancelled." — no way for the user to notice."""
    db, audit, prefs = store
    from friday.store.reminders import ReminderStore

    rs = ReminderStore(db)
    meeting = rs.create(3 * 3600, "the 3pm meeting", kind="reminder")
    pasta = rs.create(600, "check the pasta")  # created later, fires sooner

    r = asyncio.run(run_turn(
        "cancel my timer", StubClient(_plan_json("cancel_reminder", {})),
        request_id="r2", audit=audit, prefs=prefs,
    ))

    still_active = {x.id for x in rs.list_active()}
    assert pasta.id not in still_active, "the newest reminder should be cancelled"
    assert meeting.id in still_active, "H7: the meeting was cancelled instead"
    assert "check the pasta" in r.spoken, "say WHICH one, so a wrong pick is audible"


def test_cancel_reminder_with_nothing_active_says_so(store):
    db, audit, prefs = store
    r = asyncio.run(run_turn(
        "cancel my timer", StubClient(_plan_json("cancel_reminder", {})),
        request_id="r3", audit=audit, prefs=prefs,
    ))
    assert not r.dispatched
    assert r.spoken == "No active timer to cancel."
    assert _rows(db) == []
