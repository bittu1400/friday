"""G2 eval harness — fixture -> prompt -> llama-server -> validator -> compare.

Prints three numbers (ADR-030):

    passed / total     the rate on the CURRENT gated set. Gate (at G3) is
                       >= 90%, min 20 fixtures. Any number is fine at G2.
    known-failing      fixtures flagged known_failing:true — a TODO list,
                       excluded from the rate, never a build failure.
    regressions        fixtures that passed in the last recorded baseline
                       and fail now. THIS is the only number that can block.

Scoring (decided 2026-08-23):
    action name        must match exactly
    enum params        exact match after NFKC (the app enum)
    text params        normalized case-insensitive containment: the
                       expected substring must appear in the model's value
                       (tolerates phrasing, still catches wrong extraction)
    no params in expect  only the name is checked

Run:
    uv run python -m friday.eval_harness
    uv run python -m friday.eval_harness --update-baseline
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .llm import schema
from .llm.client import LlamaClient, LlamaTimeout, LlamaUnreachable
from .llm.prompt import SYSTEM_POLICY
from .llm.validate import Plan, SchemaError, validate

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures" / "eval.jsonl"
BASELINE = Path(__file__).parent.parent / "tests" / "fixtures" / "baseline.json"


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).casefold().strip()


def _param_kind(action: str, key: str) -> str:
    return schema.PARAM_SCHEMA[action][key]["kind"]


def _matches(expect: dict[str, Any], plan: Plan) -> bool:
    if plan.name != expect["name"]:
        return False
    exp_params = expect.get("params")
    if not exp_params:
        return True
    for key, exp_val in exp_params.items():
        act_val = plan.params.get(key)
        if act_val is None:
            return False
        if _param_kind(expect["name"], key) == "enum":
            if unicodedata.normalize("NFKC", act_val) != unicodedata.normalize(
                "NFKC", exp_val
            ):
                return False
        else:  # text: lenient containment
            if _norm(exp_val) not in _norm(act_val):
                return False
    return True


def _load_fixtures() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in FIXTURES.read_text().splitlines()
        if line.strip()
    ]


def _revision() -> str:
    return hashlib.sha1(FIXTURES.read_bytes()).hexdigest()[:12]


@dataclass
class Result:
    fid: str
    passed: bool
    known_failing: bool
    predicted: str


def run(client: LlamaClient) -> list[Result]:
    grammar = (Path(schema.__file__).parent / "grammars" / "plan.gbnf").read_text()

    results: list[Result] = []
    for fx in _load_fixtures():
        known = bool(fx.get("known_failing"))
        try:
            raw = client.complete(
                system=SYSTEM_POLICY, user=fx["utt"], grammar=grammar
            )
            plan = validate(raw)
            predicted = plan.name + (
                f" {dict(plan.params)}" if plan.params else ""
            )
            ok = _matches(fx["expect"], plan)
        except SchemaError as exc:
            predicted, ok = f"<invalid: {exc}>", False
        results.append(Result(fx["id"], ok, known, predicted))
    return results


def _report(results: list[Result]) -> int:
    gated = [r for r in results if not r.known_failing]
    passed = sum(r.passed for r in gated)
    total = len(gated)
    known = [r for r in results if r.known_failing]

    base = json.loads(BASELINE.read_text()) if BASELINE.exists() else None
    regressions: list[str] = []
    if base:
        prev = base.get("results", {})
        regressions = [
            r.fid for r in results if prev.get(r.fid) and not r.passed
        ]

    print(f"fixture-set revision: {_revision()}")
    print(f"passed {passed}/{total}  ({100 * passed // total if total else 0}%)")
    print(f"known-failing: {len(known)}")
    print(
        f"regressions vs baseline: {len(regressions)}"
        + (f" {regressions}" if regressions else "")
        + ("" if base else "  (no baseline recorded yet)")
    )
    for r in results:
        if not r.passed:
            flag = "known-failing" if r.known_failing else "FAIL"
            print(f"  [{flag}] {r.fid}: got {r.predicted}")
    return len(regressions)


def _write_baseline(results: list[Result]) -> None:
    BASELINE.write_text(
        json.dumps(
            {
                "revision": _revision(),
                "results": {r.fid: r.passed for r in results},
            },
            indent=2,
        )
        + "\n"
    )
    print(f"\nbaseline written to {BASELINE} at revision {_revision()}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--base-url", default="http://127.0.0.1:8080")
    args = ap.parse_args(argv)

    client = LlamaClient(base_url=args.base_url)
    if not client.health():
        print(f"llama-server not reachable at {args.base_url} — start it first")
        return 2

    try:
        results = run(client)
        regressions = _report(results)
        if args.update_baseline:
            _write_baseline(results)
        return 1 if regressions else 0
    except (LlamaUnreachable, LlamaTimeout) as exc:
        print(f"llama-server error: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
