"""The eval gate must be able to FAIL — M6.

`just eval` is the contract every model swap and every refactor is judged by,
and on 2026-09-03 all four of its exit-condition mutations survived the full
suite: the gate could be made to always exit 0, regression detection could be
switched off, a failing newly-added fixture could stop counting, and the >=90%
floor could be removed. Nothing touched `_report`'s return value.

The third of those is F23's exact shape — fixed in code, pinned by nothing.

Each test isolates ONE branch: the rate stays at or above 90% wherever the
regression or unbaselined branch is the subject, so only that branch can be
what returns 1.
"""

from __future__ import annotations

import json

import pytest

from friday import eval_harness
from friday.eval_harness import Result, _report


def _results(n_pass: int, n_fail: int = 0, *, known_failing: int = 0) -> list[Result]:
    out = [Result(f"P{i}", True, False, "ok") for i in range(n_pass)]
    out += [Result(f"F{i}", False, False, "wrong") for i in range(n_fail)]
    out += [Result(f"K{i}", False, True, "wrong") for i in range(known_failing)]
    return out


@pytest.fixture
def baseline(tmp_path, monkeypatch):
    """Write a baseline mapping fid -> passed, and point the harness at it."""

    path = tmp_path / "baseline.json"
    monkeypatch.setattr(eval_harness, "BASELINE", path)

    def write(mapping: dict[str, bool]) -> None:
        path.write_text(json.dumps({"revision": "test", "results": mapping}))

    return write


def test_clean_run_exits_zero(baseline):
    baseline({f"P{i}": True for i in range(20)})
    assert _report(_results(20)) == 0


def test_a_regression_fails_the_gate(baseline):
    """One of 20 regresses: 95% passes the floor, so ONLY the regression blocks."""

    baseline({f"P{i}": True for i in range(19)} | {"F0": True})
    assert _report(_results(19, 1)) == 1


def test_a_failing_new_fixture_fails_the_gate(baseline):
    """F23: `F0` has no baseline entry, so it can never be a *regression*."""

    baseline({f"P{i}": True for i in range(19)})
    assert _report(_results(19, 1)) == 1


def test_the_90_percent_floor_fails_the_gate(baseline):
    """Both failures were already failing, so neither branch above fires."""

    baseline({f"P{i}": True for i in range(8)} | {"F0": False, "F1": False})
    assert _report(_results(8, 2)) == 1


def test_known_failing_neither_counts_nor_blocks(baseline):
    """A known-failing fixture is a TODO list, never a build failure (ADR-030)."""

    baseline({f"P{i}": True for i in range(10)})
    assert _report(_results(10, known_failing=5)) == 0


def test_no_baseline_still_gates_on_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(eval_harness, "BASELINE", tmp_path / "missing.json")
    assert _report(_results(20)) == 0
    assert _report(_results(19, 1)) == 1
