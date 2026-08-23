"""Single source of truth for the planning action schema.

Both the GBNF grammar and the application-side validator are derived from
the definitions in this file, so they cannot silently drift (ADR-006 wants
grammar AND validation; this is how they stay one schema, two consumers).
`tests/test_schema.py` regenerates the grammar and asserts it matches the
committed `grammars/plan.gbnf` — a drift there fails the build.

Scope note (G2): this file defines the *shape* of a plan. It does NOT
build argv, resolve semantic app keys to binaries, or sanitize the
youtube query into a URL — those live in the G3 tool registry. The app
enum here is the *semantic* vocabulary a user speaks (browser, terminal,
...), decided 2026-08-23; brand resolution (browser -> brave) is G3.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

# Semantic app keys are canonical (decided 2026-08-23; registry is ADR-032).
# Fixtures speak the way a user speaks: "open my browser" -> app="browser".
APP_ENUM: Final[tuple[str, ...]] = ("browser", "terminal", "editor", "video", "vlc")

# `thought` is a short scratchpad, capped and never persisted (ADR-011).
THOUGHT_MAX: Final[int] = 120

# Param kinds:
#   "enum" — a closed set, exact match required after NFKC normalization.
#            A confusable that does not fold to a member is rejected (AS-9).
#   "text" — a free string. Typed only here (non-empty str). Value-level
#            rules (e.g. the youtube query charset, FR-39) belong to the
#            G3 tool, not to plan shape validation.
PARAM_SCHEMA: Final = MappingProxyType(
    {
        "none": MappingProxyType({}),
        "open_app": MappingProxyType({"app": {"kind": "enum", "values": APP_ENUM}}),
        "web_search": MappingProxyType({"query": {"kind": "text"}}),
        "open_youtube": MappingProxyType({}),
        "youtube_search": MappingProxyType({"query": {"kind": "text"}}),
        "remember_preference": MappingProxyType(
            {"key": {"kind": "text"}, "value": {"kind": "text"}}
        ),
        "forget_preference": MappingProxyType({"key": {"kind": "text"}}),
    }
)

# Ordering is fixed and load-bearing: the grammar's name alternation and the
# committed plan.gbnf must be reproducible byte-for-byte.
ACTIONS: Final[tuple[str, ...]] = tuple(PARAM_SCHEMA)


def _q(s: str) -> str:
    """Quote a literal for a GBNF terminal."""
    return '"\\"' + s + '\\""'


def build_grammar(*, with_thought: bool) -> str:
    """Return the GBNF planning grammar.

    The grammar constrains JSON shape and the action-name enum. It does NOT
    encode per-action param dependencies — that is the validator's job
    (ADR-006: the grammar narrows generation, the validator fails closed).
    `params` is a flat string->string object here; every param this schema
    defines is string-valued, and the validator rejects any key not allowed
    for the chosen action.

    `with_thought` toggles the `thought` field for the OQ-08 experiment
    (does the scratchpad measurably help tool selection?).
    """
    names = " | ".join(_q(a) for a in ACTIONS)
    lines = [
        "# Generated from friday/llm/schema.py — do not edit by hand.",
        "# Regenerate with: uv run python -m friday.llm.schema",
        "",
    ]
    if with_thought:
        lines.append(
            'root ::= "{" ws "\\"thought\\"" ws ":" ws string ws "," '
            'ws "\\"action\\"" ws ":" ws action ws "}" ws'
        )
    else:
        lines.append(
            'root ::= "{" ws "\\"action\\"" ws ":" ws action ws "}" ws'
        )
    lines += [
        'action ::= "{" ws "\\"name\\"" ws ":" ws name ws "," ws '
        '"\\"params\\"" ws ":" ws params ws "}"',
        f"name ::= {names}",
        'params ::= "{" ws ( pair ( ws "," ws pair )* ws )? "}"',
        'pair ::= string ws ":" ws string',
        r'string ::= "\"" char* "\""',
        r'char ::= [^"\\] | "\\" (["\\/bfnrt] | "u" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F])',
        'ws ::= [ \\t\\n]*',
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    # Regenerate the committed grammar files from the schema.
    from pathlib import Path

    gdir = Path(__file__).parent / "grammars"
    gdir.mkdir(exist_ok=True)
    (gdir / "plan.gbnf").write_text(build_grammar(with_thought=True))
    (gdir / "plan_no_thought.gbnf").write_text(build_grammar(with_thought=False))
    print(f"wrote {gdir}/plan.gbnf and plan_no_thought.gbnf")
