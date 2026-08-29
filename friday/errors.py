"""Error taxonomy (spec.md §4). Log the code, speak the template, never
speak or log a raw exception.

A code lives here once the tree can actually reach it. As of 2026-08-29 that
is every code in spec §4 except two, and their absence is deliberate:

    E_NET_DOWN    the search path speaks `templates.SEARCH_UNAVAILABLE` and
                  writes an audit row with outcome `net_down`; the string
                  constant is the contract there, not a code symbol.
    E_DB_LOCKED   unreachable by construction — one connection behind one lock
                  (FR-51), so SQLite has no second writer to contend with.

If either becomes reachable, define it here rather than logging a literal.
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
# G2/G8 (the LLM): reachable in `turn._plan`, which catches both and speaks a
# template. They were cited in comments and defined nowhere until 2026-08-29.
E_LLM_DOWN = "E_LLM_DOWN"  # llama-server unreachable, or answering with a status
E_LLM_TIMEOUT = "E_LLM_TIMEOUT"  # generation exceeded the budget
# G10 (always-on audio): a PortAudio callback failed repeatedly and its feature
# was disabled (M-A1). Logged, never spoken — the user hears nothing change.
E_AUDIO_DEAD = "E_AUDIO_DEAD"


class PolicyRejected(Exception):
    """A value passed grammar + validation but violates a tool policy
    (e.g. the youtube query charset, FR-39). Carries an error code."""

    def __init__(self, code: str = E_POLICY_DENIED) -> None:
        super().__init__(code)
        self.code = code
