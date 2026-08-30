"""D1 (CRITICAL) — a SPOKEN "yes" must confirm. ADR-075, FR-85.

`is_affirmation` compared `text.strip().casefold()` against a frozenset of bare
tokens. Whisper punctuates every utterance, so `"Yes."` was not an affirmation
and ADR-069's fail-safe turned every spoken confirm into a decline. Proven from
`action_audit` on 2026-08-29: bare `Yes` -> allowed/ok, `Yes.` / `Yes!` ->
declined, six times, across clipboard_read, clipboard_set, system_wifi{off} and
hypr_window{close}. Every confirm-gated capability had been unreachable by
voice for the whole of Phase 2.

A grep for a punctuated affirmation across `tests/` returned 0 hits before this
file existed — which is exactly why five review passes and a typed pass all
missed it. **Every string here is realistic STT output.**
"""

import asyncio

import pytest

from friday import daemon as daemon_mod
from friday.audio.stt import Transcript
from friday.daemon import Daemon
from friday.store.audit import AuditLog
from friday.store.db import Database
from friday.turn import (
    PendingAction,
    TurnResult,
    is_affirmation,
    is_decline,
    resolve_pending,
)


class FakeTranscriber:
    def __init__(self, text="open my browser"):
        self._t = Transcript(text, over_limit=False)

    def run(self, pcm):
        return self._t


class FakeSpeaker:
    def __init__(self):
        self.said = []

    def say(self, text, on_play=None):
        self.said.append(text)
        if on_play is not None:
            on_play()
        return True

    def stop(self):
        pass


class FakeRecorder:
    def reset(self):
        pass

    def collect(self):
        return b""

    def open(self):
        return True

    def ensure_open(self):
        return True

    def close(self):
        pass


def _daemon(**kw):
    kw.setdefault("client", object())
    kw.setdefault("recorder", FakeRecorder())
    kw.setdefault("transcriber", FakeTranscriber())
    kw.setdefault("speaker", FakeSpeaker())
    return Daemon(**kw)


def _plan(monkeypatch, result):
    async def fake_run_turn(*a, **k):
        return result

    monkeypatch.setattr(daemon_mod, "run_turn", fake_run_turn)


# --- (a) normalise: this is the whole of D1 --------------------------------


@pytest.mark.parametrize(
    "heard", ["Yes.", "Yes!", "Yeah.", "Yep.", "Sure.", "Okay,", "OK.", " Yes. "]
)
def test_punctuated_yes_is_an_affirmation(heard: str) -> None:
    assert is_affirmation(heard), f"Whisper writes {heard!r}; that is a yes"


# --- (b) widen: the user was shown the tradeoff and chose to widen ---------


@pytest.mark.parametrize(
    "heard", ["Go ahead.", "Do it.", "Please do.", "Confirm.", "Yeah, do it."]
)
def test_widened_spoken_forms_affirm(heard: str) -> None:
    assert is_affirmation(heard)


@pytest.mark.parametrize("heard", ["No.", "Nope.", "Cancel.", "Never mind.", "Don't."])
def test_punctuated_no_is_a_decline_and_not_an_affirmation(heard: str) -> None:
    assert is_decline(heard) and not is_affirmation(heard)


def test_a_command_is_neither(heard: str = "Open a terminal.") -> None:
    assert not is_affirmation(heard) and not is_decline(heard)


# --- resolve_pending: the three outcomes -----------------------------------


def _audit(tmp_path):
    return AuditLog(Database(tmp_path / "memory.db"))


def _pending():
    return PendingAction("system_wifi", {"state": "off"}, "turn off Wi-Fi")


def test_spoken_yes_dispatches_and_audits_allowed(tmp_path, monkeypatch) -> None:
    ran = []

    async def fake_execute(spec, params, request_id, dry_run=False):
        from friday.errors import Outcome
        from friday.tools.executor import ToolResult

        ran.append(params)
        return ToolResult(Outcome.OK, "Wi-Fi")

    from friday.tools import executor as ex

    monkeypatch.setattr(ex, "execute", fake_execute)
    audit = _audit(tmp_path)

    spoken = asyncio.run(
        resolve_pending(
            _pending(), "Yes.", prefs=None, audit=audit, request_id="r1"
        )
    )
    assert ran == [{"state": "off"}], "a spoken yes must actually dispatch"
    assert spoken
    rows = audit._db.query("SELECT policy_decision, outcome FROM action_audit")
    assert rows[0]["policy_decision"] == "allowed" and rows[0]["outcome"] == "ok"


