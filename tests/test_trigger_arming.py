"""Trigger-arm discipline across the audio thread / event loop seam
(audit H5, M-A2, M-A3).

Three triggers can open a capture — wake, barge-in, PTT — and they arrive on
two different threads. Nothing in the suite ever raced two of them, which is
why the listener could end up armed for a capture that was never accepted.
"""

import asyncio

import numpy as np
import pytest

from friday import daemon as daemon_mod
from friday.audio.aec import NullAec
from friday.audio.state import State
from friday.audio.stt import Transcript
from friday.audio.wake import FarEndRef, WakeCallbacks, WakeListener
from friday.daemon import Daemon
from friday.turn import TurnResult


# --- fakes -----------------------------------------------------------------


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


class RecordingListener:
    """Counts arm calls; that is all the daemon-side tests need."""

    def __init__(self):
        self.armed = 0

    def arm_end_of_speech(self):
        self.armed += 1

    def start(self):
        return True

    def stop(self):
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


def _frame(n=320):
    return np.zeros(n, dtype=np.float32)


class ScriptedDetector:
    def __init__(self, scores):
        self._scores = list(scores)

    def score(self, frame):
        return self._scores.pop(0) if self._scores else 0.0


class AlwaysSpeechVad:
    def is_speech(self, frame):
        return True


# --- H5: arming follows acceptance, not detection --------------------------


def test_wake_detection_alone_does_not_arm_the_listener():
    """H5: `_on_frame` used to set `_awaiting_end` on the AUDIO thread, before
    the loop had decided whether to accept the trigger at all."""
    fired = []
    wl = WakeListener(
        detector=ScriptedDetector([0.9]),
        vad=AlwaysSpeechVad(),
        aec=NullAec(),
        callbacks=WakeCallbacks(
            on_wake=lambda: fired.append("wake"),
            on_speech_end=lambda: fired.append("end"),
            on_barge=lambda: None,
        ),
        far_ref=FarEndRef(),
        threshold=0.5,
        frame_len=320,
        refractory_s=0.0,
        is_idle=lambda: True,
        is_speaking=lambda: False,
        schedule=lambda cb: cb(),
    )

    wl._on_frame(_frame())

    assert fired == ["wake"], "the wake still has to fire"
    assert wl._awaiting_end is False, "detection must not arm; acceptance does"


def test_accepted_wake_capture_is_armed_by_the_daemon():
    """The other half: acceptance DOES arm, or a hands-free capture could only
    ever end at the 15 s cap (ADR-062)."""
    wl = RecordingListener()
    d = _daemon(wake_listener=wl)

    async def go():
        await d.on_wake()
        assert d.state.state is State.CAPTURING

    asyncio.run(go())
    assert wl.armed == 1


def test_rejected_wake_never_arms():
    """A wake rejected as busy (FR-5) must leave the listener untouched —
    otherwise VAD end-of-speech terminates the PTT capture that is actually
    running, contradicting ADR-044."""
    wl = RecordingListener()
    d = _daemon(wake_listener=wl)

    async def go():
        await d.on_ptt("press")  # a PTT capture owns the machine
        assert wl.armed == 0
        await d.on_wake()  # rejected: busy

    asyncio.run(go())
    assert d.rejected == 1
    assert wl.armed == 0, "a rejected wake armed the listener anyway"


@pytest.mark.parametrize("order", ["wake_first", "ptt_first"])
def test_interleaved_wake_and_ptt_leave_no_stuck_state(monkeypatch, order):
    """Race both trigger sources, both orders: exactly one capture, exactly one
    arm decision, and no orphaned cap timer."""
    _plan(monkeypatch, TurnResult("chat", {}, "Hi.", False))
    wl = RecordingListener()
    d = _daemon(wake_listener=wl)

    async def go():
        if order == "wake_first":
            await d.on_wake()
            await d.on_ptt("press")
        else:
            await d.on_ptt("press")
            await d.on_wake()

        assert d.state.state is State.CAPTURING
        assert d.rejected == 1, "the second trigger must be rejected, not queued"
        # Only the ACCEPTED source decides arming: wake arms, PTT does not.
        assert wl.armed == (1 if order == "wake_first" else 0)

        cap = d._cap_timer
        assert cap is not None
        await d.on_ptt("release")
        await d._turn_task
        assert cap.cancelled(), "the cap timer outlived its capture"
        assert d._cap_timer is None
        assert d.state.state is State.IDLE

    asyncio.run(go())


# --- M-A2: the cap timer must not leak on re-arm ---------------------------


def test_rearming_the_cap_cancels_the_previous_handle(monkeypatch):
    """M-A2: `_arm_capture_cap` overwrote `_cap_timer` without cancelling it, so
    the orphan fired mid-NEXT-capture and ended it early."""
    _plan(monkeypatch, TurnResult("chat", {}, "Hi.", False))
    d = _daemon()

    async def go():
        await d.on_ptt("press")
        first = d._cap_timer
        assert first is not None

        d._arm_capture_cap()  # re-arm (barge-in into a fresh capture does this)
        second = d._cap_timer

        assert second is not first
        assert first.cancelled(), "the old cap timer was orphaned, not cancelled"

    asyncio.run(go())


def test_barge_in_into_a_live_capture_leaves_one_cap_timer(monkeypatch):
    """The realistic route to a re-arm: speak, barge in, capture again."""
    _plan(monkeypatch, TurnResult("chat", {}, "Hi.", False))
    d = _daemon()

    async def go():
        await d.on_ptt("press")
        first = d._cap_timer
        d.state._state = State.SPEAKING  # arrange: mid-playback
        await d.on_barge()
        assert d.state.state is State.CAPTURING
        assert d._cap_timer is not first
        assert first.cancelled()

    asyncio.run(go())


# --- M-A3: no VAD means no pretending ---------------------------------------


def _listener_without_vad():
    return WakeListener(
        detector=ScriptedDetector([]),
        vad=None,
        aec=NullAec(),
        callbacks=WakeCallbacks(
            on_wake=lambda: None, on_speech_end=lambda: None, on_barge=lambda: None,
        ),
        far_ref=FarEndRef(),
        threshold=0.5,
        frame_len=320,
        refractory_s=0.0,
        is_idle=lambda: True,
        is_speaking=lambda: False,
        schedule=lambda cb: cb(),
    )


def test_arming_without_a_vad_is_refused_and_logged_once(caplog):
    """M-A3: with no VAD an 'armed' capture has neither end-of-speech nor the
    ADR-066 bail-out, so it runs the full 15 s cap with Friday deaf — the
    pre-ADR-066 behaviour, silently back."""
    wl = _listener_without_vad()

    with caplog.at_level("WARNING", logger="friday.audio.wake"):
        wl.arm_end_of_speech()
        wl.arm_end_of_speech()
        wl.arm_end_of_speech()

    assert wl._awaiting_end is False, "armed with nothing able to disarm it"
    warnings = [r for r in caplog.records if "no VAD" in r.getMessage()]
    assert len(warnings) == 1, "warn once, not once per capture"
    assert "PTT" in warnings[0].getMessage(), "say what still works"
