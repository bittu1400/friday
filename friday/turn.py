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

from . import config
from .capabilities import CAPABILITIES, Risk
from .errors import E_LLM_DOWN, E_LLM_TIMEOUT, E_SCHEMA, E_TOOL_NOTFOUND, Outcome
from .llm import chat, grounding, schema
from .llm.client import LlamaClient, LlamaTimeout, LlamaUnreachable
from .llm.prompt import assemble_system
from .llm.validate import AppNotInstalledError, SchemaError, validate
from .store.approvals import ApprovalStore, fingerprint
from .store.audit import AuditLog
from .store.prefs import PendingPreference, PrefStore, resolve
from .tools import executor
from .tools.apps import APPS
from .tools.registry import REGISTRY
from .tools.search import SearchClient, SearchResult, SearchUnavailable, sanitize
from .ui import templates

log = logging.getLogger("friday.turn")

_PLAN_GRAMMAR = (Path(schema.__file__).parent / "grammars" / "plan.gbnf").read_text()

# Deterministic confirm handshake (ADR-037): no second model turn, so no
# injection surface and "one turn in flight" holds. A pending is only ever
# executed on an explicit affirmative — fail safe, no write.
#
# The set is WIDER than the ten bare tokens it started as (ADR-075b). The user
# was shown the tradeoff — every added phrase is one more way to approve a
# destructive action by accident — and chose to widen, because the natural
# spoken answer to "Are you sure?" is rarely the word "yes" alone.
_AFFIRM = frozenset(
    {
        "yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay", "correct",
        "do it", "go ahead", "please do", "confirm", "yes please",
        "yeah do it", "do it please", "affirmative", "go for it",
    }
)
# An EXPLICIT no is answered ("Okay, cancelled."). Anything that is neither
# cancels the pending and is then re-routed as a fresh command (ADR-075c), so
# the two sets have to be told apart — they are not each other's complement.
_DECLINE = frozenset(
    {
        "no", "n", "nope", "nah", "negative", "cancel", "stop", "don't",
        "dont", "do not", "never mind", "nevermind", "forget it", "no thanks",
        "no thank you",
    }
)
# Whisper punctuates EVERY utterance. Matching bare tokens meant `"Yes."` was
# not an affirmation, so every spoken confirm in Phase 2 declined while every
# typed one passed (D1, ADR-075a). The one character never in a fixture was
# the full stop.
# Inner punctuation matters too: Whisper writes "Yeah, do it." with a comma.
# The apostrophe is deliberately NOT stripped — it would turn "don't" into
# "don t" — only normalised from the curly form STT prefers.
_SPOKEN_PUNCT = re.compile("[.,!?;:\u2026\"\u201c\u201d-]")


def _normalise(text: str) -> str:
    """Casefold and drop the punctuation STT sprinkles through a spoken answer,
    collapsing what is left to single spaces so the set lookup stays exact."""
    return " ".join(_SPOKEN_PUNCT.sub(" ", text.casefold().replace("\u2019", "'")).split())


# Heads that may LEAD a longer answer (D25, ADR-091). Whole-string matching
# fixed `"Yes."` but not `"Yes, I am sure"` — which is what a user actually
# says to "Are you sure?", and which ADR-075c then treated as a non-answer,
# cancelling a `system_wifi{off}` the user had just emphatically approved.
# Observed live 2026-08-30 (audit: two `declined` rows, Wi-Fi still enabled).
#
# Deliberately NOT every member of _AFFIRM: "do" and "go" are excluded because
# "do not" and "go back" lead with them. Those phrases still match exactly.
_AFFIRM_HEADS = frozenset(
    {"yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay", "correct",
     "confirm", "affirmative"}
)
_DECLINE_HEADS = frozenset({"no", "n", "nope", "nah", "negative", "cancel", "stop"})
# A single negative word anywhere VETOES a leading yes. This gate approves
# destructive actions, so "yes, but not now" and "yeah actually cancel that"
# must not read as approval — they fall through to ADR-075c, which cancels the
# pending and re-runs the words as a command. Ambiguity resolves to not-acting.
_NEGATIVE_WORDS = frozenset(
    {"no", "not", "nope", "nah", "negative", "cancel", "stop", "don't", "dont",
     "never", "nevermind", "forget"}
)


