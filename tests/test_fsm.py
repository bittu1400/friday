"""FSM: legal transitions, one-turn-in-flight (FR-5), the mic gate (FR-6),
and barge-in (FR-7)."""

import pytest

from friday.audio.state import IllegalTransition, State, TurnState


def test_starts_idle_mic_closed():
    s = TurnState()
    assert s.state is State.IDLE
    assert s.mic_open is False
    assert s.is_idle


def test_happy_path_to_speaking_and_back():
    s = TurnState()
    assert s.begin_capture() is True
    assert s.state is State.CAPTURING
    s.end_capture()
    assert s.state is State.TRANSCRIBING
    s.got_transcript(nonempty=True)
    assert s.state is State.PLANNING
    s.got_plan(will_speak=True)
    assert s.state is State.SPEAKING
    s.done_speaking()
    assert s.state is State.IDLE


def test_mic_open_only_in_capturing():
    """FR-6 / ADR-014: the half-duplex gate is open in exactly one state."""
    s = TurnState()
    assert not s.mic_open  # IDLE
    s.begin_capture()
    assert s.mic_open  # CAPTURING
    s.end_capture()
    assert not s.mic_open  # TRANSCRIBING
    s.got_transcript(nonempty=True)
    assert not s.mic_open  # PLANNING
    s.got_plan(will_speak=True)
    assert not s.mic_open  # SPEAKING — never listen while speaking


def test_second_begin_is_rejected_not_queued():
    """FR-5: one turn in flight; a second submit while busy is rejected."""
    s = TurnState()
    assert s.begin_capture() is True
    assert s.begin_capture() is False  # already CAPTURING
    s.end_capture()
    assert s.begin_capture() is False  # TRANSCRIBING
    s.got_transcript(nonempty=True)
    assert s.begin_capture() is False  # PLANNING


def test_five_rapid_submits_one_turn_four_rejections():
    """FR-5 acceptance: 5 rapid submits -> 1 accepted + 4 rejected."""
    s = TurnState()
    results = [s.begin_capture() for _ in range(5)]
    assert results.count(True) == 1
    assert results.count(False) == 4


def test_empty_transcript_returns_to_idle_silently():
    """FR-12: empty/garbage transcript -> IDLE, no planning, no speech."""
    s = TurnState()
    s.begin_capture()
    s.end_capture()
    s.got_transcript(nonempty=False)
    assert s.state is State.IDLE


def test_plan_with_nothing_to_say_returns_to_idle():
    """action=none has no speakable outcome -> IDLE, skip SPEAKING."""
    s = TurnState()
    s.begin_capture()
    s.end_capture()
    s.got_transcript(nonempty=True)
    s.got_plan(will_speak=False)
    assert s.state is State.IDLE


def test_barge_in_from_speaking_goes_to_capturing():
    """FR-7: PTT press during SPEAKING -> CAPTURING (not IDLE), mic reopens."""
    s = TurnState()
    s.begin_capture()
    s.end_capture()
    s.got_transcript(nonempty=True)
    s.got_plan(will_speak=True)
    assert s.state is State.SPEAKING
    assert s.barge_in() is True
    assert s.state is State.CAPTURING
    assert s.mic_open is True


def test_barge_in_only_valid_from_speaking():
    s = TurnState()
    assert s.barge_in() is False  # IDLE
    s.begin_capture()
    assert s.barge_in() is False  # CAPTURING


def test_illegal_internal_transitions_raise():
    """Internal steps are caller-driven; a wrong one is a bug, not input."""
    s = TurnState()
    with pytest.raises(IllegalTransition):
        s.end_capture()  # from IDLE
    with pytest.raises(IllegalTransition):
        s.done_speaking()  # from IDLE


def test_fail_and_reset_from_any_state():
    s = TurnState()
    s.begin_capture()
    s.fail()
    assert s.state is State.ERROR
    s.reset()
    assert s.state is State.IDLE
    assert s.begin_capture() is True  # usable again
