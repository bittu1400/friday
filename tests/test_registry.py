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
    # No inherited environment (FR-32): PATH and HOME always, plus ONLY the two
    # Wayland-addressing vars a client needs to reach the compositor. Nothing
    # else may leak in — no PARAM-derived keys, no wildcard passthrough.
    allowed = {"PATH", "HOME", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR"}
    for spec in REGISTRY.values():
        assert {"PATH", "HOME"} <= set(spec.env)
        assert set(spec.env) <= allowed


def test_env_passes_wayland_vars_when_present(monkeypatch) -> None:
    # BUG regression: a directly-spawned Wayland app needs WAYLAND_DISPLAY +
    # XDG_RUNTIME_DIR to reach the compositor. They pass through from the
    # daemon's own environment (never built from params).
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    from friday.tools.registry import _build_app_env

    env = _build_app_env()
    assert env["WAYLAND_DISPLAY"] == "wayland-1"
    assert env["XDG_RUNTIME_DIR"] == "/run/user/1000"


def test_env_omits_wayland_vars_when_absent(monkeypatch) -> None:
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    from friday.tools.registry import _build_app_env

    assert set(_build_app_env()) == {"PATH", "HOME"}
