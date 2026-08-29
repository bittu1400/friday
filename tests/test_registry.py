"""The registry is a security surface (ADR-007). These lock its shape."""

from __future__ import annotations

from friday.llm import schema
from friday.tools.apps import APPS
from friday.tools.registry import NOT_YET_WIRED, REGISTRY


def test_no_irreversible_tools() -> None:
    # FR-33: Phase 1 ships only read_only and reversible.
    assert all(spec.risk != "irreversible" for spec in REGISTRY.values())


def test_every_registered_tool_is_a_known_action() -> None:
    known = set(schema.ACTIONS)
    assert set(REGISTRY) <= known
    assert set(NOT_YET_WIRED) <= known


def test_open_app_builds_direct_binary_argv_per_app() -> None:
    # ADR-043: spawn the app binary directly (no hyprctl wrapper). The model's
    # enum key never appears verbatim in argv; the binary does.
    spec = REGISTRY["open_app"]
    for key, app in APPS.items():
        argv = spec.build_argv({"app": key})
        # argv is the fixed table entry verbatim (binary + any fixed flags,
        # e.g. mpv's idle flags); never the model's enum key, and the binary
        # is argv[0] for the which() preflight.
        assert argv == list(app.argv)
        assert spec.target_binary({"app": key}) == app.argv[0]


def test_env_is_minimal_and_explicit() -> None:
    # No inherited environment (FR-32): PATH and HOME always, plus ONLY the
    # session/compositor-addressing vars a GUI client needs. Nothing else may
    # leak in — no PARAM-derived keys, no wildcard passthrough.
    allowed = {
        "PATH",
        "HOME",
        "WAYLAND_DISPLAY",
        "XDG_RUNTIME_DIR",
        "DBUS_SESSION_BUS_ADDRESS",
        "DISPLAY",
        "HYPRLAND_INSTANCE_SIGNATURE",  # ADR-074: hyprctl cannot find the
                                        # compositor without it
    }
    for spec in REGISTRY.values():
        assert {"PATH", "HOME"} <= set(spec.env)
        assert set(spec.env) <= allowed


def test_env_passes_session_vars_when_present(monkeypatch) -> None:
    # BUG regression: a directly-spawned Wayland app needs WAYLAND_DISPLAY +
    # XDG_RUNTIME_DIR to reach the compositor, and DBUS_SESSION_BUS_ADDRESS so a
    # single-instance app (Brave) hands off to its running instance and exits 0
    # (ADR-043 amendment). All pass through from the daemon's own environment
    # (never built from params).
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1000/bus")
    monkeypatch.setenv("DISPLAY", ":0")
    from friday.tools.registry import _build_app_env

    env = _build_app_env()
    assert env["WAYLAND_DISPLAY"] == "wayland-1"
    assert env["XDG_RUNTIME_DIR"] == "/run/user/1000"
    assert env["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/run/user/1000/bus"
    # Measured 2026-08-25: without DISPLAY, Brave prints "Missing X server or
    # $DISPLAY" and exits before showing a window, while the detached spawn
    # still reports ok. Chromium and Electron default to the X11 Ozone backend
    # on this machine, so every GUI launch needs it.
    assert env["DISPLAY"] == ":0"


def test_env_omits_session_vars_when_absent(monkeypatch) -> None:
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    from friday.tools.registry import _build_app_env

    assert set(_build_app_env()) == {"PATH", "HOME"}
