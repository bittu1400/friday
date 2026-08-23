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

from . import config
from .errors import Outcome
from .llm import chat, grounding, schema
from .llm.client import LlamaClient, LlamaTimeout, LlamaUnreachable
from .llm.prompt import assemble_system
from .llm.validate import SchemaError, validate
from .store.audit import AuditLog
from .store.prefs import PendingPreference, PrefStore, resolve
from .tools import executor
from .tools.registry import NOT_YET_WIRED, REGISTRY
from .tools.search import SearchClient, SearchResult, SearchUnavailable, sanitize
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
    sources: tuple[SearchResult, ...] = ()


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
        connected=connected,
        history=history,
        habits_digest=habits_digest,
        summaries_digest=summaries_digest,
    )
    if speaker is not None and result.spoken:
        await asyncio.to_thread(speaker.say, result.spoken)
    return result


async def _plan_and_act(
    utterance: str,
    client: LlamaClient,
    *,
    request_id: str,
    dry_run: bool = False,
    prefs: PrefStore | None = None,
    audit: AuditLog | None = None,
    search_client: SearchClient | None = None,
    connected: bool = True,
    history: str = "",
    habits_digest: str = "",
    summaries_digest: str = "",
) -> TurnResult:
    # History is passed to the PLANNER too (ADR-052) so a follow-up command
    # ("open that", "try again") can resolve against the prior turn. It is
    # first-party data (user speech + Friday replies), never web content, so
    # invariant #1 is untouched; the planner stays grammar-locked + validated.
    system = assemble_system(prefs.digest() if prefs else "", history=history)
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
        return TurnResult("none", params, templates.OUT_OF_SCOPE, False)

    if plan.name == "chat":
        # invariant #1 (ADR-008/048) holds structurally: `chat` can only be
        # chosen by the grammar-locked planner (plan.gbnf, trusted input). The
        # untrusted path (grounding, G7) uses final.gbnf, whose name is locked
        # to "none", so an untrusted turn can never emit name=="chat". `chat`
        # NEVER dispatches — no executor call, dispatched=False.
        reply = await asyncio.to_thread(
            chat.generate_reply, client, utterance,
            prefs_digest=(prefs.digest() if prefs else ""), history=history,
            habits_digest=habits_digest,
            summaries_digest=summaries_digest,
        )
        return TurnResult("chat", {}, reply, False)



    if plan.name == "remember_preference":
        return _plan_remember(params)

    if plan.name == "forget_preference":
        return await _do_forget(params, prefs, audit, request_id)

    if plan.name == "web_search":
        return await _do_web_search(
            params.get("query", utterance), client, search_client, connected
        )

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


async def _do_web_search(
    query: str,
    client: LlamaClient,
    search_client: SearchClient | None,
    connected: bool,
) -> TurnResult:
    """Query -> sanitize -> ground. NEVER dispatches (dispatched=False): the
    grounding turn is final.gbnf-locked (invariant #1) and there is no
    subprocess here. `query` is the model's own text, used ONLY as a SearXNG
    query parameter (invariant #2 — not the youtube exception)."""
    if not connected:  # ADR-046: local mode refuses audibly
        return TurnResult("web_search", {"query": query}, templates.SEARCH_LOCAL_MODE, False)
    sc = search_client or SearchClient(
        base_url=config.SEARXNG_URL, timeout_s=config.SEARCH_TIMEOUT_S
    )
    try:
        # SearchClient is sync; keep the turn loop's thread free.
        results = await asyncio.to_thread(sc.query, query)
    except SearchUnavailable:  # E_NET_DOWN — spoken fallback, never a raw exc
        return TurnResult("web_search", {"query": query}, templates.SEARCH_UNAVAILABLE, False)
    bodies, sources = sanitize(
        results,
        max_results=config.SEARCH_MAX_RESULTS,
        max_tokens=config.SEARCH_MAX_TOKENS,
    )
    if not any(bodies):
        return TurnResult(
            "web_search", {"query": query}, templates.SEARCH_NO_RESULTS, False,
            sources=tuple(sources),
        )
    answer = await asyncio.to_thread(grounding.ground, client, query, bodies)
    return TurnResult(
        "web_search", {"query": query}, answer, False, sources=tuple(sources)
    )


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
