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
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

from .errors import E_LLM_DOWN, E_LLM_TIMEOUT, E_SCHEMA, E_TOOL_NOTFOUND, Outcome
from .llm import schema
from .llm.client import LlamaClient, LlamaTimeout, LlamaUnreachable
from .llm.prompt import assemble_system
from .llm.validate import AppNotInstalledError, SchemaError, validate
from .gate import (
    PendingAction,
    TurnResult,
    audit_params,
    _confirm_question,
    _panic_blocked,
)
from .handlers import HANDLERS, TurnContext
from .store.approvals import ApprovalStore
from .store.audit import AuditLog
from .store.prefs import PendingPreference, PrefStore
from .tools import executor
from .tools.registry import REGISTRY
from .tools.search import SearchClient
from .ui import templates

log = logging.getLogger("friday.turn")

_PLAN_GRAMMAR = (Path(schema.__file__).parent / "grammars" / "plan.gbnf").read_text()

async def run_turn(
    utterance: str,
    client: LlamaClient,
    *,
    request_id: str,
    dry_run: bool = False,
    prefs: PrefStore | None = None,
    audit: AuditLog | None = None,
    speaker: "object | None" = None,
    search_client: SearchClient | None = None,
    approvals: ApprovalStore | None = None,
    connected: bool = True,
    history: str = "",
    habits_digest: str = "",
    summaries_digest: str = "",
) -> TurnResult:
    """Plan + act, then voice the outcome (ADR-040). Execute-first is
    preserved: the action runs inside `_plan_and_act`, the template is chosen
    from its outcome, and only then is it spoken."""
    result = await _plan_and_act(
        utterance,
        client,
        request_id=request_id,
        dry_run=dry_run,
        prefs=prefs,
        audit=audit,
        search_client=search_client,
        approvals=approvals,
        connected=connected,
        history=history,
        habits_digest=habits_digest,
        summaries_digest=summaries_digest,
    )
    if speaker is not None and result.spoken:
        await asyncio.to_thread(speaker.say, result.spoken)
    return result


async def _plan(
    utterance: str,
    client: LlamaClient,
    prefs: PrefStore | None,
    *,
    history: str,
):
    """One grammar-locked planning round. Raises the client/schema errors for
    the caller to turn into a spoken template."""
    system = assemble_system(prefs.digest() if prefs else "", history=history)
    raw = await asyncio.to_thread(
        client.complete, system=system, user=utterance, grammar=_PLAN_GRAMMAR
    )
    return validate(raw)  # fail closed on anything malformed


