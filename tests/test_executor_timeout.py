"""`ToolSpec.timeout_s` was dead config, and the executor's docstring lied
about a process-group kill that did not exist (audit M-T1, ADR-067d).

Every tool got the 0.4 s fire-and-forget launch grace and was then reported OK
whatever it did — right for a GUI app that must outlive the turn (ADR-043),
wrong for the six G12 command tools, where the exit code IS the verdict and a
hung `nmcli` should not be announced as a Wi-Fi change.
"""

import asyncio
import os
import signal
import sys
import time

import pytest

from friday.errors import Outcome
from friday.tools import executor
from friday.tools.registry import ToolSpec

_ENV = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/tmp")}


def _spec(argv: list[str], *, binary: str, timeout_s: float, detach: bool) -> ToolSpec:
    return ToolSpec(
        tool_id="probe",
        risk="reversible",
        build_argv=lambda p: list(argv),
        target_binary=lambda p: binary,
        display=lambda p: "probe",
        cwd="/tmp",
        env=_ENV,
        timeout_s=timeout_s,
        detach=detach,
    )


def _run(spec: ToolSpec):
    return asyncio.run(executor.execute(spec, {}, "t1"))


def test_a_hung_command_times_out_instead_of_being_announced_as_done():
    spec = _spec(["sleep", "30"], binary="sleep", timeout_s=0.3, detach=False)
    started = time.monotonic()
    res = _run(spec)
    assert res.outcome is Outcome.TIMEOUT
    assert res.code == "E_TOOL_TIMEOUT"
    assert time.monotonic() - started < 5.0, "it waited for the full sleep"


def test_the_whole_process_group_is_killed_on_timeout(tmp_path):
    """The docstring has claimed this since G3. It was not true until now:
    a child that forks leaves the grandchild running forever.

    The forking child is a python script, not `sh -c`: every shell is on the
    permanent ban list (invariant #10) and so is `>`, so the executor refuses
    the obvious version of this test outright — which is the ban working.
    """
    marker = tmp_path / "grandchild.pid"
    script = tmp_path / "forker.py"
    script.write_text(
        "import subprocess, time\n"
        "p = subprocess.Popen(['sleep', '30'])\n"
        f"open({str(marker)!r}, 'w').write(str(p.pid))\n"
        "time.sleep(30)\n"
    )
    spec = _spec(
        [sys.executable, str(script)],
        binary=sys.executable,
        timeout_s=1.0,
        detach=False,
    )
    res = _run(spec)
    assert res.outcome is Outcome.TIMEOUT

    pid = int(marker.read_text().strip())
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            return  # the grandchild died with the group
        time.sleep(0.05)
    os.kill(pid, signal.SIGKILL)  # don't leak it out of the test
    pytest.fail("the grandchild survived the timeout — no process-group kill")


def test_a_failing_command_is_not_reported_as_success():
    spec = _spec(["false"], binary="false", timeout_s=2.0, detach=False)
    res = _run(spec)
    assert res.outcome is Outcome.ERROR
    assert res.code == "E_TOOL_FAILED"


def test_a_succeeding_command_is_ok():
    spec = _spec(["true"], binary="true", timeout_s=2.0, detach=False)
    assert _run(spec).outcome is Outcome.OK


def test_a_gui_launch_still_reports_ok_on_a_nonzero_exit():
    """ADR-043 regression guard. Brave's single-instance handoff exits non-zero
    ON SUCCESS; treating that as failure is the defect ADR-043 exists to stop.
    Exit codes are a verdict for commands, never for launches."""
    spec = _spec(["false"], binary="false", timeout_s=2.0, detach=True)
    assert _run(spec).outcome is Outcome.OK


def test_a_gui_launch_is_not_bounded_by_timeout_s():
    """A GUI app is supposed to outlive the turn — it must not be killed at
    timeout_s, and the turn must not wait for it either."""
    spec = _spec(["sleep", "30"], binary="sleep", timeout_s=0.5, detach=True)
    started = time.monotonic()
    res = _run(spec)
    elapsed = time.monotonic() - started
    assert res.outcome is Outcome.OK
    assert elapsed < 2.0, "the launch waited for the app to exit"
    os.system("pkill -f 'sleep 30' >/dev/null 2>&1")  # the app really did survive


def test_every_registry_tool_declares_which_kind_it_is():
    from friday.tools.registry import REGISTRY

    launches = {"open_app", "open_youtube", "youtube_search", "file_open"}
    for name, spec in REGISTRY.items():
        assert spec.detach is (name in launches), f"{name} has the wrong launch kind"
