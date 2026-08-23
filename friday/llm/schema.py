"""Single source of truth for the planning action schema.

Both the GBNF grammar and the application-side validator are derived from
the definitions in this file, so they cannot silently drift (ADR-006 wants
grammar AND validation; this is how they stay one schema, two consumers).
`tests/test_schema.py` regenerates the grammars and asserts they match the
committed files — a drift there fails the build.

The `thought` field was removed at G3: OQ-08 measured a 0-fixture delta, so
per the pre-committed ADR-011 rule it earns nothing and its removal also
closes the sensitive-scratchpad privacy concern permanently.

Scope note: this file defines the *shape* of a plan. It does NOT build
argv, resolve semantic app keys to binaries, or sanitize the youtube query
into a URL — those live in the tool registry (`friday/tools/`). The app
enum here is the *semantic* vocabulary a user speaks (browser, terminal,
...); brand resolution (browser -> brave) is the registry's job.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

# Semantic app keys are canonical (ADR-032 / ADR-033). Fixtures speak the
# way a user speaks: "open my browser" -> app="browser".
APP_ENUM: Final[tuple[str, ...]] = ("browser", "terminal", "editor", "video", "vlc")

# Param kinds:
#   "enum" — a closed set, exact match required after NFKC normalization.
#            A confusable that does not fold to a member is rejected (AS-9).
#   "text" — a free string. Typed only here (non-empty str). Value-level
#            rules (e.g. the youtube query charset, FR-39) belong to the
#            tool, not to plan-shape validation.
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

# Ordering is fixed and load-bearing: the committed grammars must be
# reproducible byte-for-byte.
ACTIONS: Final[tuple[str, ...]] = tuple(PARAM_SCHEMA)

# A turn that has consumed untrusted data may ONLY answer, never act
# (ADR-008, invariant #1). final.gbnf constrains the action name to exactly
# "none". Generated here so it cannot drift from the enum; its *enforcement*
# (untrusted region -> final.gbnf) is wired at the search gate (G7).
FINAL_ACTIONS: Final[tuple[str, ...]] = ("none",)


def _q(s: str) -> str:
    """Quote a literal for a GBNF terminal."""
    return '"\\"' + s + '\\""'


def _grammar(names: tuple[str, ...]) -> str:
    name_alt = " | ".join(_q(a) for a in names)
    return "\n".join(
        [
            "# Generated from friday/llm/schema.py — do not edit by hand.",
            "# Regenerate with: uv run python -m friday.llm.schema",
            "",
            'root ::= "{" ws "\\"action\\"" ws ":" ws action ws "}" ws',
            'action ::= "{" ws "\\"name\\"" ws ":" ws name ws "," ws '
            '"\\"params\\"" ws ":" ws params ws "}"',
            f"name ::= {name_alt}",
            'params ::= "{" ws ( pair ( ws "," ws pair )* ws )? "}"',
            'pair ::= string ws ":" ws string',
            r'string ::= "\"" char* "\""',
            r'char ::= [^"\\] | "\\" (["\\/bfnrt] | "u" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F])',
            "ws ::= [ \\t\\n]*",
            "",
        ]
    )


def build_grammar() -> str:
    """The full planning grammar: the whole action enum."""
    return _grammar(ACTIONS)


def build_final_grammar() -> str:
    """The grounding grammar: action name can only be "none" (ADR-008)."""
    return _grammar(FINAL_ACTIONS)


if __name__ == "__main__":
    from pathlib import Path

    gdir = Path(__file__).parent / "grammars"
    gdir.mkdir(exist_ok=True)
    (gdir / "plan.gbnf").write_text(build_grammar())
    (gdir / "final.gbnf").write_text(build_final_grammar())
    print(f"wrote {gdir}/plan.gbnf and final.gbnf")
