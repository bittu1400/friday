"""`clipboard_read` is a confirmed action (ADR-068a, closing OQ-34).

Reading the clipboard puts its contents into the ROOM as sound. A copied
password or 2FA code must not be voiced because the planner matched a phrase,
so `clipboard_read` joins clipboard_set / wifi-off / window-close behind the
confirm — and the selection is not even fetched until the user says yes.
"""

import asyncio
from dataclasses import dataclass

import friday.tools.clipboard as clip
from friday.turn import PendingAction, resolve_pending, run_turn

_SECRET = "hunter2-correct-horse"
_PLAN = '{"action":{"name":"clipboard_read","params":{}}}'


@dataclass
class StubClient:
    reply: str

    def complete(self, *, system: str, user: str, grammar: str) -> str:
        return self.reply

    def health(self) -> bool:
        return True


def _read_spy(monkeypatch):
    reads: list[int] = []

    def fake_read():
        reads.append(1)
        return _SECRET

    monkeypatch.setattr(clip, "read_clipboard", fake_read)
    return reads


def test_clipboard_read_asks_before_speaking_anything(monkeypatch):
    reads = _read_spy(monkeypatch)
    r = asyncio.run(run_turn("what's in my clipboard", StubClient(_PLAN), request_id="t"))

    assert r.plan_name == "clipboard_read"
    assert not r.dispatched
    assert isinstance(r.pending, PendingAction)
    assert r.pending.tool_id == "clipboard_read"
    assert _SECRET not in r.spoken, "the contents leaked into the question"
    assert reads == [], "the clipboard must not even be read before consent"


def test_declined_confirm_speaks_no_clipboard_characters(monkeypatch):
    reads = _read_spy(monkeypatch)
    pending = PendingAction("clipboard_read", {}, "read the clipboard aloud")

    spoken = asyncio.run(resolve_pending(
        pending, "no", prefs=None, audit=None, request_id="t",
    ))

    assert _SECRET not in spoken
    assert "clipboard" not in spoken.lower(), "a decline reveals nothing at all"
    assert reads == [], "a declined confirm must not fetch the selection"


def test_confirmed_confirm_reads_and_speaks(monkeypatch):
    reads = _read_spy(monkeypatch)
    pending = PendingAction("clipboard_read", {}, "read the clipboard aloud")

    spoken = asyncio.run(resolve_pending(
        pending, "yes", prefs=None, audit=None, request_id="t",
    ))

    assert spoken == f"Clipboard contains: {_SECRET}"
    assert reads == [1]


def test_confirmed_read_caps_and_collapses_whitespace(monkeypatch):
    monkeypatch.setattr(clip, "read_clipboard", lambda: "a\n\tb  c" + "x" * 200)
    pending = PendingAction("clipboard_read", {}, "read the clipboard aloud")

    spoken = asyncio.run(resolve_pending(
        pending, "yes", prefs=None, audit=None, request_id="t",
    ))

    body = spoken.removeprefix("Clipboard contains: ")
    assert len(body) == 100
    assert body.startswith("a b c")


def test_confirmed_read_reports_an_empty_or_missing_clipboard(monkeypatch):
    pending = PendingAction("clipboard_read", {}, "read the clipboard aloud")

    monkeypatch.setattr(clip, "read_clipboard", lambda: "   \n ")
    assert asyncio.run(resolve_pending(
        pending, "yes", prefs=None, audit=None, request_id="t",
    )) == "Your clipboard is empty."

    monkeypatch.setattr(clip, "read_clipboard", lambda: None)
    assert asyncio.run(resolve_pending(
        pending, "yes", prefs=None, audit=None, request_id="t",
    )) == "Clipboard unavailable."
