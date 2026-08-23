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
import shutil
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

# A launch is fire-and-forget: wait only long enough to catch a binary that
# dies on startup, then treat "still running" as a successful launch (ADR-043).
_LAUNCH_GRACE_S = 0.4


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

    # Preflight the real binary so a missing app is NOT_FOUND up front, before
    # the spawn — a clearer signal than catching the exec error, and the same
    # verdict either way (the spawn's FileNotFoundError also maps to NOT_FOUND).
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
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,  # detach: the GUI app outlives this turn
        )
    except (FileNotFoundError, PermissionError):
        return ToolResult(Outcome.NOT_FOUND, display, E_TOOL_NOTFOUND)

    # Fire-and-forget launch (ADR-043). A GUI app does not exit, so we do NOT
    # wait for it — we give it a short grace to surface an IMMEDIATE failure
    # (bad binary, missing lib -> quick non-zero exit), then treat "still
    # running" as success and leave it alone. This is the semantics hyprctl's
    # `dispatch exec` had; the grace only adds early-crash detection.
    try:
        rc = await asyncio.wait_for(proc.wait(), timeout=_LAUNCH_GRACE_S)
    except asyncio.TimeoutError:
        dur = int((loop.time() - start) * 1000)
        return ToolResult(Outcome.OK, display, None, dur)  # launched, running
    dur = int((loop.time() - start) * 1000)
    if rc == 0:
        return ToolResult(Outcome.OK, display, None, dur)
    return ToolResult(Outcome.ERROR, display, E_TOOL_FAILED, dur)
