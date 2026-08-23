"""Stage 2 of a conversational turn (G8, ADR-048): generate a spoken reply.

Free text -- NO grammar (temperature > 0, a stop sequence). Reuses the same
llama-server (invariant #6). The command-vs-chat decision was already made in
the grammar-locked planner; this runs only after `chat` was chosen, and it
NEVER dispatches. Output is sanitized before TTS: it is spoken aloud, so no
markup, URLs, or control chars, and a hard length cap. Any failure or empty
output returns a fixed fallback (never a raw exception -- FR-26).
"""

from __future__ import annotations

import re
import unicodedata

from .prompt import assemble_chat_system

# Deterministic fallback (never the LLM): spoken when generation fails/empty.
CHAT_FALLBACK = "My words failed me for a second."

# Tuned provisionally; a listening test refines these (design open items).
_CHAT_TEMPERATURE = 0.7
_CHAT_MAX_TOKENS = 160          # ~4 short sentences
_CHAT_STOP = ["\nYou:", "\nUser:"]   # don't let it hallucinate the next turn
_MAX_CHARS = 600                # hard cap after sanitization

_URL = re.compile(r"https?://\S+")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_MD = re.compile(r"[*_`#>\[\]()]")


def _speakable(text: str) -> str:
    """Strip anything that should never be spoken; collapse whitespace; cap."""
    text = unicodedata.normalize("NFKC", text)
    text = _URL.sub("", text)
    text = _MD.sub(" ", text)
    text = _CONTROL.sub(" ", text)
    text = " ".join(text.split())
    return text[:_MAX_CHARS].strip()


def generate_reply(
    client,
    utterance: str,
    *,
    prefs_digest: str = "",
    history: str = "",
    habits_digest: str = "",
) -> str:
    system = assemble_chat_system(prefs_digest=prefs_digest, habits_digest=habits_digest)
    user = f"{history}\nYou: {utterance}".strip() if history else utterance
    try:
        raw = client.complete(
            system=system,
            user=user,
            grammar="",                 # free text
            max_tokens=_CHAT_MAX_TOKENS,
            temperature=_CHAT_TEMPERATURE,
            stop=_CHAT_STOP,
        )
    except Exception:                   # never leak a raw exception (FR-26)
        return CHAT_FALLBACK
    return _speakable(raw) or CHAT_FALLBACK

