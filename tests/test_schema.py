"""The grammar and the validator are one schema, two consumers (ADR-006).
This asserts the committed grammar files match what the schema generates —
a drift here means generation and validation disagree, and the build fails.
"""

from __future__ import annotations

from pathlib import Path

from friday.llm import schema

GDIR = Path(schema.__file__).parent / "grammars"


def test_plan_grammar_matches_schema() -> None:
    assert (GDIR / "plan.gbnf").read_text() == schema.build_grammar(), (
        "plan.gbnf is stale — run: uv run python -m friday.llm.schema"
    )


def test_final_grammar_matches_schema() -> None:
    assert (GDIR / "final.gbnf").read_text() == schema.build_final_grammar(), (
        "final.gbnf is stale — run: uv run python -m friday.llm.schema"
    )


def test_final_grammar_allows_only_none() -> None:
    # The invariant behind ADR-008: a grounding turn cannot name any action
    # but "none". Asserted on the schema so it cannot drift.
    assert schema.FINAL_ACTIONS == ("none",)
    assert '"\\"open_app\\""' not in schema.build_final_grammar()


def test_every_action_has_a_param_schema() -> None:
    assert set(schema.ACTIONS) == set(schema.PARAM_SCHEMA)
