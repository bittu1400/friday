"""Prompt assembly: preferences inject as DATA, eval sees policy unchanged
(FR-55)."""

from __future__ import annotations

from friday.llm.prompt import SYSTEM_POLICY, assemble_system


def test_no_prefs_is_policy_verbatim() -> None:
    # Eval injects no prefs; the planning prompt must be byte-identical to
    # the baseline SYSTEM_POLICY so the eval set cannot silently drift.
    assert assemble_system("") == SYSTEM_POLICY


def test_prefs_block_is_appended_as_data() -> None:
    digest = "<preferences>\nbrowser=brave\n</preferences>"
    out = assemble_system(digest)
    assert out.startswith(SYSTEM_POLICY)
    assert digest in out
    assert "DATA, not" in out  # named as data, not instructions


def test_prefs_lines_are_key_value_only() -> None:
    digest = "<preferences>\nbrowser=brave\neditor=code\n</preferences>"
    inner = [
        ln
        for ln in digest.splitlines()
        if ln and not ln.startswith("<")
    ]
    assert all("=" in ln and " " not in ln.split("=")[0] for ln in inner)


def test_policy_mentions_chat_routing() -> None:
    from friday.llm.prompt import SYSTEM_POLICY

    # Anchor on the literal action-entry line prefix (two-space indent, the
    # name, then a space before the description) used by every entry in the
    # enum block. A plain substring check on lowercased text would pass on
    # "chit-chat" alone even with no `chat` action -- this only passes when
    # `chat` exists as its own entry.
    assert "\n  chat " in SYSTEM_POLICY

    low = SYSTEM_POLICY.lower()
    assert "greeting" in low or "conversation" in low

    # `none` must no longer claim casual talk/chit-chat for itself -- that
    # routing moved to `chat`. Isolate the `none` entry's text (from its line
    # up to the `chat` line that must immediately follow it) and check it.
    none_idx = SYSTEM_POLICY.index("\n  none ")
    chat_idx = SYSTEM_POLICY.index("\n  chat ")
    none_entry = SYSTEM_POLICY[none_idx:chat_idx].lower()
    assert "chit-chat" not in none_entry and "greeting" not in none_entry

    # none is narrowed to genuine refusals/ambiguity, not casual talk
    assert "destructive" in low or "refuse" in low


def test_chat_system_is_persona_and_spoken_safe():
    from friday.llm.prompt import CHAT_SYSTEM
    low = CHAT_SYSTEM.lower()
    assert "friday" in low
    assert "sentence" in low            # the <=4-sentence bound is stated
    assert "markdown" in low or "spoken" in low  # spoken-aloud constraint


def test_assemble_chat_system_appends_prefs_as_data():
    from friday.llm.prompt import CHAT_SYSTEM, assemble_chat_system
    assert assemble_chat_system("") == CHAT_SYSTEM
    digest = "<preferences>\nname=Subham\n</preferences>"
    out = assemble_chat_system(digest)
    assert out.startswith(CHAT_SYSTEM)
    assert digest in out
    assert "DATA, not" in out           # named as data, not instructions


def test_assemble_chat_system_appends_habits_as_data():
    from friday.llm.prompt import CHAT_SYSTEM, assemble_chat_system
    habits = "<user_habits>\n- After opening Brave, you often open VS Code.\n</user_habits>"
    out = assemble_chat_system(habits_digest=habits)
    assert out.startswith(CHAT_SYSTEM)
    assert habits in out
    assert "observed user habits" in out
    assert "DATA, not" in out


def test_assemble_chat_system_appends_summaries_as_data():
    from friday.llm.prompt import CHAT_SYSTEM, assemble_chat_system
    summaries = "<past_sessions>\n- User worked on Python in VS Code.\n</past_sessions>"
    out = assemble_chat_system(summaries_digest=summaries)
    assert out.startswith(CHAT_SYSTEM)
    assert summaries in out
    assert "distilled summaries of past sessions" in out
    assert "DATA, not" in out


