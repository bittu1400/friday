"""ADR-113 / OQ-64: a capture that heard nothing must cost only the wait.

ADR-066 gave up early on a capture nobody speaks into, but handed it to
`on_speech_end` — the ordinary finish path. That runs the whole turn: Whisper
on silence for a flat ~600 ms whatever the audio length (F26), an empty
transcript, then a silent return to IDLE. FR-5 means Friday is deaf for all of
it, so a false wake cost the timeout PLUS a turn.

That surcharge is what made a longer timeout look expensive. Removing it is
what pays for VAD_NO_SPEECH_TIMEOUT_S going 3.0 -> 5.0 s, which is the owner's
actual complaint (OQ-64: "up to 2 second pause at max, anymore and then no
response").
"""

import asyncio

import numpy as np
import pytest

from friday import config
from friday.audio.aec import NullAec
from friday.audio.state import State
from friday.audio.wake import FarEndRef, WakeCallbacks, WakeListener
from friday.daemon import Daemon


def _frame(n=320):
    return np.zeros(n, dtype=np.float32)


class _Vad:
    def __init__(self, voiced: bool):
        self._v = voiced

    def is_speech(self, frame) -> bool:
        return self._v


class _Detector:
    def score(self, frame) -> float:
        return 0.0


def _listener(*, voiced: bool, calls: WakeCallbacks) -> WakeListener:
    return WakeListener(
        detector=_Detector(),
        vad=_Vad(voiced),
        aec=NullAec(),
        callbacks=calls,
        far_ref=FarEndRef(),
        threshold=0.5,
        frame_len=320,
        is_idle=lambda: False,       # a capture is running
        is_speaking=lambda: False,
    )


def _calls(events: list) -> WakeCallbacks:
    return WakeCallbacks(
        on_wake=lambda: events.append("wake"),
        on_speech_end=lambda: events.append("speech_end"),
        on_barge=lambda: events.append("barge"),
        on_no_speech=lambda: events.append("no_speech"),
    )


def test_silent_capture_routes_to_on_no_speech_not_on_speech_end():
    """The whole point: silence must NOT enter the transcribe path."""
    events: list[str] = []
    wl = _listener(voiced=False, calls=_calls(events))
    wl._arm()

    quiet = int(config.VAD_NO_SPEECH_TIMEOUT_S * 1000 / wl.frame_ms)
    for _ in range(quiet - 1):
        wl._on_frame(_frame())
    assert events == [], "must not give up before the timeout"

    wl._on_frame(_frame())
    assert events == ["no_speech"]
    assert "speech_end" not in events, (
        "a capture with no speech must not reach the turn: on_speech_end runs "
        "Whisper on silence for a flat ~600 ms (F26) to produce an empty string"
    )


def test_capture_with_speech_still_ends_normally():
    """The bail-out must never divert someone who is actually talking."""
    events: list[str] = []
    wl = _listener(voiced=True, calls=_calls(events))
    wl._arm()
    for _ in range(int(config.VAD_NO_SPEECH_TIMEOUT_S * 1000 / wl.frame_ms) + 50):
        wl._on_frame(_frame())
    assert events == [], "continuous speech must not trigger the bail-out"


class _Recorder:
    def __init__(self):
        self.resets = 0

    def reset(self):
        self.resets += 1

    def collect(self):
        raise AssertionError(
            "on_no_speech must not collect audio -- collecting means a turn ran"
        )

    def open(self):
        return True

    def ensure_open(self):
        return True

    def close(self):
        pass


def test_daemon_on_no_speech_returns_to_idle_without_a_turn():
    """CAPTURING -> IDLE with the buffer dropped and no turn task created."""
    rec = _Recorder()
    d = Daemon(client=object(), recorder=rec, transcriber=None, speaker=None)

    async def go():
        assert d.state.begin_capture()
        assert d.state.state is State.CAPTURING
        await d.on_no_speech()

    asyncio.run(go())

    assert d.state.state is State.IDLE, "wake must be live again immediately"
    assert rec.resets == 1, "the captured silence must be discarded"
    assert d._turn_task is None, "no turn may be started for a silent capture"


def test_no_speech_from_a_non_capturing_state_is_a_no_op():
    """The callback crosses the audio-thread seam, so it can arrive late."""
    rec = _Recorder()
    d = Daemon(client=object(), recorder=rec, transcriber=None, speaker=None)

    asyncio.run(d.on_no_speech())

    assert d.state.state is State.IDLE
    assert rec.resets == 0


def test_timeout_is_the_owner_s_answer_to_oq_64():
    """OQ-64 raised 3.0 -> 5.0. Guard both ends: long enough to be the fix,
    and still far below the FR-4 cap it exists to avoid."""
    assert config.VAD_NO_SPEECH_TIMEOUT_S >= 5.0
    assert config.VAD_NO_SPEECH_TIMEOUT_S < config.MAX_CAPTURE_S
