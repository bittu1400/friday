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

log = logging.getLogger("friday.turn")

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
    except SchemaError:
        return TurnResult("none", {}, "I didn't understand.", False)
    except LlamaTimeout:
        return TurnResult("none", {}, "That took too long.", False)
    except LlamaUnreachable:
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



    if plan.name == "remember_preference":
        return _plan_remember(params)

    if plan.name == "forget_preference":
        return await _do_forget(params, prefs, audit, request_id)

    if plan.name == "set_reminder":
        return await _do_set_reminder(params, prefs, audit, request_id)

    if plan.name == "list_reminders":
        return await _do_list_reminders(prefs)

    if plan.name == "cancel_reminder":
        return await _do_cancel_reminder(params, prefs)

    if plan.name == "set_dnd":
        return TurnResult("set_dnd", {}, "Quiet mode enabled. Let me know when you need me.", False)

    if plan.name == "resume_dnd":
        return TurnResult("resume_dnd", {}, "Quiet mode disabled. How can I help?", False)

    if plan.name == "create_note":
        return await _do_create_note(params, prefs, audit, request_id)

    if plan.name == "read_notes":
        return await _do_read_notes(prefs)

    if plan.name == "clipboard_read":
        # ADR-068a (OQ-34): the clipboard is read ALOUD, so its contents leave
        # the machine as sound in whatever room Friday is in — a copied
        # password or 2FA code included. Speaking it because the planner
        # matched a phrase is not acceptable, so it joins clipboard_set,
        # wifi-off and window-close behind the confirm. Nothing is even read
        # until the user says yes.
        return TurnResult(
            "clipboard_read", params,
            "Do you want me to read your clipboard aloud?", False,
            pending=PendingAction("clipboard_read", {}, "read the clipboard aloud"),
        )

    if plan.name == "clipboard_set":
        return TurnResult(
            "clipboard_set", params, "Are you sure you want to overwrite your clipboard?",
            False, pending=PendingAction("clipboard_set", params, "overwrite clipboard")
        )

    if plan.name == "system_wifi" and params.get("state") == "off":
        return TurnResult(
            "system_wifi", params, "Are you sure you want to turn off Wi-Fi?",
            False, pending=PendingAction("system_wifi", params, "turn off Wi-Fi")
        )

    if plan.name == "hypr_window" and params.get("action") == "close":
        return TurnResult(
            "hypr_window", params, "Are you sure you want to close the active window?",
            False, pending=PendingAction("hypr_window", params, "close active window")
        )

    if plan.name == "dictation_mode":
        act = params.get("action", "start").lower()
        spoken = "Dictation mode enabled." if act == "start" else "Dictation mode disabled."
        return TurnResult("dictation_mode", params, spoken, False)

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


async def resolve_pending(
    pending: PendingPreference | PendingAction | None,
    answer: str,
    *,
    prefs: PrefStore | None,
    audit: AuditLog | None,
    request_id: str,
    dry_run: bool = False,
) -> str:
    """Resolve a confirm-first handshake for EITHER pending type, from EITHER UI.

    Both the voice daemon and the TUI route here so the two can never drift
    apart again. C1 of the 2026-08-26 audit was exactly that drift: the TUI
    still assumed `pending` was always a `PendingPreference` and called
    `confirm_preference` unconditionally, so every G12 `PendingAction` confirm
    ("Are you sure you want to overwrite your clipboard?") raised
    AttributeError on `pending.key` and did nothing at all. The voice path had
    been migrated; the text path never was. One resolver, one behaviour.

    Deterministic (ADR-037): no second model turn, so no injection surface and
    one-turn-in-flight holds. Anything that is not an explicit affirmation
    cancels — fail safe. Execute FIRST, then speak (ADR-009): every branch
    returns the line only after the side effect has actually happened.
    """
    if pending is None:  # defensive: nothing was held
        return templates.CANCELLED_ACTION

    if isinstance(pending, PendingPreference):
        if is_affirmation(answer):
            return await confirm_preference(pending, prefs, audit, request_id=request_id)
        return templates.cancelled_preference()

    if not is_affirmation(answer):
        return templates.CANCELLED_ACTION

    if pending.tool_id == "clipboard_set":
        # Not a subprocess-registry tool: text goes to wl-copy on STDIN (see
        # tools/clipboard.py). Speak the real outcome — never a blanket "done".
        from .tools.clipboard import set_clipboard

        ok = await asyncio.to_thread(set_clipboard, pending.params.get("text", ""))
        return "Copied to your clipboard." if ok else "Clipboard unavailable."

    if pending.tool_id == "clipboard_read":
        # ADR-068a: read only now, on an explicit yes — a declined confirm must
        # not so much as fetch the selection, let alone voice it.
        from .tools.clipboard import read_clipboard

        raw = await asyncio.to_thread(read_clipboard)
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
    return templates.render(res.outcome, res.display)


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
            duration_ms=0,
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


async def _do_cancel_reminder(params: dict[str, str], prefs: PrefStore | None) -> TurnResult:
    db = prefs._db if prefs else None
    if db is None:
        return TurnResult("cancel_reminder", params, "Memory unavailable.", False)

    from .store.reminders import ReminderStore

    store = ReminderStore(db)
    rid = params.get("id", "").strip()
    if rid:
        ok = await store.acancel(rid)
    else:
        # Cancel latest active
        active = await store.alist_active()
        ok = await store.acancel(active[-1].id) if active else False

    spoken = "Cancelled." if ok else "No active timer to cancel."
    return TurnResult("cancel_reminder", params, spoken, ok)


async def _do_create_note(
    params: dict[str, str],
    prefs: PrefStore | None,
    audit: AuditLog | None,
    request_id: str,
) -> TurnResult:
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
            duration_ms=0,
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


