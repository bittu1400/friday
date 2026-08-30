"""The eval gate must see every action, and the model config must exist once.

Both of these encode a defect this project actually shipped:

  * D16 — `just eval` reported 28/28 for months while the entire G12 action
    surface (20 of 28 actions) had no fixture at all. The gate that approves a
    model swap could not see the regression it would admit. FR-97.

  * C1 — two implementations of one thing IS the bug. The systemd unit and the
    `justfile` `serve` recipe are two copies of one model config; when they
    drift, `just serve` silently runs a different model from the service, and
    every measurement taken through one is a claim about the other. FR-98.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from friday.llm.schema import PARAM_SCHEMA

ROOT = Path(__file__).parent.parent
UNIT = ROOT / "deploy" / "systemd" / "friday-llm.service"
JUSTFILE = ROOT / "justfile"
FIXTURES = ROOT / "tests" / "fixtures" / "eval.jsonl"

# Flags that are load-bearing, not stylistic (ADR-090). Each is worth either
# memory or an invariant, and each has silently defaulted to the wrong thing
# at least once on this machine.
REQUIRED_FLAGS = ("--parallel 1", "-fa on", "--reasoning off", "--n-gpu-layers 99")


def _fixture_actions() -> set[str]:
    return {
        json.loads(line)["expect"]["name"]
        for line in FIXTURES.read_text().splitlines()
        if line.strip()
    }


def _model_filename(text: str) -> str:
    m = re.search(r"models/([A-Za-z0-9._-]+\.gguf)", text)
    assert m, "no model .gguf path found"
    return m.group(1)


def test_every_action_has_an_eval_fixture() -> None:
    """FR-97. A new action without a fixture is invisible to `just eval`."""
    missing = set(PARAM_SCHEMA) - _fixture_actions()
    assert not missing, (
        f"actions with no eval fixture: {sorted(missing)}. "
        "Add one to tests/fixtures/eval.jsonl — an action the gate cannot see "
        "is an action a model swap can silently break (D16)."
    )


def test_serve_recipe_and_unit_load_the_same_model() -> None:
    """FR-98. `just serve` and the service must not drift apart."""
    assert _model_filename(UNIT.read_text()) == _model_filename(JUSTFILE.read_text())


def test_both_carry_the_load_bearing_flags() -> None:
    """FR-98/FR-99. `--parallel 1` is 514 MiB; `--reasoning off` is invariant #7."""
    unit, just = UNIT.read_text(), JUSTFILE.read_text()
    for flag in REQUIRED_FLAGS:
        assert flag in unit, f"{flag} missing from friday-llm.service"
        assert flag in just, f"{flag} missing from the justfile serve recipe"


def test_reasoning_format_none_is_never_used() -> None:
    """FR-99. It looks like the fix and does the opposite: thinking is not
    suppressed, the raw thought is moved INTO message.content."""
    for f in (UNIT, JUSTFILE):
        # Comments are excluded on purpose: both files warn against this flag
        # by name, and the warning must not trip the check it documents.
        live = "\n".join(
            ln for ln in f.read_text().splitlines() if not ln.lstrip().startswith("#")
        )
        assert "--reasoning-format none" not in live, (
            f"{f.name}: --reasoning-format none leaks raw model thought into "
            "message.content (invariant #7, FR-26/57). Use --reasoning off."
        )
