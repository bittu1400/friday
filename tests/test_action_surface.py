import pytest
from friday.errors import PolicyRejected
from friday.tools.ban import assert_not_banned
from friday.tools.registry import REGISTRY, FILE_REGISTRY


def test_hard_ban_rejects_dangerous_commands():
    # Binaries
    for b in ["rm", "pacman", "yay", "dd", "mkfs", "sh", "bash", "sudo", "shutdown"]:
        with pytest.raises(PolicyRejected):
            assert_not_banned([b, "-rf", "/"])

    # Injection patterns
    with pytest.raises(PolicyRejected):
        assert_not_banned(["ls", ";", "rm", "-rf", "/"])
    with pytest.raises(PolicyRejected):
        assert_not_banned(["echo", "hello", "|", "bash"])
    with pytest.raises(PolicyRejected):
        assert_not_banned(["echo", "$(whoami)"])


def test_hard_ban_allows_safe_tools():
    assert_not_banned(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%+"])
    assert_not_banned(["brightnessctl", "set", "+5%"])
    assert_not_banned(["playerctl", "play-pause"])
    assert_not_banned(["nmcli", "radio", "wifi", "on"])
    assert_not_banned(["hyprctl", "dispatch", "workspace", "2"])


def test_volume_tool_argv():
    spec = REGISTRY["system_volume"]
    assert spec.build_argv({"direction": "up"}) == ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%+"]
    assert spec.build_argv({"direction": "down"}) == ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%-"]
    assert spec.build_argv({"direction": "mute"}) == ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"]


def test_brightness_tool_argv():
    spec = REGISTRY["system_brightness"]
    assert spec.build_argv({"direction": "up"}) == ["brightnessctl", "set", "+5%"]
    assert spec.build_argv({"direction": "down"}) == ["brightnessctl", "set", "5%-"]


def test_media_tool_argv():
    spec = REGISTRY["system_media"]
    assert spec.build_argv({"action": "play_pause"}) == ["playerctl", "play-pause"]
    assert spec.build_argv({"action": "next"}) == ["playerctl", "next"]


def test_wifi_tool_argv():
    spec = REGISTRY["system_wifi"]
    assert spec.build_argv({"state": "on"}) == ["nmcli", "radio", "wifi", "on"]
    assert spec.build_argv({"state": "off"}) == ["nmcli", "radio", "wifi", "off"]
    with pytest.raises(PolicyRejected):
        spec.build_argv({"state": "invalid"})


def test_hypr_tools_argv():
    """These assertions used to spell out the PRE-0.56 positional form
    (`dispatch workspace 3`, `movefocus l`, `killactive`) and passed happily
    while neither tool worked on the machine at all — Hyprland 0.56 routes
    `dispatch` through Lua (OQ-38, ADR-074). A test that asserts the argv the
    code builds proves only that the code builds it."""
    ws_spec = REGISTRY["hypr_workspace"]
    assert ws_spec.build_argv({"workspace": "3"}) == [
        "hyprctl", "dispatch", "hl.dsp.focus{workspace=3}",
    ]
    with pytest.raises(PolicyRejected):
        ws_spec.build_argv({"workspace": "99"})

    win_spec = REGISTRY["hypr_window"]
    assert win_spec.build_argv({"action": "focus_left"})[2] == 'hl.dsp.focus{direction="left"}'
    assert win_spec.build_argv({"action": "fullscreen"})[2] == "hl.dsp.window.fullscreen{}"
    assert win_spec.build_argv({"action": "close"})[2] == "hl.dsp.window.close{}"


def test_file_open_argv():
    spec = REGISTRY["file_open"]
    argv = spec.build_argv({"alias": "notes"})
    assert argv[1] == FILE_REGISTRY["notes"]


def test_file_open_planner_phrasing_resolves_right_file():
    # The planner emits "my config"/"my todo", not bare keys. Each must open its
    # OWN file, never silently fall back to notes.md (reality-check finding, 2026-08-25).
    spec = REGISTRY["file_open"]
    assert spec.build_argv({"alias": "my config"})[1] == FILE_REGISTRY["config"]
    assert spec.build_argv({"alias": "my todo"})[1] == FILE_REGISTRY["todo"]


def test_file_open_unregistered_alias_fails_closed():
    spec = REGISTRY["file_open"]
    for bad in ("/etc/passwd", "", "my secrets"):
        with pytest.raises(PolicyRejected):
            spec.build_argv({"alias": bad})


# --- audit 2026-08-25: off-vocabulary control params must never guess --------
# These builders used to fall back to a default, so an unrecognized value did
# the WRONG thing (volume UP, brightness DOWN, media play-pause) while the
# spoken outcome named what the user actually asked for.

def test_control_params_fail_closed_on_unknown_value():
    cases = [
        ("system_volume", "direction", ["louder", "lower", "", "MUTE!"]),
        ("system_brightness", "direction", ["brighten", "increase", "dim", ""]),
        ("system_media", "action", ["halt", "skip", ""]),
    ]
    for tool_id, key, bad_values in cases:
        spec = REGISTRY[tool_id]
        for bad in bad_values:
            with pytest.raises(PolicyRejected):
                spec.build_argv({key: bad})


def test_control_params_still_build_known_values():
    assert REGISTRY["system_volume"].build_argv({"direction": "down"})[-1] == "5%-"
    assert REGISTRY["system_volume"].build_argv({"direction": "up"})[-1] == "5%+"
    assert REGISTRY["system_brightness"].build_argv({"direction": "down"})[-1] == "5%-"
    assert REGISTRY["system_brightness"].build_argv({"direction": "up"})[-1] == "+5%"
    assert REGISTRY["system_media"].build_argv({"action": "stop"})[-1] == "stop"


def test_schema_enforces_control_enums():
    """The validator, not the prompt, is the control (ADR-008). An
    off-vocabulary value must fail closed to action=none before it ever
    reaches a builder."""
    from friday.llm.validate import SchemaError, validate

    for bad in (
        '{"action":{"name":"system_volume","params":{"direction":"louder"}}}',
        '{"action":{"name":"system_brightness","params":{"direction":"brighten"}}}',
        '{"action":{"name":"system_wifi","params":{"state":"maybe"}}}',
        '{"action":{"name":"hypr_window","params":{"action":"minimize"}}}',
        '{"action":{"name":"dictation_mode","params":{"action":"resume"}}}',
    ):
        with pytest.raises(SchemaError):
            validate(bad)

    # and the real vocabulary still validates
    for good in (
        '{"action":{"name":"system_volume","params":{"direction":"mute"}}}',
        '{"action":{"name":"hypr_window","params":{"action":"close"}}}',
        '{"action":{"name":"hypr_workspace","params":{"workspace":"3"}}}',
    ):
        validate(good)
