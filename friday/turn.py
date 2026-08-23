"""One turn: utterance -> plan -> (dispatch) -> spoken outcome.

G4 adds persistence to the G3 slice:

  - the planning prompt now carries the `<preferences>` digest as DATA
    (assemble_system); eval, which has no prefs, still sees SYSTEM_POLICY
    unchanged
  - `remember_preference` does NOT write on the spot (ADR-037): it resolves
    the canonical key+value and returns a `pending` preference; the UI
    confirms, then `confirm_preference()` performs the write
  - `forget_preference` soft-expires immediately (ADR-036) — safe on a
    mishear, recoverable — and speaks a template
  - every real dispatch (and the confirm write) records one audit row (FR-58)

Still enforced: fail closed to none (FR-25); execute FIRST, then speak from
a template (ADR-009); one turn in flight; the planning turn consumes no
untrusted data at G4, so it uses plan.gbnf.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from .errors import Outcome
from .llm import schema
from .llm.client import LlamaClient, LlamaTimeout, LlamaUnreachable
from .llm.prompt import assemble_system
from .llm.validate import SchemaError, validate
from .store.audit import AuditLog
from .store.prefs import PendingPreference, PrefStore, resolve
from .tools import executor
from .tools.registry import NOT_YET_WIRED, REGISTRY
from .ui import templates

_PLAN_GRAMMAR = (Path(schema.__file__).parent / "grammars" / "plan.gbnf").read_text()

# Deterministic confirm handshake (ADR-037): no second model turn, so no
# injection surface and "one turn in flight" holds. Anything not an explicit
# yes cancels — fail safe, no write.
_AFFIRM = frozenset(
    {"yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay", "correct", "do it"}
)


def is_affirmation(text: str) -> bool:
    return text.strip().casefold() in _AFFIRM


@dataclass(frozen=True)
class TurnResult:
    plan_name: str
    params: dict[str, str]
    spoken: str
    dispatched: bool
    pending: PendingPreference | None = None


async def run_turn(
    utterance: str,
    client: LlamaClient,
    *,
    request_id: str,
    dry_run: bool = False,
    prefs: PrefStore | None = None,
    audit: AuditLog | None = None,
) -> TurnResult:
    system = assemble_system(prefs.digest() if prefs else "")
    try:
        raw = await asyncio.to_thread(
            client.complete, system=system, user=utterance, grammar=_PLAN_GRAMMAR
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

    if plan.name == "remember_preference":
        return _plan_remember(params)

    if plan.name == "forget_preference":
        return await _do_forget(params, prefs, audit, request_id)

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
    if audit is not None:
        await audit.arecord(
            request_id=request_id,
            tool_id=plan.name,
            params=params,
            policy_decision="allowed" if dispatched else result.outcome.value,
            outcome=result.outcome.value,
            duration_ms=result.duration_ms,
        )
    return TurnResult(plan.name, params, spoken, dispatched)


def _plan_remember(params: dict[str, str]) -> TurnResult:
    """Resolve the preference and hand back a pending confirmation. No write
    (ADR-037). Resolution is pure, so this needs no store."""
    try:
        pending = resolve(params["key"], params["value"])
    except (SchemaError, KeyError):
        return TurnResult("remember_preference", params, "I didn't understand.", False)
    spoken = templates.confirm_preference(pending.key, pending.value)
    return TurnResult("remember_preference", params, spoken, False, pending=pending)


async def confirm_preference(
    pending: PendingPreference,
    prefs: PrefStore | None,
    audit: AuditLog | None,
    *,
    request_id: str,
) -> str:
    """Execute the confirmed write, THEN return the spoken line (ADR-009)."""
    if prefs is None:
        return templates.MEMORY_UNAVAILABLE
    await asyncio.to_thread(prefs.put, pending)
    if audit is not None:
        await audit.arecord(
            request_id=request_id,
            tool_id="remember_preference",
            params={"key": pending.key},  # value is user data — key only
            policy_decision="allowed",
            outcome="ok",
            duration_ms=0,
        )
    return templates.remembered(pending.key, pending.value)


async def _do_forget(
    params: dict[str, str],
    prefs: PrefStore | None,
    audit: AuditLog | None,
    request_id: str,
) -> TurnResult:
    if prefs is None:
        return TurnResult("forget_preference", params, templates.MEMORY_UNAVAILABLE, False)
    try:
        key = params["key"]
    except KeyError:
        return TurnResult("forget_preference", params, "I didn't understand.", False)
    # Soft-expire (ADR-036): safe on a mishear, recoverable.
    n = await asyncio.to_thread(prefs.forget_soft, key)
    from .store.prefs import canonical_key

    ck = canonical_key(key)
    spoken = templates.forgotten(ck) if n else templates.forget_unknown(ck)
    if audit is not None:
        await audit.arecord(
            request_id=request_id,
            tool_id="forget_preference",
            params={"key": ck},
            policy_decision="allowed",
            outcome="ok" if n else "not_found",
            duration_ms=0,
        )
    return TurnResult("forget_preference", params, spoken, bool(n))
