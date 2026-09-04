import asyncio
from pathlib import Path
import pytest

from friday import config
from friday.dialogue import Dialogue
from friday.llm.client import LlamaClient
from friday.proactive.notifier import notify
from friday.store.audit import AuditLog
from friday.store.db import Database
from friday.store.notes import NoteStore
from friday.store.prefs import PendingPreference, PrefStore
from friday.store.reminders import ReminderStore
from friday.tools import clipboard, typer
from friday.turn import PendingAction, resolve_pending, run_turn


class _PanicBoomClient(LlamaClient):
    """Stub client that should never be called when panic gate blocks execution."""
    def complete(self, **kw):
        raise AssertionError("LLM should not be called when panic gate blocks execution")

    def health(self) -> bool:
        return True


class _PlanClient(LlamaClient):
    """Returns one fixed plan, so the test drives the WIRING.

    These tests called `_do_web_search`, `_do_forget`, `_do_set_reminder`,
    `_do_cancel_reminder`, `_do_create_note` and `confirm_preference` directly
    while each carried its own `config.is_disabled()` block. Phase 3 criterion
    3.5 replaced those eight hand-written blocks with ONE gate derived from
    `risk`, so a test that calls the handler under the gate can no longer see
    it — and a handler-level test could never have caught F1 anyway, which was
    a gate missing from ten paths, not a gate that was wrong. Driving
    `run_turn` tests the join, which is M2's lesson.
    """

    def __init__(self, plan: str) -> None:  # no super().__init__: never connects
        self._plan = plan

    def complete(self, **kw) -> str:
        return self._plan

    def health(self) -> bool:
        return True


@pytest.fixture
def test_db(tmp_path: Path):
    db = Database(tmp_path / "friday.db")
    try:
        yield db
    finally:
        db.close()


def test_panic_gate_1_web_search(test_db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "is_disabled", lambda: True)
    audit = AuditLog(test_db)
    
    class FailingSearchClient:
        def query(self, q):
            raise AssertionError("SearchClient.query must not be called when disabled")

    res = asyncio.run(run_turn(
        "search the web for news",
        _PlanClient('{"action":{"name":"web_search","params":{"query":"news"}}}'),
        request_id="test-req-1",
        audit=audit,
        search_client=FailingSearchClient(),
    ))
    assert res.spoken == "I'm switched off."
    rows = test_db.query("SELECT tool_id, outcome, policy_decision FROM action_audit WHERE request_id = 'test-req-1'")
    assert len(rows) == 1
    assert rows[0]["tool_id"] == "web_search"
    assert rows[0]["outcome"] == "disabled"
    assert rows[0]["policy_decision"] == "disabled"


def test_panic_gate_2_clipboard_set(test_db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "is_disabled", lambda: True)
    audit = AuditLog(test_db)
    
    # Prove clipboard tool itself fails-closed
    assert clipboard.set_clipboard("secret") is False

    pending = PendingAction("clipboard_set", {"text": "secret"}, "overwrite clipboard")
    spoken = asyncio.run(resolve_pending(
        pending, "yes",
        prefs=None, audit=audit, request_id="test-req-2",
    ))
    assert spoken == "I'm switched off."
    rows = test_db.query("SELECT tool_id, outcome, policy_decision FROM action_audit WHERE request_id = 'test-req-2'")
    assert len(rows) == 1
    assert rows[0]["tool_id"] == "clipboard_set"
    assert rows[0]["outcome"] == "disabled"


def test_panic_gate_3_clipboard_read(test_db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "is_disabled", lambda: True)
    audit = AuditLog(test_db)

    # Prove clipboard tool itself fails-closed
    assert clipboard.read_clipboard() is None

    pending = PendingAction("clipboard_read", {}, "read the clipboard aloud")
    spoken = asyncio.run(resolve_pending(
        pending, "yes",
        prefs=None, audit=audit, request_id="test-req-3",
    ))
    assert spoken == "I'm switched off."
    rows = test_db.query("SELECT tool_id, outcome, policy_decision FROM action_audit WHERE request_id = 'test-req-3'")
    assert len(rows) == 1
    assert rows[0]["tool_id"] == "clipboard_read"
    assert rows[0]["outcome"] == "disabled"


def test_panic_gate_4_dictation_typing(test_db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "is_disabled", lambda: True)
    # Prove typer fails closed
    assert typer.type_text("hello world") is False

    from friday.daemon import Daemon
    from friday.audio.capture import Recorder
    import numpy as np

    from friday.audio.stt import Transcript

    class FakeTranscriber:
        def run(self, pcm):
            return Transcript("test typing sentence")

        def transcribe(self, pcm):
            return "test typing sentence"

    rec = Recorder(gate=lambda: False)
    audit = AuditLog(test_db)
    d = Daemon(
        client=_PanicBoomClient(),
        recorder=rec,
        transcriber=FakeTranscriber(),
        speaker=None,
        audit=audit,
    )
    d._dictation.start()

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        if d._turn_task:
            await d._turn_task
        await d.close()

    asyncio.run(go())
    
    rows = test_db.query("SELECT tool_id, outcome, policy_decision FROM action_audit")
    assert len(rows) == 1
    assert rows[0]["tool_id"] == "dictation_type"
    assert rows[0]["outcome"] == "disabled"


