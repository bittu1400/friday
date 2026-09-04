"""A capability without eval fixtures fails the suite (criterion 3.6).

The gate is only ever as wide as its fixtures, and this repo has paid for that
twice. **D16:** 28 fixtures, all Phase-1 actions, so 20 of the 28 actions in
`PARAM_SCHEMA` had no fixture at all — two models scored 28/28 while emitting
`action=none` for "copy that to the clipboard". **D31:** the ten scanned-app
fixtures were all programs whose names ARE their ids, so a 60/60 gate sat on top
of an `open_app` that could not reach 160 of its 165 ids.

`examples` is the obligation. `tests/fixtures/eval.jsonl` stays the source of
truth — generating it from the record would move `just eval` off its baseline
inside a behaviour-freeze refactor — so the rule is that every example must
EXIST there, against the right action.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from friday.capabilities import CAPABILITIES, Capability, Risk

_FIXTURES = Path(__file__).parent / "fixtures" / "eval.jsonl"


def _by_action() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for line in _FIXTURES.read_text().splitlines():
        if not line.strip():
            continue
        fx = json.loads(line)
        out.setdefault(fx["expect"]["name"], set()).add(fx["utt"])
    return out


def test_every_capability_declares_at_least_two_examples() -> None:
    thin = {c.id: len(c.examples) for c in CAPABILITIES.values() if len(c.examples) < 2}
    assert not thin, f"a capability needs >=2 examples: {thin}"


def test_every_example_exists_as_an_eval_fixture_for_that_action() -> None:
    """Not "an example exists" — the example must be a fixture the gate scores,
    against THIS action. An example that scores nothing is a comment."""
    fixtures = _by_action()
    missing = {
        cid: sorted(set(cap.examples) - fixtures.get(cid, set()))
        for cid, cap in CAPABILITIES.items()
        if set(cap.examples) - fixtures.get(cid, set())
    }
    assert not missing, (
        f"these examples are in no eval fixture for their action: {missing}. "
        "Add the fixture to tests/fixtures/eval.jsonl, run `just eval`, then "
        "`just eval-baseline` — a NEW fixture that fails is never a regression "
        "(F23), so the count alone will not tell you."
    )


def test_a_capability_with_no_examples_fails_this_suite() -> None:
    """Criterion 3.6's acceptance, proven rather than asserted: a stub
    capability with empty `examples` must be caught. `examples` defaults to `()`
    precisely so that forgetting it is possible — and then caught here rather
    than by nobody."""
    stub = Capability(
        "stub_capability", {}, Risk.LOW, summary="a stub. params: {}",
        persona="do a stub thing",
    )
    assert stub.examples == ()

    fixtures = _by_action()
    with pytest.raises(AssertionError):
        assert len(stub.examples) >= 2, "a capability needs >=2 examples"
    assert set(stub.examples) - fixtures.get(stub.id, set()) == set()  # vacuous
    # …which is why the real check is the LENGTH one above: an empty tuple is a
    # subset of everything, so "every example is a fixture" passes vacuously.
    # Both tests are needed; neither alone catches this stub.