def test_spoken_no_declines_and_never_dispatches(tmp_path, monkeypatch) -> None:
    ran = []

    async def fake_execute(spec, params, request_id, dry_run=False):
        ran.append(params)

    from friday.tools import executor as ex

    monkeypatch.setattr(ex, "execute", fake_execute)
    audit = _audit(tmp_path)

    spoken = asyncio.run(
        resolve_pending(_pending(), "No.", prefs=None, audit=audit, request_id="r2")
    )
    assert ran == [] and spoken is not None
    assert audit._db.query("SELECT outcome FROM action_audit")[0]["outcome"] == "declined"


def test_a_non_answer_drops_the_pending_and_asks_to_be_rerouted(tmp_path) -> None:
    """ADR-075(c): neither yes nor no -> the pending is cancelled and audited,
    and `None` tells the caller to run the text as a fresh command."""
    audit = _audit(tmp_path)
    out = asyncio.run(
        resolve_pending(
            _pending(), "Open a terminal.", prefs=None, audit=audit, request_id="r3"
        )
    )
    assert out is None
    assert audit._db.query("SELECT outcome FROM action_audit")[0]["outcome"] == "declined"


# --- the daemon end of (c) -------------------------------------------------


def test_non_answer_during_a_confirm_runs_as_a_command(monkeypatch) -> None:
    """Live 2026-08-29: "Open a terminal" was eaten by a live preference confirm
    and the terminal never opened. It must now cancel the pending and RUN."""
    d = _daemon()
    d._pending = _pending()

    seen = []

    async def fake_run_turn(text, *a, **k):
        seen.append(text)
        return TurnResult("open_app", {"app": "terminal"}, "Launching foot.", True)

    monkeypatch.setattr(daemon_mod, "run_turn", fake_run_turn)
    d._transcriber = FakeTranscriber(text="Open a terminal.")

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task

    asyncio.run(go())
    assert seen == ["Open a terminal."], "the non-answer must reach the planner"
    assert d._speaker.said == ["Launching foot."]
    assert d._pending is None


def test_spoken_yes_during_a_confirm_does_not_reach_the_planner(monkeypatch) -> None:
    """The other side: a real answer is still answered, never re-planned."""
    d = _daemon()
    d._pending = _pending()

    seen = []

    async def fake_run_turn(text, *a, **k):
        seen.append(text)
        return TurnResult("none", {}, "", False)

    monkeypatch.setattr(daemon_mod, "run_turn", fake_run_turn)

    async def fake_resolve(pending, answer, **k):
        return "Wi-Fi off."

    monkeypatch.setattr(daemon_mod, "resolve_pending", fake_resolve)
    d._transcriber = FakeTranscriber(text="Yes.")

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task

    asyncio.run(go())
    assert seen == [] and d._speaker.said == ["Wi-Fi off."]


# --- D25: a leading yes with a trailing clause (ADR-091) --------------------
#
# D1/ADR-075 fixed punctuation ("Yes." was not an affirmation). It did not fix
# the other half of how people actually answer "Are you sure?": they lead with
# the word and keep talking. Observed live 2026-08-30 — "Yes, I am sure" to a
# `system_wifi{off}` confirm was read as a non-answer, ADR-075c cancelled the
# pending, and the audit recorded `declined` with Wi-Fi still enabled. It was
# the last untested row in the manifest and it failed for a NEW reason.


def test_leading_yes_with_a_trailing_clause_is_an_affirmation():
    from friday.turn import is_affirmation

    # The exact utterance from the live session.
    assert is_affirmation("Yes, I am sure")
    assert is_affirmation("Yes, I am sure!")
    assert is_affirmation("yeah go ahead then")
    assert is_affirmation("ok do that for me")


def test_a_negative_anywhere_vetoes_a_leading_yes():
    """This gate approves destructive actions. Ambiguity must resolve to
    not-acting, never to acting."""
    from friday.turn import is_affirmation

    assert not is_affirmation("yes but not now")
    assert not is_affirmation("yeah actually cancel that")
    assert not is_affirmation("yes don't do it")


def test_head_matching_does_not_over_match():
    from friday.turn import is_affirmation, is_decline

    assert not is_affirmation("yesterday was fine")
    assert not is_affirmation("what's in my clipboard")
    # A fresh command must stay a non-answer so ADR-075c re-routes it.
    assert not is_affirmation("open my browser")
    assert not is_decline("open my browser")


def test_leading_no_with_a_trailing_clause_is_a_decline():
    from friday.turn import is_decline

    assert is_decline("No, cancel that")
    assert is_decline("nope not that one")
