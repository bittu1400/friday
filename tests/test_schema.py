"""The grammar and the validator are one schema, two consumers (ADR-006).
This asserts the committed grammar files match what the schema generates —
a drift here means generation and validation disagree, and the build fails.
"""

from __future__ import annotations

from pathlib import Path

from friday.llm import schema

GDIR = Path(schema.__file__).parent / "grammars"


def test_plan_grammar_matches_schema() -> None:
    assert (GDIR / "plan.gbnf").read_text() == schema.build_grammar(
        with_thought=True
    ), "plan.gbnf is stale — run: uv run python -m friday.llm.schema"


def test_no_thought_grammar_matches_schema() -> None:
    assert (GDIR / "plan_no_thought.gbnf").read_text() == schema.build_grammar(
        with_thought=False
    ), "plan_no_thought.gbnf is stale — run: uv run python -m friday.llm.schema"


def test_every_action_has_a_param_schema() -> None:
    assert set(schema.ACTIONS) == set(schema.PARAM_SCHEMA)
