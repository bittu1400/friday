"""The executor: turns a validated Plan into a bounded subprocess and a
typed Outcome. It never raises to the caller and never speaks — the caller
renders an outcome template AFTER this returns (ADR-009, execute-first).

Guarantees (architecture.md §3.3, FR-32, FR-41):
    - shell=False by construction (argv list, create_subprocess_exec)
    - minimal explicit env, no inheritance
    - bounded by spec.timeout_s; the whole process group is killed on timeout
    - NEVER retried (retrying a side effect duplicates it)
    - the panic switch is checked before every dispatch (FR-36)
    - a value that fails a tool policy (youtube charset) fails closed to
      DENIED, never dispatched
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
from dataclasses import dataclass
from typing import Mapping

from .. import config
from ..errors import (
    E_DISABLED,
    E_POLICY_DENIED,
    E_TOOL_FAILED,
    E_TOOL_NOTFOUND,
    E_TOOL_TIMEOUT,
    Outcome,
    PolicyRejected,
)
from .registry import ToolSpec


@dataclass(frozen=True)
class ToolResult:
    outcome: Outcome
    display: str
    code: str | None = None  # error code from the taxonomy, if any
    duration_ms: int = 0


async def execute(
    spec: ToolSpec,
    params: Mapping[str, str],
    request_id: str,
    *,
    dry_run: bool = False,
) -> ToolResult:
    # FR-36: panic switch, checked before every dispatch, before argv is even
    # built. Fail closed.
    if config.is_disabled():
        return ToolResult(Outcome.DISABLED, "", E_DISABLED)

    # build_argv may reject a policy-violating value (youtube charset). That
    # is a denial, not a crash.
    try:
        argv = spec.build_argv(params)
        display = spec.display(params)
        target = spec.target_binary(params)
    except PolicyRejected as exc:
        return ToolResult(Outcome.DENIED, "", exc.code)
    except KeyError:
        # A param the registry needs is absent — validation should have
        # caught this; fail closed rather than trust it.
        return ToolResult(Outcome.DENIED, "", E_POLICY_DENIED)

    # Preflight: hyprctl returns 0 even when the target app does not exist,
    # so exit code cannot tell us "not installed". Check the real binary.
    if shutil.which(target) is None:
        return ToolResult(Outcome.NOT_FOUND, display, E_TOOL_NOTFOUND)

    if dry_run:
        return ToolResult(Outcome.OK, display + f" [dry-run: {argv}]")

    loop = asyncio.get_running_loop()
    start = loop.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=spec.cwd,
            env=dict(spec.env),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,  # own process group, killable as a unit
        )
    except (FileNotFoundError, PermissionError):
        return ToolResult(Outcome.NOT_FOUND, display, E_TOOL_NOTFOUND)

    try:
        _, _ = await asyncio.wait_for(proc.communicate(), timeout=spec.timeout_s)
    except asyncio.TimeoutError:
        _kill_group(proc)
        await proc.wait()  # reap so the transport is cleaned up on this loop
        return ToolResult(Outcome.TIMEOUT, display, E_TOOL_TIMEOUT)
    finally:
        dur = int((loop.time() - start) * 1000)

    if proc.returncode == 0:
        return ToolResult(Outcome.OK, display, None, dur)
    return ToolResult(Outcome.ERROR, display, E_TOOL_FAILED, dur)


def _kill_group(proc: asyncio.subprocess.Process) -> None:
    """Kill the whole process group so a wrapper that forked children dies
    with the timeout, not just the direct child."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
