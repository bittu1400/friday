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


def test_plan_grammar_constrains_the_seven_closed_enums() -> None:
    """ADR-128: the seven machine-independent closed enum actions must have their
    allowed values pinned in plan.gbnf so spelling failures (D19, D20, D34) are
    structurally impossible server-side."""
    expected_seven = (
        "system_volume", "system_brightness", "system_media", "system_wifi",
        "hypr_workspace", "hypr_window", "dictation_mode",
    )
    assert schema.CONSTRAINED_ENUM_ACTIONS == expected_seven
    assert set(schema.CONSTRAINED_ENUM_ACTIONS) | set(schema.GENERIC_ACTIONS) == set(schema.ACTIONS)
    assert set(schema.CONSTRAINED_ENUM_ACTIONS).isdisjoint(set(schema.GENERIC_ACTIONS))

    content = (GDIR / "plan.gbnf").read_text()
    for cid in expected_seven:
        cid_slug = cid.replace("_", "-")
        assert f"action-{cid_slug}" in content
        assert f"params-{cid_slug}" in content
        # Verify specific values are present
        cap = schema.PARAM_SCHEMA[cid]
        for param_spec in cap.values():
            if param_spec.get("kind") == "enum":
                for val in param_spec["values"]:
                    assert f'\\"{val}\\"' in content


def test_plan_grammar_does_not_constrain_open_app() -> None:
    """ADR-128: open_app.app is generated from XDG entries and must NOT be constrained
    in plan.gbnf — enumerating it would break byte-identity across machines, and a
    constrained app cannot fail closed (it would force hallucination of a wrong app)."""
    assert "open_app" in schema.GENERIC_ACTIONS
    assert "open_app" not in schema.CONSTRAINED_ENUM_ACTIONS

    content = (GDIR / "plan.gbnf").read_text()
    assert "action-open-app" not in content
    assert "val-open-app-app" not in content
    assert '\\"open_app\\"' in content

