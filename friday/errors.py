"""Error taxonomy (spec.md §4). Log the code, speak the template, never
speak or log a raw exception. Only the codes G3 can actually reach are
given exceptions here; the rest are added with the gate that raises them.
"""

from __future__ import annotations

from enum import Enum


class Outcome(str, Enum):
    """The outcome of a dispatch, keyed to an outcome template (ADR-009)."""

    OK = "ok"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    DENIED = "denied"
    ERROR = "error"
    DISABLED = "disabled"  # panic switch (FR-36)


# Error codes referenced by code so far. The full taxonomy lives in spec.md §4.
E_SCHEMA = "E_SCHEMA"
E_POLICY_DENIED = "E_POLICY_DENIED"
E_TOOL_NOTFOUND = "E_TOOL_NOTFOUND"
E_TOOL_TIMEOUT = "E_TOOL_TIMEOUT"
E_TOOL_FAILED = "E_TOOL_FAILED"
E_DISABLED = "E_DISABLED"
# G6 (voice in): the audio path's codes.
E_STT_EMPTY = "E_STT_EMPTY"  # no speech -> silence, back to IDLE (FR-12)
E_STT_TIMEOUT = "E_STT_TIMEOUT"  # transcription too slow
E_BUSY = "E_BUSY"  # a turn is already in flight (FR-5)


class PolicyRejected(Exception):
    """A value passed grammar + validation but violates a tool policy
    (e.g. the youtube query charset, FR-39). Carries an error code."""

    def __init__(self, code: str = E_POLICY_DENIED) -> None:
        super().__init__(code)
        self.code = code
