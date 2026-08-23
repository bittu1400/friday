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
    low = SYSTEM_POLICY.lower()
    assert "chat" in low                       # the action is named
    assert "greeting" in low or "chit-chat" in low or "conversation" in low
    # none is narrowed to genuine refusals/ambiguity, not casual talk
    assert "destructive" in low or "refuse" in low
