"""Daemon orchestration: PTT flow, one-turn-in-flight (FR-5), empty-transcript
silence (FR-12), barge-in (FR-7), and the confirm-first voice handshake.

No audio, no model: the transcriber and speaker are fakes, and `run_turn` is
monkeypatched so these tests exercise the daemon's own logic, not the turn
pipeline (which has its own tests)."""

import asyncio
import threading

import pytest

from friday import daemon as daemon_mod
from friday.audio.state import State
from friday.audio.stt import Transcript
from friday.daemon import Daemon
from friday.turn import TurnResult


class FakeTranscriber:
    def __init__(self, text="open my browser", over_limit=False):
        self._t = Transcript(text, over_limit=over_limit)

    def run(self, pcm):
        return self._t


class FakeSpeaker:
    def __init__(self, block=False):
        self.said = []
        self.stopped = 0
        self._block = block
        self._gate = threading.Event()

    def say(self, text):
        self.said.append(text)
        if self._block:
            self._gate.wait(timeout=2.0)
            return False  # cancelled
        return True

    def stop(self):
        self.stopped += 1
        self._gate.set()


class FakeRecorder:
    def __init__(self):
        self.resets = 0

    def reset(self):
        self.resets += 1

    def collect(self):
        return b""  # daemon passes it straight to the (fake) transcriber

    def open(self):
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


def test_happy_path_press_release_speaks_outcome(monkeypatch):
    _plan(monkeypatch, TurnResult("open_app", {"app": "browser"}, "Opened Brave.", True))
    d = _daemon()

    async def go():
        await d.on_ptt("press")
        assert d.state.state is State.CAPTURING
        await d.on_ptt("release")
        await d._turn_task  # let the turn finish

    asyncio.run(go())
    assert d._speaker.said == ["Opened Brave."]
    assert d.state.state is State.IDLE


def test_five_rapid_presses_one_turn_four_rejections(monkeypatch):
    """FR-5: 5 presses while busy -> 1 accepted + 4 rejected, never queued."""
    _plan(monkeypatch, TurnResult("none", {}, "(no action)", False))
    d = _daemon()

    async def go():
        for _ in range(5):
            await d.on_ptt("press")

    asyncio.run(go())
    assert d.state.state is State.CAPTURING  # still the one capture
    assert d.rejected == 4


def test_empty_transcript_is_silent_and_idle(monkeypatch):
    _plan(monkeypatch, TurnResult("open_app", {}, "should not be spoken", True))
    d = _daemon(transcriber=FakeTranscriber(text=""))

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task

    asyncio.run(go())
    assert d._speaker.said == []  # FR-12: nothing spoken
    assert d.state.state is State.IDLE


def test_over_limit_transcript_is_refused(monkeypatch):
    """FR-13: an over-limit transcript acts like empty -> silent IDLE."""
    _plan(monkeypatch, TurnResult("open_app", {}, "nope", True))
    d = _daemon(transcriber=FakeTranscriber(text="", over_limit=True))

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task

    asyncio.run(go())
    assert d._speaker.said == []
    assert d.state.state is State.IDLE


def test_barge_in_cancels_playback_and_recaptures(monkeypatch):
    """FR-7: PTT press during SPEAKING stops playback and goes to CAPTURING."""
    _plan(monkeypatch, TurnResult("open_app", {}, "A long spoken line.", True))
    speaker = FakeSpeaker(block=True)  # say() blocks until stop()
    d = _daemon(speaker=speaker)

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        # wait until the turn is in SPEAKING (say() is blocking in a thread)
        for _ in range(200):
            if d.state.state is State.SPEAKING and speaker.said:
                break
            await asyncio.sleep(0.01)
        assert d.state.state is State.SPEAKING
        await d.on_ptt("press")  # barge-in
        assert d.state.state is State.CAPTURING
        assert speaker.stopped == 1
        await d._turn_task  # the cancelled turn unwinds cleanly

    asyncio.run(go())


def test_confirm_handshake_yes_writes(monkeypatch):
    """Spoken pref -> question spoken; next 'yes' -> confirm_preference."""
    from friday.store.prefs import PendingPreference

    pending = PendingPreference(key="name", value="Subham")
    _plan(monkeypatch, TurnResult(
        "remember_preference", {}, "Remember your name is Subham?", False, pending=pending))

    confirmed = {}

    async def fake_confirm(p, prefs, audit, *, request_id):
        confirmed["key"] = p.key
        return "Okay, I'll remember that."
    monkeypatch.setattr(daemon_mod, "confirm_preference", fake_confirm)

    d = _daemon()

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task
        assert d._pending is pending  # awaiting the yes/no
        # answer "yes"
        d._transcriber = FakeTranscriber(text="yes")
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task

    asyncio.run(go())
    assert confirmed["key"] == "name"
    assert "Okay, I'll remember that." in d._speaker.said
    assert d.state.state is State.IDLE


def test_confirm_timer_not_orphaned_by_answer_press(monkeypatch):
    """BUG-3 regression: the 30 s confirm window uses its OWN timer handle, so
    pressing the key to speak the answer (which arms the 15 s capture cap) does
    not orphan it, and resolving the confirm cancels it — no stray timer is
    left to reset the FSM mid-future-turn."""
    from friday.store.prefs import PendingPreference

    pending = PendingPreference(key="name", value="Subham")
    _plan(monkeypatch, TurnResult(
        "remember_preference", {}, "Remember your name is Subham?", False, pending=pending))

    async def fake_confirm(p, prefs, audit, *, request_id):
        return "Okay."
    monkeypatch.setattr(daemon_mod, "confirm_preference", fake_confirm)

    d = _daemon()

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task
        # Confirm window open on its own handle, separate from the cap timer.
        confirm_timer = d._confirm_timer
        assert confirm_timer is not None
        assert confirm_timer is not d._cap_timer

        # Press to answer: arms the capture cap. The confirm timer must survive
        # unchanged (old bug overwrote the shared handle here).
        d._transcriber = FakeTranscriber(text="yes")
        await d.on_ptt("press")
        assert d._confirm_timer is confirm_timer  # not clobbered
        assert d._cap_timer is not None and d._cap_timer is not confirm_timer

        await d.on_ptt("release")
        await d._turn_task
        # Resolved: the confirm timer is cancelled, not left to fire later.
        assert d._confirm_timer is None
        assert confirm_timer.cancelled()
        assert d.state.state is State.IDLE

    asyncio.run(go())


def test_release_without_capture_is_ignored():
    d = _daemon()

    async def go():
        await d.on_ptt("release")  # no press first

    asyncio.run(go())
    assert d.state.state is State.IDLE
    assert d._turn_task is None
