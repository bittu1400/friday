"""The pending-confirm handshake under degraded and interrupted conditions
(audit H2, H3, M-P1 — fixed together as ADR-069).

Every defect here lives on a path the 328-test suite never drove: the TTS
raising, a barge-in landing on the confirm question, and the 30 s window
expiring while the user is mid-answer. The happy path was always green.
"""

import asyncio
import threading

import pytest

from friday import daemon as daemon_mod
from friday.audio.state import State
from friday.audio.stt import Transcript
from friday.daemon import Daemon
from friday.turn import PendingAction, TurnResult


class FakeTranscriber:
    def __init__(self, text="open my browser"):
        self._t = Transcript(text, over_limit=False)

    def run(self, pcm):
        return self._t


class FakeSpeaker:
    """Mirrors the real Speaker's contract: say() returns True when it played
    to the end, False when stop() cut it short (tts.py:105-180)."""

    def __init__(self, block=False):
        self.said = []
        self.stopped = 0
        self._block = block
        self._gate = threading.Event()

    def say(self, text, on_play=None):
        self.said.append(text)
        if on_play is not None:
            on_play()
        if self._block:
            self._gate.wait(timeout=2.0)
            return False  # cut short
        return True

    def stop(self):
        self.stopped += 1
        self._gate.set()


class RaisingSpeaker(FakeSpeaker):
    """An audio device that has gone away mid-session."""

    def say(self, text, on_play=None):
        self.said.append(text)
        raise RuntimeError("audio device gone")


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


def _wifi_off_question():
    return TurnResult(
        "system_wifi", {"state": "off"}, "Are you sure you want to turn off Wi-Fi?",
        False, pending=PendingAction("system_wifi", {"state": "off"}, "turn off Wi-Fi"),
    )


@pytest.fixture
def spy_executor(monkeypatch):
    ran: list[dict] = []

    async def fake_execute(spec, params, request_id, dry_run=False):
        from friday.errors import Outcome
        from friday.tools.executor import ToolResult

        ran.append(params)
        return ToolResult(Outcome.OK, "Wi-Fi")

    from friday.tools import executor as ex

    monkeypatch.setattr(ex, "execute", fake_execute)
    return ran


# --- H2: a question nobody heard must not arm a confirm --------------------


def test_failed_question_tts_does_not_arm_the_confirm(monkeypatch, spy_executor):
    """H2: `_pending` was assigned BEFORE the question was spoken. When
    `speaker.say` raised, `_pending` stayed set with NO confirm timer armed, so
    an unrelated "yeah" minutes later dispatched a held `system_wifi{off}` the
    user never heard proposed."""
    _plan(monkeypatch, _wifi_off_question())
    d = _daemon(speaker=RaisingSpeaker())

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task

        assert d._pending is None, "an undelivered question must not arm a confirm"
        assert d._confirm_timer is None, "and must not leave an unarmed window"
        assert d.state.state is State.IDLE

        # A later affirmation is an ordinary utterance, not an answer.
        d._speaker = FakeSpeaker()
        _plan(monkeypatch, TurnResult("chat", {}, "Sure thing.", False))
        d._transcriber = FakeTranscriber(text="yeah")
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task

    asyncio.run(go())
    assert spy_executor == [], "no action may dispatch from an unheard question"


def test_failed_speech_does_not_strand_the_fsm(monkeypatch):
    """A raising speaker must not blow up the error handler that reports it —
    that would leave the FSM in ERROR and reject every later trigger."""
    _plan(monkeypatch, TurnResult("open_app", {"app": "browser"}, "Opened Brave.", True))
    d = _daemon(speaker=RaisingSpeaker())

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task
        assert d.state.state is State.IDLE
        # The daemon still accepts work afterwards.
        await d.on_ptt("press")
        assert d.state.state is State.CAPTURING

    asyncio.run(go())


# --- H3: barge-in during the question, and interrupted speech --------------


async def _reach_speaking(d, speaker):
    for _ in range(200):
        if d.state.state is State.SPEAKING and speaker.said:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("never reached SPEAKING")


