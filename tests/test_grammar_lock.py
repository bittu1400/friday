from pathlib import Path

from friday.llm import schema

_FINAL = Path(schema.__file__).parent / "grammars" / "final.gbnf"


def test_final_grammar_action_name_has_exactly_one_alternative():
    """§9.3 / FR-23: the grounding grammar's action name must be exactly
    "none". If this ever grows a second alternative, the build fails."""
    text = _FINAL.read_text()
    name_line = next(
        ln for ln in text.splitlines() if ln.strip().startswith("name ::=")
    )
    rhs = name_line.split("::=", 1)[1]
    assert rhs.count("|") == 0                       # no alternatives
    assert '"none"' in rhs.replace('\\"', '"')       # and it is "none"


def test_build_final_grammar_matches_committed_file():
    assert schema.build_final_grammar().strip() == _FINAL.read_text().strip()
