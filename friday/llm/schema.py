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

from ..tools.apps import APPS

# Semantic app keys are canonical (ADR-032 / ADR-033). Fixtures speak the
# way a user speaks: "open my browser" -> app="browser".
#
# The enum is DERIVED from the app table, not typed here (ADR-097): the five
# curated semantic ids plus every installed desktop entry that passed the
# scan. It is still a CLOSED enum, exact-matched by `validate.py` after NFKC —
# that is what rejects a path, a command injection and a Cyrillic confusable
# (AS-7/AS-8/AS-9), and none of it changed. Only the population did. The
# grammar does not enumerate param values, so the extra ids cost zero tokens;
# `prompt.py` lists the common ones and states the rule for the rest.
APP_ENUM: Final[tuple[str, ...]] = tuple(APPS)

# Phase 2 control vocabularies (G12). Each is exactly the set its registry
# builder in friday/tools/registry.py knows how to translate into argv — a
# superset of what SYSTEM_POLICY advertises, so no phrasing the planner already
# emits regresses, and anything outside fails closed to action=none.
VOLUME_ENUM: Final[tuple[str, ...]] = ("up", "down", "mute", "unmute", "toggle_mute")
BRIGHTNESS_ENUM: Final[tuple[str, ...]] = ("up", "down")
MEDIA_ENUM: Final[tuple[str, ...]] = (
    "play_pause", "play", "pause", "next", "previous", "stop",
)
WIFI_ENUM: Final[tuple[str, ...]] = ("on", "off")
WINDOW_ENUM: Final[tuple[str, ...]] = (
    "focus_left", "focus_right", "focus_up", "focus_down", "fullscreen", "close",
)
DICTATION_ENUM: Final[tuple[str, ...]] = ("start", "stop")
# Ten workspaces, as strings, because that is what the planner emits. This was
# `{"kind": "text"}` with the range checked only inside build_argv — the same
# shape that let brightness "brighten" reach a builder that guessed (2026-08-25).
# It matters more now: the workspace selects a Lua dispatch constant (ADR-074).
WORKSPACE_ENUM: Final[tuple[str, ...]] = tuple(str(i) for i in range(1, 11))

# Param kinds:
#   "enum" — a closed set, exact match required after NFKC normalization.
#            A confusable that does not fold to a member is rejected (AS-9).
#   "text" — a free string. Typed only here (non-empty str). Value-level
#            rules (e.g. the youtube query charset, FR-39) belong to the
#            tool, not to plan-shape validation.
PARAM_SCHEMA: Final = MappingProxyType(
    {
        "none": MappingProxyType({}),
        # Conversational reply (G8, ADR-048). No params: stage 2 uses the
        # transcript the caller already holds — the model does not pass the
        # utterance through a field. Routed in turn.py to llm/chat.py, never
        # to the executor; can never dispatch.
        "chat": MappingProxyType({}),
        "open_app": MappingProxyType({"app": {"kind": "enum", "values": APP_ENUM}}),
        "web_search": MappingProxyType({"query": {"kind": "text"}}),
        "open_youtube": MappingProxyType({}),
        "youtube_search": MappingProxyType({"query": {"kind": "text"}}),
        "remember_preference": MappingProxyType(
            {"key": {"kind": "text"}, "value": {"kind": "text"}}
        ),
        "forget_preference": MappingProxyType({"key": {"kind": "text"}}),
        "set_reminder": MappingProxyType(
            {"seconds": {"kind": "text"}, "message": {"kind": "text"}}
        ),
        "list_reminders": MappingProxyType({}),
        # No params. `id` used to be declared here as required text, which made
        # the tool unusable: reminder ids are `rem_<hex8>` and are never spoken
        # or shown, so the planner could not know one — while the validator
        # rejected an empty string, so `turn.py`'s "cancel the latest" branch
        # was unreachable and every "cancel my timer" answered "No active timer
        # to cancel." A param the model can never fill correctly is also
        # exactly what invariant #2 forbids: an opaque id from a CLOSED set, or
        # nothing. Found 2026-08-29 while fixing H7 (ADR-070).
        "cancel_reminder": MappingProxyType({}),
        "set_dnd": MappingProxyType({}),
        "resume_dnd": MappingProxyType({}),
        # Phase 2 control params are CLOSED SETS, so they are declared as enums,
        # not text. The prompt already advertises these exact vocabularies, but a
        # prompt is not a control (ADR-008): declared as "text" the validator only
        # checked non-emptiness, so an off-vocabulary value reached the registry
        # and silently became the wrong action (volume "lower" -> UP, brightness
        # anything-but-up -> DOWN). Enum here makes invariant #5 fail closed to
        # action=none, and satisfies invariant #2 (an opaque ID from a closed
        # enum, never a free string that becomes an argv element).
        "system_volume": MappingProxyType(
            {"direction": {"kind": "enum", "values": VOLUME_ENUM}}
        ),
        "system_brightness": MappingProxyType(
            {"direction": {"kind": "enum", "values": BRIGHTNESS_ENUM}}
        ),
        "system_media": MappingProxyType(
            {"action": {"kind": "enum", "values": MEDIA_ENUM}}
        ),
        "system_wifi": MappingProxyType({"state": {"kind": "enum", "values": WIFI_ENUM}}),
        # workspace stays text: it is a NUMBER, not a vocabulary. The registry
        # validates isdigit() + 1..10 and already fails closed.
        "hypr_workspace": MappingProxyType(
            {"workspace": {"kind": "enum", "values": WORKSPACE_ENUM}}
        ),
        "hypr_window": MappingProxyType(
            {"action": {"kind": "enum", "values": WINDOW_ENUM}}
        ),
        "file_open": MappingProxyType({"alias": {"kind": "text"}}),
        "create_note": MappingProxyType({"content": {"kind": "text"}}),
        "read_notes": MappingProxyType({}),
        "clipboard_read": MappingProxyType({}),
        "clipboard_set": MappingProxyType({"text": {"kind": "text"}}),
        "dictation_mode": MappingProxyType(
            {"action": {"kind": "enum", "values": DICTATION_ENUM}}
        ),
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
