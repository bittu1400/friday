"""Adversarial suite AS-1..AS-12 — hostile model output straight into the
validator, bypassing the model entirely. Every one must fail closed.

AS-13..AS-16 (youtube query hardening, FR-39x) are NOT here: they exercise
the G3 tool's URL builder, not plan-shape validation. They are added with
the registry at G3 (see progress.md G3, architecture.md layout, ADR-027).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from friday.llm.validate import SchemaError, validate

FIXTURES = Path(__file__).parent / "fixtures" / "adversarial.jsonl"


def _cases():
    return [
        pytest.param(fx["raw"], id=f"{fx['id']}:{fx['desc']}")
        for fx in (
            json.loads(line)
            for line in FIXTURES.read_text().splitlines()
            if line.strip()
        )
    ]


@pytest.mark.parametrize("raw", _cases())
def test_adversarial_rejected(raw: str) -> None:
    """Each hostile output must raise SchemaError (-> action=none, zero
    dispatch). A validator that accepts any of these is a dispatch of
    attacker-shaped input."""
    with pytest.raises(SchemaError):
        validate(raw)


def test_all_twelve_present() -> None:
    ids = {json.loads(l)["id"] for l in FIXTURES.read_text().splitlines() if l.strip()}
    assert ids == {f"AS-{i}" for i in range(1, 13)}
