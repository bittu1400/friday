"""Outcome -> spoken/printed string (ADR-009).

Direct-action speech NEVER comes from the LLM. It comes from a template
keyed on the executor's outcome, so Friday cannot say "Opened Brave" when
the launch failed. There is no round-trip and no hallucinated success.
"""

from __future__ import annotations

from ..errors import Outcome

TEMPLATES: dict[Outcome, str] = {
    Outcome.OK: "Opened {display}.",
    Outcome.NOT_FOUND: "I couldn't find {display} on this system.",
    Outcome.TIMEOUT: "That took too long, so I stopped it.",
    Outcome.DENIED: "I'm not allowed to do that.",
    Outcome.ERROR: "That didn't work.",
    Outcome.DISABLED: "I'm switched off.",
}


def render(outcome: Outcome, display: str) -> str:
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
