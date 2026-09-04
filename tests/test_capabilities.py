"""The capability record, and the two things that make it a contract.

Criterion 3.1 (the record), 3.2 (the derived schema and grammars) and 3.8 (a
risk tier on all 25) of `design-2026-09-02.md` §11.1.

The whole phase rests on one claim: moving a capability's definition into one
record changed NOTHING. Two tests are that claim — the grammars stay
byte-identical (`tests/test_schema.py`, which regenerates and diffs them) and
`just eval` stays 64/64 (`tests/test_eval_gate.py`, which is what M6 bought).
What this file adds is the third: the derived RISK reproduces every hand-coded
confirm branch in `turn.py` exactly, which is ADR-120(b).
"""

from __future__ import annotations

import dataclasses

import pytest

from friday.capabilities import CAPABILITIES, Capability, Risk
from friday.llm.schema import ACTIONS, PARAM_SCHEMA

# The order the committed grammars enumerate. Pinned here because `ACTIONS` is
# `tuple(PARAM_SCHEMA)` and PARAM_SCHEMA is now derived: a reordering of the
# record would silently rewrite plan.gbnf.
_EXPECTED_ORDER = (
    "none", "chat", "open_app", "web_search", "open_youtube", "youtube_search",
    "remember_preference", "forget_preference", "set_reminder", "list_reminders",
    "cancel_reminder", "set_dnd", "resume_dnd", "system_volume",
    "system_brightness", "system_media", "system_wifi", "hypr_workspace",
    "hypr_window", "file_open", "create_note", "read_notes", "clipboard_read",
    "clipboard_set", "dictation_mode", "local_time", "system_status",
    "window_move_to_workspace", "window_focus_app", "window_list",
)


def test_the_param_schema_is_derived_from_the_record_in_order():
    assert tuple(CAPABILITIES) == _EXPECTED_ORDER
    assert ACTIONS == _EXPECTED_ORDER
    assert len(PARAM_SCHEMA) == 30  # Phase 4a adds 5 capabilities -> 30
    for cid, cap in CAPABILITIES.items():
        assert PARAM_SCHEMA[cid] is cap.params


def test_no_capability_can_ship_without_an_explicit_risk():
    """Criterion 3.8: `risk` has NO DEFAULT. A default is how 'every capability
    declares its tier' quietly stops being true — the next capability added
    would inherit someone's guess instead of a decision."""
    with pytest.raises(TypeError):
        Capability("stub", {}, )  # type: ignore[call-arg]

    for cid, cap in CAPABILITIES.items():
        assert isinstance(cap.risk, Risk) or callable(cap.risk), cid
        assert isinstance(cap.risk_for({}), Risk), cid


def test_the_record_is_frozen():
    cap = CAPABILITIES["read_notes"]
    assert dataclasses.is_dataclass(cap)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cap.id = "something_else"  # type: ignore[misc]


def test_the_derived_tiers_reproduce_every_hand_coded_confirm_exactly():
    """ADR-120(b), and the reason `tests/test_confirm_arming.py` can keep
    passing untouched through this phase. `turn.py` gates five things today and
    three of them are conditional on a PARAM, not on the action — which is why
    `risk` had to accept a callable (owner's call, 2026-09-04)."""
    gated = Risk.ALWAYS

    assert CAPABILITIES["clipboard_read"].risk_for({}) is gated
    assert CAPABILITIES["clipboard_set"].risk_for({"text": "x"}) is gated

    wifi = CAPABILITIES["system_wifi"]
    assert wifi.risk_for({"state": "off"}) is gated
    assert wifi.risk_for({"state": "on"}) is Risk.LOW      # NOT gated today

    window = CAPABILITIES["hypr_window"]
    assert window.risk_for({"action": "close"}) is gated
    for free in ("focus_left", "focus_right", "focus_up", "focus_down", "fullscreen"):
        assert window.risk_for({"action": free}) is Risk.LOW


