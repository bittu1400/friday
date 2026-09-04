"""Every capability is reachable, and reachable exactly one way (criterion 3.4).

`_plan_and_act` was nineteen `if plan.name == ...` branches, so "is this
capability wired?" was answered by reading a chain in the order it happened to
be written. It is now a lookup, and this file is the question the lookup cannot
answer for itself: does every capability in the record have somewhere to go?

That question has bitten twice. `cancel_reminder` had a branch that could not be
REACHED — the validator required an id the planner cannot know — so the tool had
never worked at all (ADR-070). And `NOT_YET_WIRED` was a mapping that had been
empty since G7, making its branch dead code nobody noticed for months.
"""

from __future__ import annotations

from friday.capabilities import CAPABILITIES
from friday.handlers import HANDLERS
from friday.tools.registry import REGISTRY

#: Confirmed capabilities that never reach the handler lookup at all: they are
#: `Risk.ALWAYS`, so the gate always arms a `PendingAction` and the work
#: happens in `gate.resolve_pending`, which reads the selection only after an
#: explicit yes (ADR-068a — a declined confirm must not so much as fetch it).
#: Adding a third has to be a deliberate edit HERE, which is the point.
_RESOLVED_IN_GATE = {"clipboard_read", "clipboard_set"}


def test_every_capability_is_reachable() -> None:
    unreachable = (
        set(CAPABILITIES) - set(HANDLERS) - set(REGISTRY) - _RESOLVED_IN_GATE
    )
    assert not unreachable, (
        f"these capabilities can be planned but not run: {sorted(unreachable)}. "
        "Add a handler row, a registry spec, or say why in _RESOLVED_IN_GATE."
    )


def test_no_handler_row_names_something_that_is_not_a_capability() -> None:
    """The other direction: a row left behind after a capability is removed is
    dead code that still reads as coverage."""
    assert set(HANDLERS) <= set(CAPABILITIES)


def test_a_capability_is_served_one_way_only() -> None:
    """A capability in both tables has two implementations, and the lookup
    order decides which one runs — which is C1's shape (two implementations of
    one protocol IS the bug)."""
    both = set(HANDLERS) & set(REGISTRY)
    assert not both, f"served twice: {sorted(both)}"


def test_the_turn_holds_no_per_capability_branch() -> None:
    """Criterion 3.4's real content: `turn.py` must not grow a special case
    back. It may name a capability in a comment; it may not branch on one."""
    import re
    from pathlib import Path

    src = Path(__file__).parent.parent / "friday" / "turn.py"
    text = src.read_text()
    branches = set(re.findall(r'plan\.name\s*==\s*"([a-z_]+)"', text))
    # `none` is the one legitimate test: ADR-065 re-plans WITH history only
    # when the first pass, which sees the user's words alone, resolved nothing.
    # That is a property of the plan, not a capability being dispatched.
    branches -= {"none"}
    assert not branches, f"turn.py branches on {sorted(branches)}; add a handler row"
    # And it stays small enough to read in one screenful (the criterion is 400;
    # it was 941 the day this was written).
    assert len(text.splitlines()) < 400
