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


def test_chat_system_states_real_capabilities():
    # Fix (live-review): chat used to invent its capabilities ("I can't search",
    # a wrong app list). The persona now names the real toolset and forbids
    # inventing/omitting, so it describes itself accurately.
    from friday.llm.prompt import CHAT_SYSTEM
    low = CHAT_SYSTEM.lower()
    assert "web" in low and "youtube" in low        # the search tools it has
    assert "apps" in low                             # general installed apps
    assert "accurately" in low or "invent" in low    # honesty instruction


def test_assemble_system_history_empty_is_policy_verbatim():
    # ADR-052: history is opt-in. With neither prefs nor history, the planning
    # prompt stays byte-identical to SYSTEM_POLICY so the eval cannot drift.
    assert assemble_system("", "") == SYSTEM_POLICY
    assert assemble_system("") == SYSTEM_POLICY       # default arg


def test_assemble_system_appends_history_as_data():
    hist = "You: open brave\nFriday: Opened Brave."
    out = assemble_system("", hist)
    assert out.startswith(SYSTEM_POLICY)
    assert hist in out
    assert "<recent_conversation>" in out
    assert "DATA for context" in out                 # framed as data, not command
    assert "LATEST message" in out                    # action is for the latest turn


def test_assemble_system_prefs_and_history_both_present():
    digest = "<preferences>\nname=Subham\n</preferences>"
    hist = "You: hi\nFriday: Hello!"
    out = assemble_system(digest, hist)
    assert out.startswith(SYSTEM_POLICY)
    assert digest in out and hist in out
    # prefs block comes before the history block
    assert out.index(digest) < out.index(hist)


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




# --- D24 / ADR-091: the persona must not deny a real ability, nor claim to
# have used one. Both were observed live on 2026-08-30 within one session:
# Gemma 4 said "I cannot actually control your window size or toggle full
# screen modes" in a session where hypr_window{fullscreen} had just dispatched
# three times, and a first attempt at fixing that produced the opposite fault,
# "I have taken the window out of full screen mode for you" -- a chat turn
# claiming an action it structurally cannot perform (invariant #4, ADR-009).


def test_chat_system_forbids_denying_a_listed_ability():
    from friday.llm.prompt import CHAT_SYSTEM

    low = CHAT_SYSTEM.lower()
    # The abilities Gemma denied must be named where it cannot miss them.
    assert "fullscreen" in low
    assert "workspace" in low
    assert "never tell the user you are unable" in low


def test_chat_system_forbids_claiming_to_have_acted():
    """The talking half takes no action. Saying otherwise is a fabricated
    outcome, which is exactly what ADR-009 keeps out of the LLM's hands."""
    from friday.llm.prompt import CHAT_SYSTEM

    low = CHAT_SYSTEM.lower()
    assert "taken no action" in low
    assert "never say you have done" in low


def test_chat_system_caps_length_because_the_reply_is_spoken():
    """Length is latency here: TTFA includes synthesizing the WHOLE reply, so a
    376-character answer is a ~7-10 s wait. Measured 2026-08-30, n=38."""
    from friday.llm.prompt import CHAT_SYSTEM

    low = CHAT_SYSTEM.lower()
    assert "2 short sentences" in low
    assert "200 characters" in low


def test_chat_system_advertises_every_action_in_the_schema():
    """ADR-053 says the persona states its REAL toolset; nothing enforced it.
    `system_wifi` shipped in G12 and was never added here, so for months chat
    answered "I do not have permission to toggle your Wi-Fi" — honestly, from a
    prompt that was wrong. Observed live 2026-08-30, twice, in the same session
    where a system_wifi confirm had just been armed."""
    from friday.llm.prompt import CHAT_SYSTEM
    from friday.llm.schema import PARAM_SCHEMA

    low = CHAT_SYSTEM.lower()
    # One keyword per action that the persona must be able to speak about.
    # `chat` and `none` are not capabilities.
    keyword = {
        "open_app": "apps", "web_search": "web", "open_youtube": "youtube",
        "youtube_search": "youtube", "remember_preference": "preference",
        "forget_preference": "preference", "set_reminder": "timer",
        "list_reminders": "timer", "cancel_reminder": "timer",
        "set_dnd": "quiet", "resume_dnd": "quiet", "system_volume": "volume",
        "system_brightness": "brightness", "system_media": "media",
        "system_wifi": "wi-fi", "hypr_workspace": "workspace",
        "hypr_window": "window", "file_open": "file", "create_note": "note",
        "read_notes": "note", "clipboard_read": "clipboard",
        "clipboard_set": "clipboard", "dictation_mode": "dictation",
    }
    # Every dispatchable action needs an entry, so a NEW action fails here too.
    undeclared = set(PARAM_SCHEMA) - set(keyword) - {"chat", "none"}
    assert not undeclared, f"add a CHAT_SYSTEM keyword for: {sorted(undeclared)}"
    missing = [a for a, k in keyword.items() if k not in low]
    assert not missing, f"CHAT_SYSTEM never mentions: {missing}"


def test_chat_system_has_no_hardcoded_numeral_app_count():
    """F2: chat persona must never pin a fixed numeral app count like 'five apps'."""
    import re
    from friday.llm.prompt import CHAT_SYSTEM, SYSTEM_POLICY

    assert not re.search(r"\b(five|\d+)\s+apps\b", CHAT_SYSTEM, re.IGNORECASE), (
        "CHAT_SYSTEM contains a hardcoded numeral app count"
    )
    assert not re.search(r"\b(five|\d+)\s+app\s+ids\b", SYSTEM_POLICY, re.IGNORECASE), (
        "SYSTEM_POLICY contains a hardcoded numeral app count"
    )
