"""The executor: turns a validated Plan into a bounded subprocess and a
typed Outcome. It never raises to the caller and never speaks — the caller
renders an outcome template AFTER this returns (ADR-009, execute-first).

Guarantees (architecture.md §3.3, FR-32, FR-41):
    - shell=False by construction (argv list, create_subprocess_exec)
    - minimal explicit env, no inheritance
    - a COMMAND is bounded by spec.timeout_s and its whole process group is
      killed on expiry; its exit code is the verdict (ADR-073)
    - a LAUNCH (spec.detach) is fire-and-forget: it must outlive the turn, so
      it is neither waited on nor killed, and its exit code means nothing
      (ADR-043 — a single-instance handoff exits NON-ZERO on success)
    - NEVER retried (retrying a side effect duplicates it)
    - the panic switch is checked before every dispatch (FR-36)
    - a value that fails a tool policy (youtube charset) fails closed to
      DENIED, never dispatched
"""

from __future__ import annotations

import asyncio
import contextlib
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
        from .ban import assert_not_banned
        assert_not_banned(argv)
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

    if not spec.detach:
        # A COMMAND, not a launch: wpctl, brightnessctl, playerctl, nmcli,
        # hyprctl. It exits, so wait for it — `timeout_s` was dead config until
        # 2026-08-29 (M-T1) and a hung `nmcli` was announced as a Wi-Fi change.
        try:
            rc = await asyncio.wait_for(proc.wait(), timeout=spec.timeout_s)
        except asyncio.TimeoutError:
            _kill_group(proc)
            with contextlib.suppress(Exception):
                await proc.wait()  # reap, so no zombie outlives the turn
            dur = int((loop.time() - start) * 1000)
            return ToolResult(Outcome.TIMEOUT, display, E_TOOL_TIMEOUT, dur)
        dur = int((loop.time() - start) * 1000)
        if rc != 0:
            # Here the exit code IS the verdict (ADR-073). ADR-043's warning is
            # about GUI handoffs, which take the branch below.
            return ToolResult(Outcome.ERROR, display, E_TOOL_FAILED, dur)
        return ToolResult(Outcome.OK, display, None, dur)

    # Fire-and-forget launch (ADR-043, amended). A GUI app does not exit, so we
    # do NOT wait for it — we give it a short grace only to catch a launch that
    # never happened, then leave it alone.
    #
    # The child's EXIT CODE is NOT a launch verdict (ADR-043 amendment): a
    # single-instance app (Brave/Chromium) launched while already running hands
    # off to the running instance — a window opens — and the launcher process
    # exits NON-ZERO. Treating that non-zero as failure spoke "That didn't work."
    # over a browser that DID open, so the user retried and piled up windows.
    # which() already preflighted the binary and a real exec failure raises
    # FileNotFoundError above (-> NOT_FOUND), so once we have spawned, we report
    # the launch as OK regardless of how the (possibly handoff) process exits.
    #
    # What we still cannot tell is whether a WINDOW appeared: a binary that
    # spawns and instantly dies (missing lib, early segfault) looks identical
    # from here. So the OK template does not claim one — it says "Launching X."
    # rather than "Opened X." (ADR-073).
    try:
        await asyncio.wait_for(proc.wait(), timeout=_LAUNCH_GRACE_S)
    except asyncio.TimeoutError:
        pass  # still running past the grace — the normal GUI case
    dur = int((loop.time() - start) * 1000)
    return ToolResult(Outcome.OK, display, None, dur)


def _kill_group(proc: asyncio.subprocess.Process) -> None:
    """SIGKILL the child's whole process group.

    The executor's docstring has promised this since G3 and it did not exist.
    `start_new_session=True` above makes the child a session leader, so its pgid
    is its pid: a tool that forks (a shell wrapper, `hyprctl` behind a script)
    leaves the grandchild running forever without this.
    """
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
