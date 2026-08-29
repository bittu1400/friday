"""TUI-parity for the confirm-first handshake (audit C1, 2026-08-26).

The voice daemon was migrated to `PendingAction` when Phase 2 (G12) landed;
the TUI was not. Text mode therefore called `confirm_preference(pending, ...)`
on a `PendingAction`, which reads `pending.key` — AttributeError, swallowed by
the Textual worker. Confirming "Are you sure you want to overwrite your
clipboard?" in text mode did nothing at all, forever.

These tests drive the REAL app through Textual's headless harness (`run_test`),
not a stand-in for it, because the whole defect class here is "the test drove a
path the user never takes".
"""

import asyncio

import pytest
from textual.widgets import Input

import friday.ui.tui as tui_mod
from friday.errors import Outcome
from friday.store.prefs import PendingPreference
from friday.tools import executor as ex
from friday.tools.executor import ToolResult
from friday.turn import PendingAction, TurnResult
from friday.ui.tui import FridayTUI


class _Client:
    """Stands in for LlamaClient; the TUI only calls health() at mount."""

    def health(self) -> bool:
        return True


def _pending_turn(monkeypatch, result: TurnResult) -> None:
    async def fake_run_turn(*a, **k):
        return result

    monkeypatch.setattr(tui_mod, "run_turn", fake_run_turn)


def _drive(app: FridayTUI, *lines: str) -> str:
    """Submit each line to the real app, let its workers finish, and return
    everything the app printed (read INSIDE the harness — the widget tree is
    torn down when `run_test` exits)."""
    from textual.widgets import RichLog

    async def go() -> str:
        async with app.run_test() as pilot:
            inp = app.query_one(Input)
            for line in lines:
                app.on_input_submitted(Input.Submitted(inp, line))
                await app.workers.wait_for_complete()
            await pilot.pause()
            rl = app.query_one("#log", RichLog)
            return "\n".join(seg.text for line in rl.lines for seg in line._segments)

    return asyncio.run(go())


@pytest.fixture
def spy_executor(monkeypatch):
    ran: list[dict] = []

    async def fake_execute(spec, params, request_id, dry_run=False):
        ran.append(params)
        return ToolResult(Outcome.OK, "Brave")

    monkeypatch.setattr(ex, "execute", fake_execute)
    return ran


def test_tui_confirmed_pending_action_executes(monkeypatch, spy_executor):
    """C1: 'yes' to a held action must actually dispatch it in text mode."""
    pending = PendingAction("open_app", {"app": "browser"}, "Brave")
    _pending_turn(monkeypatch, TurnResult(
        "open_app", {"app": "browser"}, "Did you want me to open Brave?",
        False, pending=pending,
    ))
    app = FridayTUI(_Client(), dry_run=False)

    out = _drive(app, "open it", "yes")

    assert spy_executor == [{"app": "browser"}]
    assert app._pending is None
    assert "Launching Brave." in out  # ADR-073


def test_tui_declined_pending_action_does_not_execute(monkeypatch, spy_executor):
    """Fail safe: anything but an affirmation cancels and dispatches nothing."""
    pending = PendingAction("open_app", {"app": "browser"}, "Brave")
    _pending_turn(monkeypatch, TurnResult(
        "open_app", {"app": "browser"}, "Did you want me to open Brave?",
        False, pending=pending,
    ))
    app = FridayTUI(_Client(), dry_run=False)

    out = _drive(app, "open it", "no")

    assert spy_executor == []
    assert app._pending is None
    assert "cancelled" in out.lower()


def test_tui_confirmed_clipboard_set_writes(monkeypatch):
    """clipboard_set has no registry entry — the shared resolver must take the
    wl-copy branch in text mode exactly as it does by voice."""
    import friday.tools.clipboard as clip

    calls: list[str] = []
    monkeypatch.setattr(clip, "set_clipboard", lambda text, **kw: calls.append(text) or True)

    pending = PendingAction("clipboard_set", {"text": "hello world"}, "overwrite clipboard")
    _pending_turn(monkeypatch, TurnResult(
        "clipboard_set", {"text": "hello world"},
        "Are you sure you want to overwrite your clipboard?", False, pending=pending,
    ))
    app = FridayTUI(_Client(), dry_run=False)

    out = _drive(app, "copy hello world", "yes")

    assert calls == ["hello world"]
    assert "Copied to your clipboard." in out


def test_tui_preference_confirm_still_writes(monkeypatch):
    """Regression guard: fixing the action path must not break the G4 path."""
    written: list[str] = []

    async def fake_confirm(p, prefs, audit, *, request_id):
        written.append(p.key)
        return "Okay, I'll remember that your name is Subham."

    # The resolver lives in turn.py now; patch it where it is looked up.
    monkeypatch.setattr(tui_mod, "run_turn", None, raising=False)
    import friday.turn as turn_mod

    monkeypatch.setattr(turn_mod, "confirm_preference", fake_confirm)

    pending = PendingPreference(key="name", value="Subham")
    _pending_turn(monkeypatch, TurnResult(
        "remember_preference", {}, "Remember that your name is Subham? (yes/no)",
        False, pending=pending,
    ))
    app = FridayTUI(_Client(), dry_run=False)

    out = _drive(app, "remember my name is Subham", "yes")

    assert written == ["name"]
    assert "I'll remember that" in out