def test_barge_during_question_leaves_no_pending(monkeypatch, spy_executor):
    """H3: barging over the confirm question used to leave `_pending` armed with
    a 30 s timer, so the user's real command was read as the yes/no answer,
    cancelled with "Okay, cancelled." and never run."""
    _plan(monkeypatch, _wifi_off_question())
    speaker = FakeSpeaker(block=True)
    d = _daemon(speaker=speaker)

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await _reach_speaking(d, speaker)

        await d.on_ptt("press")  # barge-in over the question
        assert d.state.state is State.CAPTURING
        await d._turn_task  # the superseded turn unwinds

        assert d._pending is None, "a talked-over question is not a question"
        assert d._confirm_timer is None

        # The barged utterance is a fresh COMMAND, not a yes/no answer.
        d._speaker = FakeSpeaker()
        _plan(monkeypatch, TurnResult("open_app", {"app": "browser"}, "Opened Brave.", True))
        d._transcriber = FakeTranscriber(text="open my browser")
        await d.on_ptt("release")
        await d._turn_task
        assert "Opened Brave." in d._speaker.said

    asyncio.run(go())
    assert spy_executor == [], "the abandoned wifi-off must never dispatch"


def test_interrupted_reply_is_not_recorded_as_history(monkeypatch):
    """H3 (second half): a barged reply was appended to `Dialogue` as if fully
    delivered. History is what ADR-065 resolves anaphora against, so Friday
    could later resolve "open it" against a sentence cut off before its noun."""
    _plan(monkeypatch, TurnResult("chat", {}, "The nearest cafe is Blue Tokai.", False))
    speaker = FakeSpeaker(block=True)
    d = _daemon(speaker=speaker)

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await _reach_speaking(d, speaker)
        await d.on_ptt("press")  # barge-in mid-reply
        await d._turn_task

    asyncio.run(go())
    assert len(d._dialogue) == 0, "speech the user never received is not history"


def test_completed_reply_is_recorded_as_history(monkeypatch):
    """The other side of the same rule: an uninterrupted reply still counts."""
    _plan(monkeypatch, TurnResult("chat", {}, "Hello there!", False))
    d = _daemon()

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task

    asyncio.run(go())
    assert len(d._dialogue) == 1


def test_superseded_turn_does_not_clobber_the_new_speak_handle(monkeypatch):
    """H3 (third): after a barge-in, two turn tasks are briefly alive. The old
    one's teardown must not blank `_speak_task` — the newer turn owns it, and a
    cleared handle means the NEXT barge-in finds nothing to cancel."""
    _plan(monkeypatch, TurnResult("chat", {}, "First reply.", False))
    first = FakeSpeaker(block=True)
    d = _daemon(speaker=first)

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await _reach_speaking(d, first)
        old_turn = d._turn_task

        await d.on_ptt("press")  # barge-in: starts capture #2

        # Turn #2 speaks while turn #1 is still unwinding.
        second = FakeSpeaker(block=True)
        d._speaker = second
        _plan(monkeypatch, TurnResult("chat", {}, "Second reply.", False))
        await d.on_ptt("release")
        await _reach_speaking(d, second)

        await old_turn  # let the superseded turn finish its teardown
        assert d._speak_task is not None, "the old turn blanked the new handle"

        await d.on_ptt("press")  # barge #2 must still be able to cut playback
        assert second.stopped == 1
        await d._turn_task

    asyncio.run(go())
    assert d._dialogue.render().count("reply") == 0, "neither reply was delivered"


# --- M-P1: the 30 s window must never yank a live capture ------------------


def test_confirm_expiry_does_not_reset_a_live_capture(monkeypatch, spy_executor):
    """M-P1: `_expire_confirm` force-reset the FSM. Firing while the user was
    CAPTURING the yes/no slammed the mic gate shut, so the release found
    state != CAPTURING and the answer vanished with zero feedback."""
    _plan(monkeypatch, _wifi_off_question())
    d = _daemon()

    async def go():
        await d.on_ptt("press")
        await d.on_ptt("release")
        await d._turn_task
        assert d._pending is not None

        await d.on_ptt("press")  # user starts speaking the answer
        assert d.state.state is State.CAPTURING
        d._expire_confirm()  # 30 s elapses mid-answer

        assert d.state.state is State.CAPTURING, "the live capture was yanked"
        assert d._pending is None, "the window is closed; the answer is now a command"

        # The capture completes normally and is planned as a fresh utterance.
        _plan(monkeypatch, TurnResult("chat", {}, "Sure.", False))
        d._transcriber = FakeTranscriber(text="yes")
        await d.on_ptt("release")
        await d._turn_task
        assert d.state.state is State.IDLE

    asyncio.run(go())
    assert spy_executor == [], "an expired confirm must not dispatch on a late yes"