def is_affirmation(text: str) -> bool:
    norm = _normalise(text)
    if norm in _AFFIRM:
        return True
    words = norm.split()
    if not words or words[0] not in _AFFIRM_HEADS:
        return False
    return not _NEGATIVE_WORDS.intersection(words)


def is_decline(text: str) -> bool:
    """An explicit refusal. NOT `not is_affirmation(...)` — see `_DECLINE`.

    Head-matching needs no veto here: declining is the fail-safe direction, so
    reading "no problem, go ahead" as a refusal costs one repeated question,
    while the reverse mistake dispatches something irreversible."""
    norm = _normalise(text)
    if norm in _DECLINE:
        return True
    words = norm.split()
    return bool(words) and words[0] in _DECLINE_HEADS


@dataclass(frozen=True)
class PendingAction:
    tool_id: str
    params: dict[str, str]
    description: str


@dataclass(frozen=True)
class TurnResult:
    plan_name: str
    params: dict[str, str]
    spoken: str
    dispatched: bool
    pending: PendingPreference | PendingAction | None = None
    sources: tuple[SearchResult, ...] = ()



# --- the derived gate (Phase 3, criterion 3.5; design §3.1/§3.2) ------------
#
# One place decides, for every capability, whether the panic switch blocks it
# and whether it must be confirmed. Both answers come from `risk`, so a new
# capability cannot be added without one — which is what the five hand-coded
# `if plan.name == ...` confirm branches and the eight hand-written
# `config.is_disabled()` blocks that used to live in this file could not
# guarantee. Three of those five confirms were deletable in silence with the
# whole suite green (M1), and the panic switch guarded one of eleven
# side-effecting paths when Phase 1 found it (F1).