async def _plan_and_act(
    utterance: str,
    client: LlamaClient,
    *,
    request_id: str,
    dry_run: bool = False,
    prefs: PrefStore | None = None,
    audit: AuditLog | None = None,
    search_client: SearchClient | None = None,
    approvals: ApprovalStore | None = None,
    connected: bool = True,
    history: str = "",
    habits_digest: str = "",
    summaries_digest: str = "",
) -> TurnResult:
    # History reaches the PLANNER (ADR-052) so a follow-up command ("open that",
    # "try again") can resolve against the prior turn. It is first-party data
    # (user speech + Friday replies), never web content, so invariant #1 is
    # untouched; the planner stays grammar-locked + validated.
    #
    # ADR-065: but it is asked WITHOUT history FIRST. What the planner returns
    # from the user's words alone is what the user actually said. History may
    # then RESOLVE a command it could not ("open it" -> none -> open_app), and
    # an action that appears ONLY once history is in the prompt is confirmed,
    # never dispatched silently. Without this, Friday's own suggestion becomes
    # its own instruction: measured 2026-08-25, after two turns proposing VS
    # Code and ending "Ready to start coding?", a bare "hey jarvis" dispatched
    # open_app{editor} 4 times out of 4 — a command the user never gave.
    try:
        plan = await _plan(utterance, client, prefs, history="")
        from_history = False
        if plan.name == "none" and history:
            resolved = await _plan(utterance, client, prefs, history=history)
            if resolved.name not in ("none", "chat"):
                plan, from_history = resolved, True
    except AppNotInstalledError as exc:
        log.info("%s: app %r not installed, failing closed to none", E_TOOL_NOTFOUND, exc.app_name)
        return TurnResult("none", {}, f"I couldn't find {exc.app_name} on this system.", False)
    except SchemaError:
        # Log the code, speak the template (spec §4). E_SCHEMA existed in the
        # taxonomy and was written nowhere, so a run of malformed plans left no
        # trace distinguishable from the user saying nothing useful.
        log.info("%s: plan failed validation, failing closed to none", E_SCHEMA)
        return TurnResult("none", {}, "I didn't understand.", False)
    except LlamaTimeout:
        log.info("%s: generation exceeded the budget", E_LLM_TIMEOUT)
        return TurnResult("none", {}, "That took too long.", False)
    except LlamaUnreachable as exc:
        # `LlamaServerError` subclasses this (M-L2): same spoken line, but the
        # log distinguishes "nothing is listening" from "the server answered
        # with a status", which are different things to go fix.
        log.info("%s: %s", E_LLM_DOWN, exc)
        return TurnResult("none", {}, "My brain's offline.", False)

    params = dict(plan.params)
    ctx = TurnContext(
        client=client, request_id=request_id, utterance=utterance, prefs=prefs,
        audit=audit, search_client=search_client, connected=connected,
        dry_run=dry_run, history=history, habits_digest=habits_digest,
        summaries_digest=summaries_digest,
    )

    if from_history:
        spec = REGISTRY.get(plan.name)
        what = spec.display(params) if spec is not None else plan.name
        return TurnResult(
            plan.name, params, templates.confirm_from_history(what), False,
            pending=PendingAction(plan.name, params, what),
        )

    # THE GATE (criterion 3.5). One panic check and one confirm decision for
    # every capability, both derived from `risk`. Everything below this point
    # is a handler, and no handler re-asks either question. `none` and `chat`
    # pass through untouched: they are `Risk.NONE` and declare no `ask`.
    blocked = await _panic_blocked(
        plan.name, audit_params(PendingAction(plan.name, params, "")),
        audit, request_id, time.monotonic(),
    )
    if blocked is not None:
        return TurnResult(plan.name, params, blocked, False)

    gate = _confirm_question(plan.name, params, approvals)
    if gate is not None:
        question, what = gate
        return TurnResult(
            plan.name, params, question, False,
            pending=PendingAction(plan.name, params, what),
        )

    handler = HANDLERS.get(plan.name)
    if handler is not None:
        return await handler(ctx, params)

    # Everything else is a subprocess capability and shares ONE body: execute
    # FIRST, then speak from the outcome template (ADR-009, invariant #4). The
    # spoken line is never the model's — that is how "Opening Firefox" got said
    # about a launch that had already failed.
    spec = REGISTRY.get(plan.name)
    if spec is None:  # defensive: a name in the enum but not wired anywhere
        return TurnResult(plan.name, params, "I can't do that yet.", False)

    result = await executor.execute(spec, params, request_id, dry_run=dry_run)
    spoken = templates.render(result.outcome, result.display, detach=spec.detach)
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


# --- compatibility re-exports ----------------------------------------------
# `friday.turn` is the name every caller and ~30 test files already import
# from. The split is internal (criterion 3.4), so the surface does not move:
# the confirm handshake lives in `gate.py` and the per-capability work in
# `handlers.py`, and both are reachable here under their old names.
from .gate import (  # noqa: E402,F401  (re-export, deliberately at the tail)
    confirm_preference,
    is_affirmation,
    is_decline,
    resolve_pending,
)
from .handlers import (  # noqa: E402,F401
    _do_cancel_reminder,
    _do_create_note,
    _do_forget,
    _do_list_reminders,
    _do_read_notes,
    _do_set_reminder,
    _do_web_search,
    _humanize_duration,
    _parse_reminder_seconds,
    _plan_remember,
)
