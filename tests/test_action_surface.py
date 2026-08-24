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
    ws_spec = REGISTRY["hypr_workspace"]
    assert ws_spec.build_argv({"workspace": "3"}) == ["hyprctl", "dispatch", "workspace", "3"]
    with pytest.raises(PolicyRejected):
        ws_spec.build_argv({"workspace": "99"})

    win_spec = REGISTRY["hypr_window"]
    assert win_spec.build_argv({"action": "focus_left"}) == ["hyprctl", "dispatch", "movefocus", "l"]
    assert win_spec.build_argv({"action": "fullscreen"}) == ["hyprctl", "dispatch", "fullscreen", "1"]
    assert win_spec.build_argv({"action": "close"}) == ["hyprctl", "dispatch", "killactive"]


def test_file_open_argv():
    spec = REGISTRY["file_open"]
    argv = spec.build_argv({"alias": "notes"})
    assert argv[1] == FILE_REGISTRY["notes"]
