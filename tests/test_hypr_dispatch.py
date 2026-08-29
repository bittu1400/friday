"""The Hyprland tools had never worked on this machine (OQ-38, ADR-074).

Two causes, both found only when ADR-073 made a command's exit code a verdict:
`HYPRLAND_INSTANCE_SIGNATURE` was missing from the executor's minimal env, so
hyprctl could not find the compositor at all; and Hyprland 0.56 routes
`dispatch` through Lua, so the old `hyprctl dispatch workspace 2` form no
longer parses. Friday announced success both times.

The Lua form means an argv element is now a small program, so these tests exist
mainly to prove the thing ADR-074 promises: **no parameter is ever formatted
into it.** The param selects one of a fixed set of constant strings built at
import time, or it is rejected.
"""

import os

import pytest

from friday.errors import PolicyRejected
from friday.llm.schema import PARAM_SCHEMA, WORKSPACE_ENUM
from friday.tools import registry


def test_workspace_switch_uses_the_lua_dispatcher():
    argv = registry._build_workspace_argv({"workspace": "3"})
    assert argv == ["hyprctl", "dispatch", "hl.dsp.focus{workspace=3}"]


def test_window_actions_map_to_dispatcher_constants():
    b = registry._build_window_argv
    assert b({"action": "close"})[2] == "hl.dsp.window.close{}"
    assert b({"action": "fullscreen"})[2] == "hl.dsp.window.fullscreen{}"
    assert b({"action": "focus_left"})[2] == 'hl.dsp.focus{direction="left"}'
    assert b({"action": "focus_down"})[2] == 'hl.dsp.focus{direction="down"}'


@pytest.mark.parametrize(
    "bad",
    [
        '3"} hl.dsp.window.close{',   # break out of the table
        "3} or hl.dsp.exit{",         # Lua injection through the closing brace
        "1; hl.dsp.exit{}",
        "0", "11", "-1", "3.0", "", " 3", "3 ", "three", "٣",  # Arabic-Indic digit
    ],
)
def test_a_value_outside_the_closed_set_never_reaches_the_lua(bad):
    with pytest.raises(PolicyRejected):
        registry._build_workspace_argv({"workspace": bad})


def test_nothing_is_formatted_into_the_lua_at_call_time():
    """ADR-074's actual guarantee: the param is a KEY, not an input to a
    format string. Every reachable dispatch string is a compile-time constant."""
    produced = {
        registry._build_workspace_argv({"workspace": w})[2] for w in WORKSPACE_ENUM
    }
    assert produced <= set(registry._LUA_DISPATCH.values())
    assert all(isinstance(v, str) for v in registry._LUA_DISPATCH.values())


def test_workspace_is_a_closed_enum_in_the_schema():
    """It was `{"kind": "text"}` until 2026-08-29, so the range check lived only
    in build_argv — the same "a prompt is not a control" shape that let
    `brightness "brighten"` dim the screen."""
    spec = PARAM_SCHEMA["hypr_workspace"]["workspace"]
    assert spec["kind"] == "enum"
    assert spec["values"] == WORKSPACE_ENUM
    assert WORKSPACE_ENUM == tuple(str(i) for i in range(1, 11))


def test_the_tool_env_carries_the_instance_signature(monkeypatch):
    """Without it hyprctl says "is hyprland running?" and exits 1 — the same
    class of defect as the missing DISPLAY that made every "Opened X." a lie."""
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "probe_sig")
    env = registry._build_app_env()
    assert env["HYPRLAND_INSTANCE_SIGNATURE"] == "probe_sig"


def test_the_tool_env_omits_what_the_session_does_not_have(monkeypatch):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    assert "HYPRLAND_INSTANCE_SIGNATURE" not in registry._build_app_env()