def test_open_app_gates_settings_panels_and_asks_once_for_everything_else():
    """The one intentional behaviour change of this phase (ADR-120(a)): the
    owner chose FIRST_USE for all 165 ids over the safer plumbing-only option.
    It is DECLARED here and is not live until the approvals table (3.9) and the
    derived gate (3.5) land, in that order."""
    from friday.tools.apps import APPS

    open_app = CAPABILITIES["open_app"]

    settings = [k for k, a in APPS.items() if a.confirm]
    assert settings, "no Settings-category app on this machine to test with"
    for key in settings:
        assert open_app.risk_for({"app": key}) is Risk.ALWAYS, key

    for ordinary in ("browser", "terminal", "editor", "firefox", "android_studio"):
        if ordinary in APPS:
            assert open_app.risk_for({"app": ordinary}) is Risk.FIRST_USE, ordinary

    # An id that is not installed resolves to the ordinary tier rather than
    # raising; the validator has already rejected it long before this is asked.
    assert open_app.risk_for({"app": "nope_not_installed"}) is Risk.FIRST_USE


def test_a_read_only_capability_never_confirms():
    for cid in ("none", "chat", "list_reminders", "read_notes"):
        assert CAPABILITIES[cid].risk_for({}) is Risk.NONE


# --- criterion 3.3: the two prompt regions ----------------------------------


def test_no_capability_can_ship_without_a_summary_or_a_persona_clause():
    """Criterion 3.3, and F2 closed by construction.

    Neither field has a default, for the same reason `risk` does not: a
    default is how "every capability describes itself" quietly stops being
    true. F2 is what that looks like in production — the chat persona denied
    an ability the schema had, TWICE, months apart (`system_wifi` in D24, then
    the whole app enum after ADR-097), and the second one survived a coverage
    test because it checks action NAMES and an app id is a parameter VALUE.
    """
    with pytest.raises(TypeError):
        Capability("stub", {}, Risk.LOW)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        Capability("stub", {}, Risk.LOW, summary="x")  # type: ignore[call-arg]

    for cid, cap in CAPABILITIES.items():
        assert cap.summary and cap.summary.strip() == cap.summary, cid
        # `none` and `chat` never reach the executor, so there is no ability
        # to advertise; everything else must have a clause.
        if cid in {"none", "chat"}:
            assert cap.persona is None, cid
        else:
            assert cap.persona and cap.persona.strip() == cap.persona, cid


def test_every_summary_and_persona_clause_reaches_its_prompt():
    """The derivation, asserted from the record's side.

    `tests/test_prompt.py` pins the assembled strings; this pins that no
    capability's text is silently dropped on the way there.
    """
    from friday.llm.prompt import CHAT_SYSTEM, SYSTEM_POLICY

    for cid, cap in CAPABILITIES.items():
        assert f"\n  {cid:<21}{cap.summary}\n" in SYSTEM_POLICY, cid
        if cap.persona:
            assert cap.persona in CHAT_SYSTEM, cid


def test_describe_action_covers_every_capability():
    """Criterion 3.7 / audit F21. `habits.describe_action` is a chain of
    `elif tool_id == ...`, and a capability it does not name returns None — so
    the habits miner silently drops it and the daemon's re-ask has nothing to
    say. That is how `web_search`'s branch stayed permanently unreachable: the
    miner reads `action_audit`, and nothing was writing a web_search row (H1).

    The chain itself is not derived from this record, deliberately: rewriting a
    hundred lines of tuned phrasing inside a behaviour-freeze refactor would
    change what Friday says while the gate that watches for changes cannot see
    it. What IS derived is the obligation — a new capability with no phrasing
    fails here.
    """
    from friday.store.habits import describe_action

    # `none` and `chat` never reach the executor, so no audit row and nothing
    # to mine. Every other capability must have phrasing.
    missing = [
        cid for cid in CAPABILITIES
        if cid not in ("none", "chat") and describe_action(cid, "{}") is None
    ]
    assert not missing, f"describe_action says nothing about: {missing}"
