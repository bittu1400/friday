"""One turn: utterance -> plan -> (dispatch) -> spoken outcome.

This is the G3 slice of the turn loop. It is deliberately small: no audio,
no persistence, no conversation ring. It enforces the invariants that
matter at G3:

  - fail closed: any planning/validation failure becomes action=none, and
    none never dispatches (FR-25)
  - execute FIRST, then speak from a template (ADR-009, FR-40) — the model's
    words never announce an action
  - the planning turn consumes no untrusted data at G3, so it uses plan.gbnf

The conversational reply for `none` (actually answering a chit-chat
question) needs a second, unconstrained generation and is out of G3 scope;
here `none` yields a short canned line.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from . import config
from .errors import Outcome
from .llm import schema
from .llm.client import LlamaClient, LlamaTimeout, LlamaUnreachable
from .llm.prompt import SYSTEM_POLICY
from .llm.validate import SchemaError, validate
from .tools import executor
from .tools.registry import NOT_YET_WIRED, REGISTRY
from .ui import templates

_PLAN_GRAMMAR = (Path(schema.__file__).parent / "grammars" / "plan.gbnf").read_text()


@dataclass(frozen=True)
class TurnResult:
    plan_name: str
    params: dict[str, str]
    spoken: str
    dispatched: bool


async def run_turn(
    utterance: str,
    client: LlamaClient,
    *,
    request_id: str,
    dry_run: bool = False,
) -> TurnResult:
    # Plan. The blocking stdlib client call is pushed off the event loop.
    try:
        raw = await asyncio.to_thread(
            client.complete,
            system=SYSTEM_POLICY,
            user=utterance,
            grammar=_PLAN_GRAMMAR,
        )
        plan = validate(raw)  # fail closed on anything malformed
    except SchemaError:
        return TurnResult("none", {}, "I didn't understand.", False)
    except LlamaTimeout:
        return TurnResult("none", {}, "That took too long.", False)
    except LlamaUnreachable:
        return TurnResult("none", {}, "My brain's offline.", False)

    params = dict(plan.params)

    if plan.name == "none":
        return TurnResult("none", params, "(no action)", False)

    if plan.name in NOT_YET_WIRED:
        return TurnResult(
            plan.name, params, f"[planned {plan.name} — {NOT_YET_WIRED[plan.name]}]", False
        )

    spec = REGISTRY.get(plan.name)
    if spec is None:  # defensive: a name in the enum but not wired anywhere
        return TurnResult(plan.name, params, "I can't do that yet.", False)

    # Execute FIRST, then speak (ADR-009).
    result = await executor.execute(spec, params, request_id, dry_run=dry_run)
    spoken = templates.render(result.outcome, result.display)
    dispatched = result.outcome not in (Outcome.DENIED, Outcome.DISABLED, Outcome.NOT_FOUND)
    return TurnResult(plan.name, params, spoken, dispatched)
