"""The gate, and the confirm handshake behind it (criteria 3.5, 3.9).

Two questions are asked of every capability before anything happens, and both
answers come from `Capability.risk`:

  1. is the panic switch engaged?   -> `_panic_blocked`
  2. must this be confirmed?        -> `_confirm_question`

Neither used to be derived. `turn.py` carried five `if plan.name == ...`
confirm branches — three of which could be DELETED with all 581 tests green
(M1) — and eight hand-written `config.is_disabled()` blocks, which were the
tenth place a capability lived (design §1) and Phase 1's own incomplete fix for
F1, where the switch guarded one of eleven side-effecting paths.

The other half of the file is the resolution: a held `PendingAction` or
`PendingPreference` meeting the user's answer. It is deterministic (ADR-037) —
no second model turn, so no injection surface and "one turn in flight" holds —
and nothing but an explicit affirmation executes. `resolve_pending` is shared by
the voice daemon and the TUI, because two implementations of one protocol IS
the bug: the TUI's copy assumed every pending was a preference and crashed on
every G12 action for months (C1).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass

from . import config
from .capabilities import CAPABILITIES, Risk
from .errors import Outcome
from .store.approvals import ApprovalStore, fingerprint
from .store.audit import AuditLog
from .store.prefs import PendingPreference, PrefStore
from .tools import executor
from .tools.registry import REGISTRY
from .tools.search import SearchResult
from .ui import templates

log = logging.getLogger("friday.gate")

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

