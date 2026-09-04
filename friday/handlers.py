"""One handler per capability, and one table that finds it (criterion 3.4).

`_plan_and_act` used to be a chain of nineteen `if plan.name == ...` branches
with the handler bodies interleaved, so adding a capability meant editing the
turn — the ninth of the ten places design §1 counts. It is now a lookup:

    handler = HANDLERS.get(plan.name)          # or the registry, below

Everything above the lookup is policy the turn owns and no handler repeats:
the two-pass plan (ADR-065), the panic gate and the confirm decision (criterion
3.5). Everything below it is one capability's work. A handler is reached ONLY
after both gates have passed, so **no handler checks `config.is_disabled()` and
no handler asks a question** — if you find yourself writing either, it belongs
in `risk`.

Capabilities with a `Subprocess` spec in `tools/registry.py` are not in this
table at all: they share one body (execute, then speak from the outcome
template — ADR-009), and `turn.py` runs it when the lookup misses. The table
holds the ones that do something else — talk to the model, write to SQLite,
reach the network, or answer from a template.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Mapping

from . import config
from .errors import Outcome
from .gate import PendingAction, TurnResult, _audit_confirmed
from .llm import chat, grounding
from .llm.client import LlamaClient
# `_plan_remember` catches this. It was caught without being imported from
# 2026-09-04 (criterion 3.4 moved the body here and left the name behind), so
# the handler raised NameError on every malformed preference instead of
# speaking "I didn't understand." — D35.
from .llm.validate import SchemaError
from .store.audit import AuditLog
from .store.prefs import PendingPreference, PrefStore, resolve
from .tools.search import SearchClient, SearchResult, SearchUnavailable, sanitize
from .ui import templates

log = logging.getLogger("friday.handlers")


@dataclass(frozen=True)
class TurnContext:
    """Everything a handler may reach, and nothing it may not.

    It is a record rather than a long parameter list because the alternative
    was threading nine arguments through nineteen branches by hand, which is
    how `approvals` came to be missing from a call site the first time it was
    added. `dispatched` state and the confirm handshake are deliberately absent:
    a handler decides what happened, never whether it was allowed to happen.
    """

    client: LlamaClient
    request_id: str
    utterance: str = ""
    prefs: PrefStore | None = None
    audit: AuditLog | None = None
    search_client: SearchClient | None = None
    connected: bool = True
    dry_run: bool = False
    history: str = ""
    habits_digest: str = ""
    summaries_digest: str = ""


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




# --- the table (criterion 3.4) ----------------------------------------------
# One row per capability that is not a plain subprocess dispatch. Each row is
# the whole of "what does this capability do"; there is no second place that
# names it and no `if` to keep in the right order.
#
# `chat` and `none` are here rather than special-cased in the turn because they
# ARE capabilities — the grammar's name alternation is generated from the same
# record. `chat` still cannot dispatch: invariant #1 holds structurally,
# because the untrusted path is locked to final.gbnf whose name can only be
# "none".

Handler = Callable[[TurnContext, dict], Awaitable[TurnResult]]


async def _h_none(ctx: TurnContext, params: dict) -> TurnResult:
    return TurnResult("none", params, templates.OUT_OF_SCOPE, False)


async def _h_chat(ctx: TurnContext, params: dict) -> TurnResult:
    """The talking half. No executor call, `dispatched=False`, ever.

    It writes ONE audit row, and the row is deliberately EMPTY of content
    (D37). Chat is the most expensive turn class in the system — TTFA p50 was
    7177 ms before ADR-094 capped the reply, against 1858-2466 ms for a direct
    action — and it was the only turn class writing no row at all, so
    `just stats`, which reads `action_audit`, could not see it. Every latency
    conversation in this project has therefore been about the cheap half.

    **`params` is `{}` and must stay `{}`.** Both halves of a chat turn are
    exactly what invariant #7 forbids on disk: `ctx.utterance` is a raw
    transcript (FR-26) and `reply` is raw model output (FR-57). The fact worth
    keeping is that a chat turn happened and how long it took; there is no
    content whose absence costs anything.

    `outcome` separates a real reply from `CHAT_FALLBACK`, which
    `generate_reply` returns for ANY generation failure — it swallows the
    exception, so without this the row would say a chat turn succeeded while
    the model was down. That is the one bit of chat health the row can carry
    without carrying content.
    """
    t0 = time.monotonic()
    reply = await asyncio.to_thread(
        chat.generate_reply, ctx.client, ctx.utterance,
        prefs_digest=(ctx.prefs.digest() if ctx.prefs else ""),
        history=ctx.history,
        habits_digest=ctx.habits_digest,
        summaries_digest=ctx.summaries_digest,
    )
    if ctx.audit is not None:
        await ctx.audit.arecord(
            request_id=ctx.request_id,
            tool_id="chat",
            params={},  # invariant #7: never the utterance, never the reply
            policy_decision="allowed",
            outcome="ok" if reply != chat.CHAT_FALLBACK else "error",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
    return TurnResult("chat", {}, reply, False)


async def _h_set_dnd(ctx: TurnContext, params: dict) -> TurnResult:
    return TurnResult(
        "set_dnd", {}, "Quiet mode enabled. Let me know when you need me.", False
    )


async def _h_resume_dnd(ctx: TurnContext, params: dict) -> TurnResult:
    return TurnResult("resume_dnd", {}, "Quiet mode disabled. How can I help?", False)


async def _h_dictation_mode(ctx: TurnContext, params: dict) -> TurnResult:
    """The daemon applies the state; this speaks the outcome (F27: text mode
    used to speak success and change nothing, because the TUI has no
    DictationManager)."""
    act = params.get("action", "start").lower()
    spoken = "Dictation mode enabled." if act == "start" else "Dictation mode disabled."
    return TurnResult("dictation_mode", params, spoken, False)


HANDLERS: Mapping[str, Handler] = {
    "none": _h_none,
    "chat": _h_chat,
    "web_search": lambda ctx, p: _do_web_search(
        p.get("query", ctx.utterance), ctx.client, ctx.search_client, ctx.connected,
        audit=ctx.audit, request_id=ctx.request_id,
    ),
    "remember_preference": lambda ctx, p: _plan_remember_async(p),
    "forget_preference": lambda ctx, p: _do_forget(
        p, ctx.prefs, ctx.audit, ctx.request_id
    ),
    "set_reminder": lambda ctx, p: _do_set_reminder(
        p, ctx.prefs, ctx.audit, ctx.request_id
    ),
    "list_reminders": lambda ctx, p: _do_list_reminders(ctx.prefs),
    "cancel_reminder": lambda ctx, p: _do_cancel_reminder(
        p, ctx.prefs, ctx.audit, ctx.request_id
    ),
    "set_dnd": _h_set_dnd,
    "resume_dnd": _h_resume_dnd,
    "create_note": lambda ctx, p: _do_create_note(
        p, ctx.prefs, ctx.audit, ctx.request_id
    ),
    "read_notes": lambda ctx, p: _do_read_notes(ctx.prefs),
    "dictation_mode": _h_dictation_mode,
}


async def _plan_remember_async(params: dict) -> TurnResult:
    """`remember_preference` resolves the key/value and hands back a pending;
    the WRITE happens on confirm (ADR-037). Sync work, async signature, so the
    table has one shape."""
    return _plan_remember(params)
