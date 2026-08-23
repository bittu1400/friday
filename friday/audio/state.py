"""The turn state machine (diagram 01, FR-5, FR-6, FR-7).

One turn at a time, ever — enforced here, not by a lock (architecture.md §5).
A PTT press or text submit is only accepted from IDLE; the single exception
is a press during SPEAKING, which is *barge-in* (FR-7): cancel playback,
drop the turn, and go straight to CAPTURING because the user is already
holding the key to speak.

This object is driven from the asyncio event loop only. The audio callback
(a PortAudio thread) never mutates it — it reads `mic_open`, one boolean,
which is the half-duplex gate (FR-6, ADR-014): the mic is open in exactly
one state, CAPTURING.

The FSM covers the audio-facing states G6 reaches. The turn internals the
diagram draws (VALIDATING / EXECUTING / CONFIRMING / GROUNDING) live inside
`turn.py`; from the machine's view that whole span is PLANNING, and
execute-first (ADR-009) is preserved there, not here.
"""

from __future__ import annotations

from enum import Enum


class State(str, Enum):
    IDLE = "idle"
    CAPTURING = "capturing"  # mic OPEN, max 15 s
    TRANSCRIBING = "transcribing"  # whisper on CPU
    PLANNING = "planning"  # plan -> validate -> execute (turn.py)
    SPEAKING = "speaking"  # kokoro; mic MUTED (half duplex)
    ERROR = "error"  # say a user-safe line, then IDLE


class IllegalTransition(RuntimeError):
    """A transition attempted from a state that does not allow it. A bug in
    the caller, never reachable from user input — begin_capture / barge_in
    return a bool instead of raising, because those *are* driven by input."""


class TurnState:
    def __init__(self) -> None:
        self._state = State.IDLE

    @property
    def state(self) -> State:
        return self._state

    @property
    def mic_open(self) -> bool:
        """The half-duplex gate (FR-6). Open in exactly one state."""
        return self._state is State.CAPTURING

    @property
    def is_idle(self) -> bool:
        return self._state is State.IDLE

    # --- input-driven, may be rejected (return bool, never raise) ---------

    def begin_capture(self) -> bool:
        """PTT press / text submit. Accepted only from IDLE (FR-5); a press
        during SPEAKING is barge_in, not this. Returns False (-> E_BUSY) if a
        turn is already in flight."""
        if self._state is State.IDLE:
            self._state = State.CAPTURING
            return True
        return False

    def barge_in(self) -> bool:
        """PTT press during SPEAKING (FR-7): cancel playback + drop the turn,
        then straight to CAPTURING. Valid only from SPEAKING."""
        if self._state is State.SPEAKING:
            self._state = State.CAPTURING
            return True
        return False

    # --- internal progression (illegal calls are caller bugs) -------------

    def end_capture(self) -> None:
        """PTT release / VAD silence / 15 s cap: CAPTURING -> TRANSCRIBING."""
        self._require(State.CAPTURING)
        self._state = State.TRANSCRIBING

    def got_transcript(self, *, nonempty: bool) -> None:
        """Empty or garbage -> IDLE silently (FR-12, E_STT_EMPTY); otherwise
        on to PLANNING."""
        self._require(State.TRANSCRIBING)
        self._state = State.PLANNING if nonempty else State.IDLE

    def got_plan(self, *, will_speak: bool) -> None:
        """A speakable outcome -> SPEAKING; nothing to say (e.g. action
        `none`) -> IDLE."""
        self._require(State.PLANNING)
        self._state = State.SPEAKING if will_speak else State.IDLE

    def done_speaking(self) -> None:
        self._require(State.SPEAKING)
        self._state = State.IDLE

    # --- escape hatches, legal from anywhere ------------------------------

    def fail(self) -> None:
        """Any state -> ERROR on timeout / exception / cancel (diagram 01)."""
        self._state = State.ERROR

    def reset(self) -> None:
        """Back to IDLE. From ERROR after the safe line is spoken, or to
        abort a turn (30 s confirm timeout, panic)."""
        self._state = State.IDLE

    def _require(self, expected: State) -> None:
        if self._state is not expected:
            raise IllegalTransition(f"{expected.value} required, in {self._state.value}")
