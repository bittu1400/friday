"""Memory in the turn loop: confirm-first remember, soft forget, digest
injection (ADR-035/036/037)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from friday.store.db import Database
from friday.store.prefs import PrefStore, resolve
from friday.turn import confirm_preference, is_affirmation, run_turn


@dataclass
class RecordingClient:
    reply: str
    seen_system: str = field(default="", compare=False)

    def complete(self, *, system: str, user: str, grammar: str) -> str:
        self.seen_system = system
        return self.reply

    def health(self) -> bool:
        return True


def _prefs(tmp_path) -> PrefStore:
    return PrefStore(Database(tmp_path / "memory.db"))


def _run(reply: str, prefs: PrefStore, client=None):
    c = client or RecordingClient(reply)
    return asyncio.run(
        run_turn("x", c, request_id="t", dry_run=True, prefs=prefs)
    )


# -- remember: confirm-first, no write until confirmed ----------------------


def test_remember_returns_pending_without_writing(tmp_path) -> None:
    prefs = _prefs(tmp_path)
    r = _run(
        '{"action":{"name":"remember_preference",'
        '"params":{"key":"web browser","value":"brave"}}}',
        prefs,
    )
    assert r.plan_name == "remember_preference" and not r.dispatched
    assert r.pending is not None
    assert r.pending.key == "browser"  # aliased + slugged
    assert "Remember that your browser is brave" in r.spoken
    assert prefs.active() == {}  # NOTHING written yet (ADR-037)


def test_confirm_writes_the_preference(tmp_path) -> None:
    prefs = _prefs(tmp_path)
    pending = resolve("web browser", "brave")
    spoken = asyncio.run(
        confirm_preference(pending, prefs, None, request_id="t")
    )
    assert prefs.active() == {"browser": "brave"}
    assert "remember" in spoken.lower()


def test_is_affirmation() -> None:
    assert is_affirmation("yes") and is_affirmation("  OK ")
    assert not is_affirmation("nah") and not is_affirmation("")


# -- forget: soft-expire immediately ---------------------------------------


def test_forget_soft_expires(tmp_path) -> None:
    prefs = _prefs(tmp_path)
    prefs.put(resolve("name", "Subham"))
    r = _run(
        '{"action":{"name":"forget_preference","params":{"key":"my name"}}}',
        prefs,
    )
    assert r.plan_name == "forget_preference" and r.dispatched
    assert "forgotten" in r.spoken
    assert prefs.active() == {}


def test_forget_unknown(tmp_path) -> None:
    prefs = _prefs(tmp_path)
    r = _run(
        '{"action":{"name":"forget_preference","params":{"key":"nonesuch"}}}',
        prefs,
    )
    assert not r.dispatched
    assert "don't have a preference" in r.spoken


# -- digest is injected as data --------------------------------------------


def test_digest_reaches_the_prompt(tmp_path) -> None:
    prefs = _prefs(tmp_path)
    prefs.put(resolve("browser", "brave"))
    client = RecordingClient('{"action":{"name":"none","params":{}}}')
    _run("", prefs, client=client)
    assert "<preferences>" in client.seen_system
    assert "browser=brave" in client.seen_system


def test_no_prefs_no_block(tmp_path) -> None:
    prefs = _prefs(tmp_path)
    client = RecordingClient('{"action":{"name":"none","params":{}}}')
    _run("", prefs, client=client)
    assert "<preferences>" not in client.seen_system
