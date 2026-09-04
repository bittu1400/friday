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

# The param vocabularies are re-exported so `from friday.llm.schema import
# WORKSPACE_ENUM` keeps working; they are DECLARED with the record they belong
# to, in `friday/capabilities.py`, not here.
from ..capabilities import (
    APP_ENUM,
    BRIGHTNESS_ENUM,
    CAPABILITIES,
    DICTATION_ENUM,
    MEDIA_ENUM,
    VOLUME_ENUM,
    WIFI_ENUM,
    WINDOW_ENUM,
    WORKSPACE_ENUM,
)

__all__ = [
    "ACTIONS", "APP_ENUM", "BRIGHTNESS_ENUM", "DICTATION_ENUM", "FINAL_ACTIONS",
    "MEDIA_ENUM", "PARAM_SCHEMA", "VOLUME_ENUM", "WIFI_ENUM", "WINDOW_ENUM",
    "WORKSPACE_ENUM", "build_final_grammar", "build_grammar",
]

# Param kinds:
#   "enum" — a closed set, exact match required after NFKC normalization.
#            A confusable that does not fold to a member is rejected (AS-9).
#   "text" — a free string. Typed only here (non-empty str). Value-level
#            rules (e.g. the youtube query charset, FR-39) belong to the
#            tool, not to plan-shape validation.
#
# DERIVED, since 2026-09-04 (Phase 3, criterion 3.2). This was a hand-written
# dict of 25 entries and it was one of TEN places a capability lived; the
# record in `friday/capabilities.py` is now the single one, and this is a view
# over it. The proof that the derivation is faithful is that `just grammar`
# still reproduces the committed `plan.gbnf` and `final.gbnf` BYTE-FOR-BYTE —
# a refactor that changes the grammar is a refactor that changed behaviour.
#
# The app enum is itself derived from the machine's installed desktop entries
# (ADR-097) and is still CLOSED, exact-matched by `validate.py` after NFKC and
# an `app_key` fold (ADR-121) — that is what rejects a path, a command
# injection and a Cyrillic confusable (AS-7/AS-8/AS-9). Only the population
# ever changed. The grammar does not enumerate param values, so ids cost zero
# prompt tokens; `prompt.py` lists the common ones and states the rule.
PARAM_SCHEMA: Final = MappingProxyType(
    {cid: cap.params for cid, cap in CAPABILITIES.items()}
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
    """The grounding grammar (ADR-008, invariant #1). Two things it does that
    the planning grammar does not:

      1. The action name can only be "none" — the turn structurally cannot
         dispatch, no matter what untrusted web text tries to induce.
      2. `params` is forced to exactly one required key, "answer", a string —
         the synthesized spoken answer rides there (§9.3). The generic
         string:string `params` used for planning let the model emit `{}` and
         skip answering; requiring the key steers it to actually answer.

    The trailing `ws` after the root object is dropped (unlike the planning
    grammar): once `{"answer":"…"}` closes, generation stops at the brace
    instead of padding whitespace up to max_tokens.
    """
    name_alt = " | ".join(_q(a) for a in FINAL_ACTIONS)
    return "\n".join(
        [
            "# Generated from friday/llm/schema.py — do not edit by hand.",
            "# Regenerate with: uv run python -m friday.llm.schema",
            "",
            'root ::= "{" ws "\\"action\\"" ws ":" ws action ws "}"',
            'action ::= "{" ws "\\"name\\"" ws ":" ws name ws "," ws '
            '"\\"params\\"" ws ":" ws params ws "}"',
            f"name ::= {name_alt}",
            'params ::= "{" ws "\\"answer\\"" ws ":" ws string ws "}"',
            r'string ::= "\"" char* "\""',
            r'char ::= [^"\\] | "\\" (["\\/bfnrt] | "u" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F])',
            "ws ::= [ \\t\\n]*",
            "",
        ]
    )


if __name__ == "__main__":
    from pathlib import Path

    gdir = Path(__file__).parent / "grammars"
    gdir.mkdir(exist_ok=True)
    (gdir / "plan.gbnf").write_text(build_grammar())
    (gdir / "final.gbnf").write_text(build_final_grammar())
    print(f"wrote {gdir}/plan.gbnf and final.gbnf")