async def _panic_blocked(
    tool_id: str,
    params: dict[str, str],
    audit: AuditLog | None,
    request_id: str,
    t0: float,
) -> str | None:
    """The spoken line if the panic switch is engaged, else None.

    Every tier above NONE is blocked, including the FIRST_USE approval write —
    a switch that stops the launch but records the grant would come back on to
    a machine that has quietly agreed to things (design §3.2). Read-only
    capabilities (`Risk.NONE`) are not blocked: `read_notes` and
    `list_reminders` change nothing, and refusing to read back what the user
    already stored is not what "switched off" means.
    """
    if not config.is_disabled():
        return None
    if audit is not None:
        await audit.arecord(
            request_id=request_id,
            tool_id=tool_id,
            params=params,
            policy_decision="disabled",
            outcome="disabled",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
    return templates.render(Outcome.DISABLED, "")


def _confirm_question(
    tool_id: str,
    params: dict[str, str],
    approvals: ApprovalStore | None,
) -> tuple[str, str] | None:
    """`(question, description)` if this invocation must be confirmed.

    The tier is `risk_for(params)`, so a gate conditional on a param value —
    Wi-Fi only when off, a window only on close, an app only for a Settings
    panel — is expressed in the record rather than in an `if` here.

    FIRST_USE asks once per subject and remembers the answer keyed to the
    argv's fingerprint. With no store it degrades to asking EVERY time, which
    is the safe direction: an approval that cannot be recorded must not be
    assumed.
    """
    cap = CAPABILITIES.get(tool_id)
    if cap is None or cap.ask is None:
        return None
    tier = cap.risk_for(params)
    if tier in (Risk.NONE, Risk.LOW):
        return None
    question, what = cap.ask(params), cap.describe(params)  # type: ignore[misc]
    if tier is Risk.FIRST_USE:
        if approvals is not None and cap.subject is not None:
            kind, subject, argv = cap.subject(params)
            if approvals.is_approved(kind, subject, fingerprint(argv)):
                return None
        return f"{question} I'll remember.", what
    return question, what


async def _record_approval(
    pending: "PendingAction", approvals: ApprovalStore | None
) -> None:
    """Write the grant a completed FIRST_USE handshake earned.

    Called only from `resolve_pending`, only after an explicit affirmation, and
    only once the panic gate has passed — so no planner output and no disabled
    machine can create a row (design §3.3).
    """
    cap = CAPABILITIES.get(pending.tool_id)
    if approvals is None or cap is None or cap.subject is None:
        return
    if cap.risk_for(pending.params) is not Risk.FIRST_USE:
        return
    kind, subject, argv = cap.subject(pending.params)
    await approvals.aapprove(kind, subject, fingerprint(argv))


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

    if from_history:
        spec = REGISTRY.get(plan.name)
        what = spec.display(params) if spec is not None else plan.name
        return TurnResult(
            plan.name, params, templates.confirm_from_history(what), False,
            pending=PendingAction(plan.name, params, what),
        )

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



    # THE GATE (criterion 3.5). One panic check and one confirm decision for
    # every capability, both derived from `risk`. Everything below this point
    # is a handler, and no handler re-asks either question.
    t0 = time.monotonic()
    blocked = await _panic_blocked(
        plan.name, audit_params(PendingAction(plan.name, params, "")),
        audit, request_id, t0,
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

    if plan.name == "remember_preference":
        return _plan_remember(params)

    if plan.name == "forget_preference":
        return await _do_forget(params, prefs, audit, request_id)

    if plan.name == "set_reminder":
        return await _do_set_reminder(params, prefs, audit, request_id)

    if plan.name == "list_reminders":
        return await _do_list_reminders(prefs)

    if plan.name == "cancel_reminder":
        return await _do_cancel_reminder(params, prefs, audit, request_id)

    if plan.name == "set_dnd":
        return TurnResult("set_dnd", {}, "Quiet mode enabled. Let me know when you need me.", False)

    if plan.name == "resume_dnd":
        return TurnResult("resume_dnd", {}, "Quiet mode disabled. How can I help?", False)

    if plan.name == "create_note":
        return await _do_create_note(params, prefs, audit, request_id)

    if plan.name == "read_notes":
        return await _do_read_notes(prefs)

    if plan.name == "dictation_mode":
        act = params.get("action", "start").lower()
        spoken = "Dictation mode enabled." if act == "start" else "Dictation mode disabled."
        return TurnResult("dictation_mode", params, spoken, False)

    if plan.name == "web_search":
        return await _do_web_search(
            params.get("query", utterance), client, search_client, connected,
            audit=audit, request_id=request_id,
        )

    spec = REGISTRY.get(plan.name)
    if spec is None:  # defensive: a name in the enum but not wired anywhere
        return TurnResult(plan.name, params, "I can't do that yet.", False)

    # Execute FIRST, then speak (ADR-009).
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


async def _do_web_search(
    query: str,
    client: LlamaClient,
    search_client: SearchClient | None,
    connected: bool,
    *,
    audit: AuditLog | None = None,
    request_id: str = "",
) -> TurnResult:
    """Query -> sanitize -> ground. NEVER dispatches (dispatched=False): the
    grounding turn is final.gbnf-locked (invariant #1) and there is no
    subprocess here. `query` is the model's own text, used ONLY as a SearXNG
    query parameter (invariant #2 — not the youtube exception).

    Every outcome writes ONE audit row (FR-58 as amended by ADR-067b). A search
    is the one action that reaches off this machine, and it was the only action
    class writing no row at all (H1) — which also left
    `habits.describe_action`'s `web_search` branch permanently unreachable,
    since it mines the very table nothing was writing to. The query is the
    model's text, so it is length-capped before it is stored; `redact_args`
    then strips home paths as it does for every other row."""
    # Capped, not redacted-away: the query IS the useful audit content, and it
    # is already model-generated text over a first-party utterance.
    q_audited = {"query": query[:80]}
    t0 = time.monotonic()

    async def _row(outcome: str, policy_decision: str = "allowed") -> None:
        if audit is not None:
            dur_ms = int((time.monotonic() - t0) * 1000)
            await audit.arecord(
                request_id=request_id, tool_id="web_search", params=q_audited,
                policy_decision=policy_decision, outcome=outcome, duration_ms=dur_ms,
            )

    if not connected:  # ADR-046: local mode refuses audibly
        await _row("disabled")
        return TurnResult("web_search", {"query": query}, templates.SEARCH_LOCAL_MODE, False)
    sc = search_client or SearchClient(
        base_url=config.SEARXNG_URL, timeout_s=config.SEARCH_TIMEOUT_S
    )
    try:
        # SearchClient is sync; keep the turn loop's thread free.
        results = await asyncio.to_thread(sc.query, query)
    except SearchUnavailable:  # E_NET_DOWN — spoken fallback, never a raw exc
        await _row("net_down")
        return TurnResult("web_search", {"query": query}, templates.SEARCH_UNAVAILABLE, False)
    bodies, sources = sanitize(
        results,
        max_results=config.SEARCH_MAX_RESULTS,
        max_tokens=config.SEARCH_MAX_TOKENS,
    )
    if not any(bodies):
        await _row("not_found")
        return TurnResult(
            "web_search", {"query": query}, templates.SEARCH_NO_RESULTS, False,
            sources=tuple(sources),
        )
    answer = await asyncio.to_thread(grounding.ground, client, query, bodies)
    await _row("ok")
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
    t0 = time.monotonic()
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
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
    return templates.remembered(pending.key, pending.value)


async def resolve_pending(
    pending: PendingPreference | PendingAction | None,
    answer: str,
    *,
    prefs: PrefStore | None,
    audit: AuditLog | None,
    request_id: str,
    dry_run: bool = False,
    approvals: ApprovalStore | None = None,
) -> str | None:
    """Resolve a held confirm against the user's answer (G12, ADR-057/069).

    Shared by the voice daemon and the TUI. Before this helper existed the TUI
    still assumed `pending` was always a `PendingPreference` and called
    `confirm_preference` unconditionally, so every G12 `PendingAction` confirm
    ("Are you sure you want to overwrite your clipboard?") raised
    AttributeError on `pending.key` and did nothing at all. The voice path had
    been migrated; the text path never was. One resolver, one behaviour.

    Deterministic (ADR-037): no second model turn, so no injection surface and
    one-turn-in-flight holds. Nothing but an explicit affirmation executes —
    fail safe. Execute FIRST, then speak (ADR-009): every branch returns the
    line only after the side effect has actually happened.
    """
    if pending is None:  # defensive: nothing was held
        return templates.CANCELLED_ACTION

    if isinstance(pending, PendingPreference):
        if is_affirmation(answer):
            blocked = await _panic_blocked(
                "remember_preference", audit_params(pending), audit, request_id,
                time.monotonic(),
            )
            if blocked is not None:
                return blocked
            return await confirm_preference(pending, prefs, audit, request_id=request_id)
        await _audit_declined(audit, request_id, "remember_preference", pending)
        # Live 2026-08-29: "Open a terminal" was swallowed by a preference
        # confirm and the terminal never opened. A non-answer still cancels —
        # it just no longer eats the command (ADR-075c).
        return templates.cancelled_preference() if is_decline(answer) else None

    if not is_affirmation(answer):
        # ADR-072 (OQ-37): a decline is NOT a dispatch, and it still gets a row.
        # "Friday proposed turning off Wi-Fi and I said no" is the more
        # interesting half of that exchange, and it was invisible to every
        # later read. `outcome='declined'` keeps it out of `mine_habits`, which
        # filters on `outcome='ok'` — a refusal must never become a habit.
        await _audit_declined(audit, request_id, pending.tool_id, pending)
        return templates.CANCELLED_ACTION if is_decline(answer) else None

    # The same derived gate the planning path uses, on the other side of the
    # handshake: a confirm that was armed before the switch was thrown must
    # not dispatch, and — design §3.2 — must not record the FIRST_USE grant
    # either. A machine that comes back on having quietly agreed to things is
    # worse than one that asks twice.
    blocked = await _panic_blocked(
        pending.tool_id, audit_params(pending), audit, request_id, time.monotonic()
    )
    if blocked is not None:
        return blocked

    # An explicit yes to a FIRST_USE question is the ONLY thing that writes an
    # approval. It is recorded before the dispatch, so a launch that fails
    # still counts as answered — the user said yes to the application, not to
    # its exit code.
    await _record_approval(pending, approvals)

    # Every branch below EXECUTES, so every branch below audits (FR-58). These
    # are the dangerous dispatches — wifi off, close the window, overwrite the
    # clipboard, read a secret aloud — and until now they were the only ones
    # that wrote NO audit row at all (H1). The audit existed for exactly these.
    if pending.tool_id == "clipboard_set":
        # Not a subprocess-registry tool: text goes to wl-copy on STDIN (see
        # tools/clipboard.py). Speak the real outcome — never a blanket "done".
        t0 = time.monotonic()
        from .tools.clipboard import set_clipboard

        ok = await asyncio.to_thread(set_clipboard, pending.params.get("text", ""))
        # `audit_params` decides what may be recorded — here, the text's LENGTH
        # and never its content (FR-26/FR-57). Same function the declined path
        # uses, so the two cannot state the rule differently.
        await _audit_confirmed(
            audit, request_id, "clipboard_set", audit_params(pending),
            "ok" if ok else "error",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
        return "Copied to your clipboard." if ok else "Clipboard unavailable."

    if pending.tool_id == "clipboard_read":
        # ADR-068a: read only now, on an explicit yes — a declined confirm must
        # not so much as fetch the selection, let alone voice it.
        t0 = time.monotonic()
        from .tools.clipboard import read_clipboard

        raw = await asyncio.to_thread(read_clipboard)
        outcome = "not_found" if raw is None else ("ok" if raw.split() else "empty")
        # Contents are never audited — the row records that a read-aloud was
        # confirmed and happened, which is the fact worth keeping.
        await _audit_confirmed(
            audit, request_id, "clipboard_read", audit_params(pending), outcome,
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
        if raw is None:
            return "Clipboard unavailable."
        txt = " ".join(raw.split())
        if not txt:
            return "Your clipboard is empty."
        return f"Clipboard contains: {txt[:100]}"

    spec = REGISTRY.get(pending.tool_id)
    if spec is None:
        log.warning("confirm resolved unknown pending tool %s", pending.tool_id)
        return templates.ACTION_UNAVAILABLE
    res = await executor.execute(spec, pending.params, request_id, dry_run=dry_run)
    dispatched = res.outcome not in (Outcome.DENIED, Outcome.DISABLED, Outcome.NOT_FOUND)
    await _audit_confirmed(
        audit, request_id, pending.tool_id, audit_params(pending),
        res.outcome.value,
        policy_decision="allowed" if dispatched else res.outcome.value,
        duration_ms=res.duration_ms,
    )
    return templates.render(res.outcome, res.display, detach=spec.detach)


async def _audit_confirmed(
    audit: AuditLog | None,
    request_id: str,
    tool_id: str,
    params: dict[str, str],
    outcome: str,
    *,
    policy_decision: str = "allowed",
    duration_ms: int = 0,
) -> None:
    """One row per confirmed dispatch (FR-58). Mirrors `_plan_and_act`'s tail."""
    if audit is None:
        return
    await audit.arecord(
        request_id=request_id,
        tool_id=tool_id,
        params=params,
        policy_decision=policy_decision,
        outcome=outcome,
        duration_ms=duration_ms,
    )


def audit_params(pending: PendingPreference | PendingAction) -> dict[str, str]:
    """What may be recorded about a pending, executed or declined (FR-26/FR-57).

    One function, so the redaction rule cannot end up stated differently in the
    executed path and the declined path — that divergence is what C1 was.

    The rule: record enough to know WHAT was proposed, never enough to leak the
    user's own content. A preference value and clipboard text are both content;
    a tool id and a closed-enum param are not.
    """
    if isinstance(pending, PendingPreference):
        return {"key": pending.key}  # the value is user data
    if pending.tool_id == "clipboard_set":
        return {"chars": str(len(pending.params.get("text", "")))}
    if pending.tool_id == "clipboard_read":
        return {}  # nothing about the selection, not even its size
    return dict(pending.params)  # closed enums (state=off, action=close, ...)


async def _audit_declined(
    audit: AuditLog | None,
    request_id: str,
    tool_id: str,
    pending: PendingPreference | PendingAction,
) -> None:
    """One row per DECLINED confirm (ADR-072). Nothing ran, so `policy_decision`
    and `outcome` both say so and `duration_ms` is 0."""
    if audit is None:
        return
    await audit.arecord(
        request_id=request_id,
        tool_id=tool_id,
        params=audit_params(pending),
        policy_decision="declined",
        outcome="declined",
        duration_ms=0,
    )


async def _do_forget(
    params: dict[str, str],
    prefs: PrefStore | None,
    audit: AuditLog | None,
    request_id: str,
) -> TurnResult:
    t0 = time.monotonic()
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
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
    return TurnResult("forget_preference", params, spoken, bool(n))


def _parse_reminder_seconds(raw: str) -> float | None:
    """Parse the planner's `seconds` field to a positive finite float, or None
    if it is missing/garbled. None means "ask", NOT "guess a default" — a
    misheard duration must never silently become a random timer."""
    digits = "".join(c for c in raw if c.isdigit() or c == ".")
    try:
        v = float(digits)
    except ValueError:
        return None
    if v != v or v in (float("inf"), float("-inf")) or v <= 0:
        return None
    return v


def _humanize_duration(sec: float) -> str:
    if sec < 60:
        n = int(round(sec))
        return f"{n} second{'' if n == 1 else 's'}"
    if sec < 3600:
        m = int(round(sec / 60))
        return f"{m} minute{'' if m == 1 else 's'}"
    h = int(round(sec / 3600))
    return f"{h} hour{'' if h == 1 else 's'}"


# Placeholder messages the planner emits when it heard a duration but no task;
# treat them as "no message" so the spoken line stays natural.
_EMPTY_REMINDER_MSGS = frozenset({"", "timer up", "timer", "reminder", "alarm"})


async def _do_set_reminder(
    params: dict[str, str],
    prefs: PrefStore | None,
    audit: AuditLog | None,
    request_id: str,
) -> TurnResult:
    t0 = time.monotonic()
    db = prefs._db if prefs else (audit._db if audit else None)
    if db is None:
        return TurnResult("set_reminder", params, "Memory unavailable.", False)

    from .store.reminders import ReminderStore

    sec = _parse_reminder_seconds(params.get("seconds", ""))
    if sec is None:
        # Don't set a wrong timer on a mishear — ask again, with an example so
        # the retry is easy and natural. Nothing is created; dispatched=False.
        return TurnResult(
            "set_reminder", params,
            "I didn't catch how long. Try, for example, "
            "remind me in ten minutes to check the pasta.",
            False,
        )

    msg = params.get("message", "").strip()
    has_task = msg.lower() not in _EMPTY_REMINDER_MSGS

    store = ReminderStore(db)
    await store.acreate(seconds=sec, message=msg or "Timer up", kind="timer")

    dur = _humanize_duration(sec)
    spoken = (
        f"Okay, I'll remind you to {msg} in {dur}." if has_task
        else f"Timer set for {dur}."
    )

    if audit is not None:
        await audit.arecord(
            request_id=request_id,
            tool_id="set_reminder",
            params={"seconds": str(int(sec)), "message": msg[:40]},
            policy_decision="allowed",
            outcome="ok",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    return TurnResult("set_reminder", params, spoken, True)


async def _do_list_reminders(prefs: PrefStore | None) -> TurnResult:
    db = prefs._db if prefs else None
    if db is None:
        return TurnResult("list_reminders", {}, "Memory unavailable.", False)

    from .store.reminders import ReminderStore

    store = ReminderStore(db)
    active = await store.alist_active()
    if not active:
        return TurnResult("list_reminders", {}, "You have no active timers or reminders.", False)

    n = len(active)
    msgs = ", ".join(r.message for r in active[:3])
    spoken = f"You have {n} active {'timer' if n == 1 else 'timers'}: {msgs}."
    return TurnResult("list_reminders", {}, spoken, False)


async def _do_cancel_reminder(
    params: dict[str, str],
    prefs: PrefStore | None,
    audit: AuditLog | None = None,
    request_id: str = "",
) -> TurnResult:
    t0 = time.monotonic()
    db = prefs._db if prefs else None
    if db is None:
        return TurnResult("cancel_reminder", params, "Memory unavailable.", False)

    from .store.reminders import ReminderStore

    # "Cancel my reminder" means the one just set — the most recently CREATED,
    # not the one firing farthest in the future. `alist_active` orders by
    # fire_at ASC, so the old `active[-1]` picked the latest fire time: with a
    # pasta timer and a 3pm meeting reminder outstanding, "cancel my timer"
    # killed the meeting and said only "Cancelled." (audit H7).
    #
    # There is no id branch any more (ADR-070): ids are never spoken or shown,
    # so the planner could not supply one, and the required-`id` schema made
    # this whole function unreachable.
    store = ReminderStore(db)
    active = await store.alist_active()
    if not active:
        return TurnResult("cancel_reminder", params, "No active timer to cancel.", False)
    target = max(active, key=lambda r: r.created_at)
    ok = await store.acancel(target.id)
    if ok:  # a dispatch, so a row (FR-58)
        await _audit_confirmed(
            audit, request_id, "cancel_reminder", {}, "ok",
            duration_ms=int((time.monotonic() - t0) * 1000)
        )
    # Say WHICH one, so a wrong pick is audible instead of silent.
    spoken = f"Cancelled: {target.message}." if ok else "No active timer to cancel."
    return TurnResult("cancel_reminder", params, spoken, ok)


async def _do_create_note(
    params: dict[str, str],
    prefs: PrefStore | None,
    audit: AuditLog | None,
    request_id: str,
) -> TurnResult:
    t0 = time.monotonic()
    db = prefs._db if prefs else (audit._db if audit else None)
    if db is None:
        return TurnResult("create_note", params, "Memory unavailable.", False)

    from .store.notes import NoteStore

    content = params.get("content", "").strip()
    if not content:
        return TurnResult("create_note", params, "Note content was empty.", False)

    store = NoteStore(db)
    await store.acreate(content)

    if audit is not None:
        await audit.arecord(
            request_id=request_id,
            tool_id="create_note",
            params={"content": content[:40]},
            policy_decision="allowed",
            outcome="ok",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    return TurnResult("create_note", params, "Note saved.", True)


async def _do_read_notes(prefs: PrefStore | None) -> TurnResult:
    db = prefs._db if prefs else None
    if db is None:
        return TurnResult("read_notes", {}, "Memory unavailable.", False)

    from .store.notes import NoteStore

    store = NoteStore(db)
    notes = await store.alist_notes(limit=3)
    if not notes:
        return TurnResult("read_notes", {}, "You have no saved notes.", False)

    items = "; ".join(f"Note {i+1}: {n.content}" for i, n in enumerate(notes))
    return TurnResult("read_notes", {}, f"Here are your latest notes: {items}", False)


# `_do_clipboard_read` is gone: reading the clipboard aloud is now a confirmed
# action, resolved in `resolve_pending` (ADR-068a).


