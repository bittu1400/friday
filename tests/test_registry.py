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


def test_open_app_builds_hyprctl_argv_per_app() -> None:
    spec = REGISTRY["open_app"]
    for key, app in APPS.items():
        argv = spec.build_argv({"app": key})
        assert argv == ["hyprctl", "dispatch", "exec", app.argv[0]]
        # The model's enum key never appears verbatim in argv; the binary does.
        assert spec.target_binary({"app": key}) == app.argv[0]


def test_env_is_minimal_and_explicit() -> None:
    # No inherited environment (FR-32): only PATH and HOME.
    for spec in REGISTRY.values():
        assert set(spec.env) == {"PATH", "HOME"}
