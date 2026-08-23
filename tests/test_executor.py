"""Executor contract (architecture.md §3.3): shell=False, minimal env,
bounded timeout, panic honoured, no retry, never raises."""

from __future__ import annotations

import asyncio
from types import MappingProxyType

import pytest

from friday import config
from friday.errors import Outcome
from friday.tools import executor
from friday.tools.registry import REGISTRY, ToolSpec

RID = "test-request"


def _spec(argv: list[str], target: str, timeout: float = 5.0) -> ToolSpec:
    return ToolSpec(
        tool_id="probe",
        risk="reversible",
        build_argv=lambda p: argv,
        target_binary=lambda p: target,
        display=lambda p: "the probe",
        cwd="/",
        env=MappingProxyType({"PATH": "/usr/bin:/bin"}),
        timeout_s=timeout,
    )


def _run(coro):
    return asyncio.run(coro)


def test_success_on_zero_exit() -> None:
    r = _run(executor.execute(_spec(["true"], "true"), {}, RID))
    assert r.outcome is Outcome.OK


def test_error_on_nonzero_exit() -> None:
    r = _run(executor.execute(_spec(["false"], "false"), {}, RID))
    assert r.outcome is Outcome.ERROR


def test_not_found_when_binary_absent() -> None:
    r = _run(executor.execute(_spec(["nope"], "definitely_missing_xyz"), {}, RID))
    assert r.outcome is Outcome.NOT_FOUND


def test_timeout_kills_and_reports() -> None:
    r = _run(executor.execute(_spec(["sleep", "5"], "sleep", timeout=0.2), {}, RID))
    assert r.outcome is Outcome.TIMEOUT


def test_dry_run_does_not_launch() -> None:
    r = _run(executor.execute(_spec(["true"], "true"), {}, RID, dry_run=True))
    assert r.outcome is Outcome.OK
    assert "dry-run" in r.display


def test_panic_switch_blocks_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    # FR-36: panic checked before every dispatch, fails closed.
    monkeypatch.setattr(config, "is_disabled", lambda: True)
    r = _run(executor.execute(_spec(["true"], "true"), {}, RID))
    assert r.outcome is Outcome.DISABLED


def test_policy_rejected_query_is_denied_not_dispatched() -> None:
    spec = REGISTRY["youtube_search"]
    r = _run(executor.execute(spec, {"query": "lofi; rm -rf ~"}, RID))
    assert r.outcome is Outcome.DENIED