def test_panic_gate_5_confirm_preference(test_db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "is_disabled", lambda: True)
    prefs = PrefStore(test_db)
    audit = AuditLog(test_db)

    pending = PendingPreference("editor", "code")
    spoken = asyncio.run(resolve_pending(
        pending, "yes", prefs=prefs, audit=audit, request_id="test-req-5",
    ))
    assert spoken == "I'm switched off."

    # Verify against SQLite: NO rows inserted
    rows = test_db.query("SELECT * FROM preferences WHERE key = 'editor'")
    assert len(rows) == 0

    audit_rows = test_db.query("SELECT tool_id, outcome, policy_decision FROM action_audit WHERE request_id = 'test-req-5'")
    assert len(audit_rows) == 1
    assert audit_rows[0]["tool_id"] == "remember_preference"
    assert audit_rows[0]["outcome"] == "disabled"


def test_panic_gate_6_forget_preference(test_db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    prefs = PrefStore(test_db)
    prefs.put(PendingPreference("editor", "code"))
    assert prefs.active().get("editor") is not None

    monkeypatch.setattr(config, "is_disabled", lambda: True)
    audit = AuditLog(test_db)
    
    res = asyncio.run(run_turn(
        "forget my editor preference",
        _PlanClient('{"action":{"name":"forget_preference","params":{"key":"editor"}}}'),
        request_id="test-req-6", prefs=prefs, audit=audit,
    ))
    assert res.spoken == "I'm switched off."

    # Verify against SQLite: preference was NOT forgotten
    assert prefs.active().get("editor") is not None

    audit_rows = test_db.query("SELECT tool_id, outcome, policy_decision FROM action_audit WHERE request_id = 'test-req-6'")
    assert len(audit_rows) == 1
    assert audit_rows[0]["tool_id"] == "forget_preference"
    assert audit_rows[0]["outcome"] == "disabled"


def test_panic_gate_7_set_reminder(test_db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "is_disabled", lambda: True)
    prefs = PrefStore(test_db)
    audit = AuditLog(test_db)
    reminders = ReminderStore(test_db)

    res = asyncio.run(run_turn(
        "remind me in five minutes to check the oven",
        _PlanClient('{"action":{"name":"set_reminder","params":'
                    '{"seconds":"300","message":"check oven"}}}'),
        request_id="test-req-7", prefs=prefs, audit=audit,
    ))
    assert res.spoken == "I'm switched off."

    # Verify against SQLite: NO reminder created
    active = asyncio.run(reminders.alist_active())
    assert len(active) == 0

    audit_rows = test_db.query("SELECT tool_id, outcome, policy_decision FROM action_audit WHERE request_id = 'test-req-7'")
    assert len(audit_rows) == 1
    assert audit_rows[0]["tool_id"] == "set_reminder"
    assert audit_rows[0]["outcome"] == "disabled"


def test_panic_gate_8_cancel_reminder(test_db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    reminders = ReminderStore(test_db)
    r = asyncio.run(reminders.acreate(seconds=600, message="important meeting", kind="reminder"))
    assert r is not None

    monkeypatch.setattr(config, "is_disabled", lambda: True)
    prefs = PrefStore(test_db)
    audit = AuditLog(test_db)

    res = asyncio.run(run_turn(
        "cancel my reminder",
        _PlanClient('{"action":{"name":"cancel_reminder","params":{}}}'),
        request_id="test-req-8", prefs=prefs, audit=audit,
    ))
    assert res.spoken == "I'm switched off."

    # Verify against SQLite: reminder is STILL active
    active = asyncio.run(reminders.alist_active())
    assert len(active) == 1
    assert active[0].id == r.id

    audit_rows = test_db.query("SELECT tool_id, outcome, policy_decision FROM action_audit WHERE request_id = 'test-req-8'")
    assert len(audit_rows) == 1
    assert audit_rows[0]["tool_id"] == "cancel_reminder"
    assert audit_rows[0]["outcome"] == "disabled"


def test_panic_gate_9_create_note(test_db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "is_disabled", lambda: True)
    prefs = PrefStore(test_db)
    audit = AuditLog(test_db)
    notes = NoteStore(test_db)

    res = asyncio.run(run_turn(
        "note that I should buy milk",
        _PlanClient('{"action":{"name":"create_note","params":{"content":"buy milk"}}}'),
        request_id="test-req-9", prefs=prefs, audit=audit,
    ))
    assert res.spoken == "I'm switched off."

    # Verify against SQLite: NO note saved
    saved = asyncio.run(notes.alist_notes())
    assert len(saved) == 0

    audit_rows = test_db.query("SELECT tool_id, outcome, policy_decision FROM action_audit WHERE request_id = 'test-req-9'")
    assert len(audit_rows) == 1
    assert audit_rows[0]["tool_id"] == "create_note"
    assert audit_rows[0]["outcome"] == "disabled"


def test_panic_gate_10_desktop_notification(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "is_disabled", lambda: True)
    # Assert notify returns False and does not spawn subprocess
    assert notify("Friday", "Test notification") is False
