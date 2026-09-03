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


def _spec(argv: list[str], target: str, timeout: float = 5.0, *, detach: bool = False) -> ToolSpec:
    return ToolSpec(
        tool_id="probe",
        risk="reversible",
        build_argv=lambda p: argv,
        target_binary=lambda p: target,
        display=lambda p: "the probe",
        cwd="/",
        env=MappingProxyType({"PATH": "/usr/bin:/bin"}),
        timeout_s=timeout,
        detach=detach,
    )


def _run(coro):
    return asyncio.run(coro)


def test_success_on_zero_exit() -> None:
    r = _run(executor.execute(_spec(["true"], "true"), {}, RID))
    assert r.outcome is Outcome.OK


def test_nonzero_exit_after_spawn_reports_launched() -> None:
    # ADR-043 amendment: the child's exit code is NOT a launch verdict. A
    # single-instance GUI app (Brave) launched while already running hands off
    # to the running instance — a window opens — and the launcher exits
    # NON-ZERO. which() preflighted the binary and a real exec failure raises
    # (-> NOT_FOUND) before we get here, so a spawned-then-exited process is
    # reported OK, not ERROR (which used to speak "That didn't work." over a
    # browser that actually opened).
    # detach: these are LAUNCH semantics. A command's non-zero exit IS a
    # failure since ADR-073; only a launch's is meaningless.
    r = _run(executor.execute(_spec(["false"], "false", detach=True), {}, RID))
    assert r.outcome is Outcome.OK


def test_not_found_when_binary_absent() -> None:
    r = _run(executor.execute(_spec(["nope"], "definitely_missing_xyz"), {}, RID))
    assert r.outcome is Outcome.NOT_FOUND


def test_long_running_launch_returns_ok_promptly() -> None:
    # ADR-043: a GUI app never exits, so "still running after the grace" is a
    # successful launch. We must return on the grace, NOT wait the app out and
    # NOT kill it.
    import time

    start = time.monotonic()
    r = _run(executor.execute(_spec(["sleep", "5"], "sleep", detach=True), {}, RID))
    elapsed = time.monotonic() - start
    assert r.outcome is Outcome.OK
    assert elapsed < 2.0  # returned on the 0.4 s grace, not after 5 s


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


def test_banned_argv_is_denied_at_dispatch() -> None:
    # M2, invariant #10. `assert_not_banned` is thoroughly unit-tested and the
    # executor is thoroughly unit-tested; nothing crossed between them, so
    # deleting the executor's call left 42 security tests green — the
    # adversarial and injection suites included. This asserts the WIRING.
    #
    # The path does not exist, so if the gate is ever removed the mutation
    # shows up as OK/ERROR here rather than as a deleted file.
    spec = _spec(["rm", "/nonexistent/friday-ban-probe"], "rm")
    r = _run(executor.execute(spec, {}, RID))
    assert r.outcome is Outcome.DENIED


def test_subprocess_gets_the_minimal_explicit_env_only(monkeypatch: pytest.MonkeyPatch) -> None:
    # M4, FR-32 / invariant #3: "minimal explicit env, no inheritance". No test
    # had ever read the env the executor actually passes, so `env=dict(spec.env)`
    # could become `env=None` — every launched process inheriting the daemon's
    # whole environment — with the suite green. F4 rewrites this line in Phase 3.
    captured: dict[str, object] = {}

    class _FakeProc:
        pid = 4242

        async def wait(self) -> int:
            return 0

    async def _fake_exec(*argv: str, **kw: object) -> _FakeProc:
        captured.update(kw)
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    env = MappingProxyType({"PATH": "/usr/bin:/bin", "DISPLAY": ":0"})
    spec = ToolSpec(
        tool_id="probe",
        risk="reversible",
        build_argv=lambda p: ["true"],
        target_binary=lambda p: "true",
        display=lambda p: "the probe",
        cwd="/",
        env=env,
        timeout_s=5.0,
    )
    r = _run(executor.execute(spec, {}, RID))

    assert r.outcome is Outcome.OK
    assert captured["env"] == dict(env), "the child did not get spec.env verbatim"
    assert "HOME" not in (captured["env"] or {}), "the daemon's environment leaked in"
