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
