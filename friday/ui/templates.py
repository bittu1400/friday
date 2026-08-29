"""Outcome -> spoken/printed string (ADR-009).

Direct-action speech NEVER comes from the LLM. It comes from a template
keyed on the executor's outcome, so Friday cannot say "Opened Brave" when
the launch failed. There is no round-trip and no hallucinated success.
"""

from __future__ import annotations

from ..errors import Outcome

TEMPLATES: dict[Outcome, str] = {
    Outcome.OK: "{display}.",
    Outcome.NOT_FOUND: "I couldn't find {display} on this system.",
    Outcome.TIMEOUT: "That took too long, so I stopped it.",
    Outcome.DENIED: "I'm not allowed to do that.",
    Outcome.ERROR: "That didn't work.",
    Outcome.DISABLED: "I'm switched off.",
}


# A launch cannot be verified (ADR-043: the spawn is fire-and-forget and a
# single-instance handoff exits non-zero ON SUCCESS), so it states what it did
# rather than a verdict it does not have — "Launching Brave.", not "Opened
# Brave." A command IS verified: it was waited on, its exit code checked, and
# a non-zero one renders Outcome.ERROR instead of ever reaching this line.
LAUNCH_OK = "Launching {display}."


def render(outcome: Outcome, display: str, *, detach: bool = False) -> str:
    if outcome is Outcome.OK:
        if detach:
            return LAUNCH_OK.format(display=display)
        # "Opened volume up." was what the command tools spoke until 2026-08-29
        # — they shared the launch template. Speak the thing that happened.
        return f"{display[:1].upper()}{display[1:]}." if display else "Done."
    return TEMPLATES[outcome].format(display=display)


# --- memory templates (ADR-037 confirm-first) ------------------------------
# Fixed strings, never the LLM: the confirm question and its follow-ups are
# direct-action speech (ADR-009). `value` is rendered inert by the store
# before it reaches here.


def confirm_preference(key: str, value: str) -> str:
    return f"Remember that your {key} is {value}? (yes/no)"


def remembered(key: str, value: str) -> str:
    return f"Okay, I'll remember that your {key} is {value}."


def cancelled_preference() -> str:
    return "Okay, I won't remember that."


# The confirm-first handshake for an ACTION (ADR-037 extended to G12's
# reversible-but-disruptive tools, ADR-057). Same rule as a preference:
# anything that is not an explicit yes cancels, and the line is a fixed
# template, never the LLM.
CANCELLED_ACTION = "Okay, cancelled."
# A held pending whose tool is not in the registry any more. Fail honestly —
# never a blanket "done" (ADR-009).
ACTION_UNAVAILABLE = "I couldn't do that."


def forgotten(key: str) -> str:
    return f"Okay, I've forgotten your {key}."


def forget_unknown(key: str) -> str:
    return f"I don't have a preference for {key}."


MEMORY_UNAVAILABLE = "My memory isn't available right now."


# --- search templates (G7, ADR-046/047) — fixed strings, never the LLM ------
SEARCH_LOCAL_MODE = "I can't search the web in local mode."
# Canonical E_NET_DOWN string from spec.md §4 — keep them identical.
SEARCH_UNAVAILABLE = "I can't reach the web."
SEARCH_NO_RESULTS = "I didn't find anything on that."


# The deliberate-none line (G8, design open-item #4). `none` now SPEAKS so the
# operator can tell live that the model chose no action (vs an error path,
# which has its own distinct line). Destructive/out-of-ability requests land
# here. Fixed string, never the LLM.
OUT_OF_SCOPE = "That isn't something I'm able to do."


def confirm_from_history(what: str) -> str:
    """ADR-065: the action was not in the user's words — history supplied it,
    so it is confirmed before anything runs."""
    return f"Did you want me to open {what}?"
