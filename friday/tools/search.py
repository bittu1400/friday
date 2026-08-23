"""SearXNG search client + sanitizer (G7, FR-60/FR-62).

Two responsibilities, kept separate so the sanitizer is testable without a
network: `SearchResult` + `sanitize()` are pure; `SearchClient.query()` does
the loopback HTTP. Sanitized bodies are what the model sees; URLs are held OUT
of band (never inside the model's context region) — that separation is the
durable control against URL exfiltration (invariant #2, §9.2), not cosmetics.
Nothing here is written to disk (invariant #7).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Control chars (except tab/newline) and zero-width / bidi-override chars. The
# zero-width set is the AS-4 / IS-4 vector: characters that split a keyword so a
# grep-style filter misses it. We strip, not reject, because these are result
# BODIES (untrusted data we display), not a command input.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
# ZWSP..RLM, bidi overrides (LRE..RLO/PDF), word-joiner, BOM — explicit escapes.
_ZERO_WIDTH = re.compile(r"[​-‏‪-‮⁠﻿]")
_MARKUP = re.compile(r"<[^>]*>")          # HTML tags
_MD = re.compile(r"[*_`#>\[\]()]")        # markdown emphasis / link syntax

# 1500 tokens ~ 1125 words (a token is ~0.75 of a word for English). The proxy
# is deliberately conservative; exact tokenization is not worth a dependency.
_WORDS_PER_TOKEN = 0.75


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    body: str


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _MARKUP.sub(" ", text)
    text = _ZERO_WIDTH.sub("", text)
    text = _CONTROL.sub(" ", text)
    text = _MD.sub(" ", text)
    return " ".join(text.split())  # collapse whitespace


def sanitize(
    results: list[SearchResult],
    *,
    max_results: int = 5,
    max_tokens: int = 1500,
) -> tuple[list[str], list[SearchResult]]:
    """Return (clean_bodies, sources). Bodies are sanitized + budget-capped and
    carry NO URLs; sources keep title+url for the TUI (out of band)."""
    kept = results[:max_results]
    budget_words = int(max_tokens * _WORDS_PER_TOKEN)
    bodies: list[str] = []
    for r in kept:
        cleaned = _clean(r.body)
        words = cleaned.split()
        if budget_words <= 0:
            bodies.append("")
            continue
        if len(words) > budget_words:
            words = words[:budget_words]
        budget_words -= len(words)
        bodies.append(" ".join(words))
    return bodies, list(kept)
