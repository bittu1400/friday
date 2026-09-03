"""The confirm gate must be ARMED by the turn, not merely resolvable — M1.

`tests/test_clipboard_confirm.py` proves this for `clipboard_read`. The other
three gated actions had tests only for RESOLVING a `PendingAction` the test
itself constructed, so all three branches could be deleted from `turn.py` with
all 581 tests green: `system_wifi{off}` dispatched and dropped the network,
`hypr_window{close}` closed the window, neither asked (invariant #10,
demonstrated by the 2026-09-03 mutation audit).

These are the exact rows the 2026-08-30 evening microphone session existed to
prove. They were proven by voice and were pinned by nothing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from friday.turn import PendingAction, run_turn


@dataclass
class StubClient:
    reply: str

    def complete(self, *, system: str, user: str, grammar: str) -> str:
        return self.reply

    def health(self) -> bool:
        return True


# (utterance, plan JSON, expected tool_id) — one row per gate that had none.
_GATES = [
    (
        "turn off the wifi",
        '{"action":{"name":"system_wifi","params":{"state":"off"}}}',
        "system_wifi",
    ),
    (
        "copy hello to my clipboard",
        '{"action":{"name":"clipboard_set","params":{"text":"hello"}}}',
        "clipboard_set",
    ),
    (
        "close this window",
        '{"action":{"name":"hypr_window","params":{"action":"close"}}}',
        "hypr_window",
    ),
]


@pytest.mark.parametrize("utterance,plan,tool_id", _GATES, ids=[g[2] for g in _GATES])
def test_turn_arms_the_confirm_and_dispatches_nothing(utterance, plan, tool_id) -> None:
    r = asyncio.run(run_turn(utterance, StubClient(plan), request_id="t"))

    assert r.plan_name == tool_id
    assert not r.dispatched, f"{tool_id} acted without asking"
    assert isinstance(r.pending, PendingAction), f"{tool_id} armed no confirm"
    assert r.pending.tool_id == tool_id
    assert "?" in r.spoken, "the confirm must actually ask a question"


def test_wifi_on_is_not_gated() -> None:
    # The gate is on `state == "off"` specifically: turning Wi-Fi ON is
    # reversible and must not cost the user a question. Without this the three
    # tests above could be satisfied by gating system_wifi unconditionally.
    plan = '{"action":{"name":"system_wifi","params":{"state":"on"}}}'
    r = asyncio.run(run_turn("turn the wifi back on", StubClient(plan), request_id="t"))
    assert r.pending is None
