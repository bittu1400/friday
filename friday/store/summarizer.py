"""Session summarizer and long-term memory distillation (G8 Stage 3, ADR-050).

At session exit, if meaningful dialogue occurred, Friday distills the in-RAM
dialogue buffer into 1-2 concise sentences capturing high-level context
(e.g., ongoing topics, apps used) without verbatim quotes or raw transcripts.

Stored in SQLite `session_summaries` table (`session_id`, `summary`, `created_at`).
Subject to retention sweep (purged after 90 days per ADR-038).

Invariants preserved:
- Invariant #7: No raw transcripts or audio on disk. Only sanitized, model-distilled
  high-level summaries are saved.
- Invariant #1 / #4: Memory provides conversational context (ADR-048), not side-effect triggers.
- Fast & lightweight: SQL aggregation runs in <2 ms.
"""

from __future__ import annotations

import re
import time
import unicodedata
from typing import Sequence

from .db import Database

DISTILL_SYSTEM = """\
You are a summarizer. Given a conversation between a user and an assistant named Friday, \
distill the main activities, topics discussed, or pending tasks into 1 or 2 concise \
sentences. Focus only on high-level facts and context. Never use verbatim quotes, \
never include markdown formatting, code, or URLs. If nothing meaningful was discussed, \
reply with an empty string."""

_URL = re.compile(r"https?://\S+")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_MD = re.compile(r"[*_`#>\[\]()]")
_MAX_CHARS = 250


def _sanitize_summary(text: str) -> str:
    """Strip markdown, URLs, control chars; collapse whitespace; length cap."""
    text = unicodedata.normalize("NFKC", text)
    text = _URL.sub("", text)
    text = _MD.sub(" ", text)
    text = _CONTROL.sub(" ", text)
    text = " ".join(text.split())
    return text[:_MAX_CHARS].strip()


def distill_dialogue(client, dialogue_text: str) -> str:
    """Distill raw in-memory dialogue into a high-level summary string."""
    if not dialogue_text.strip():
        return ""
    try:
        raw = client.complete(
            system=DISTILL_SYSTEM,
            user=f"Conversation:\n{dialogue_text}",
            grammar="",
            max_tokens=100,
            temperature=0.3,
            stop=["\n\n", "User:", "Conversation:"],
        )
    except Exception:
        return ""
    return _sanitize_summary(raw)


def save_session_summary(db: Database, session_id: str, summary: str) -> None:
    """Save a distilled summary into `session_summaries` table."""
    clean = summary.strip()
    if not clean:
        return
    db.write(
        "INSERT INTO session_summaries(session_id, summary, created_at) "
        "VALUES (?, ?, ?)",
        (session_id, clean, int(time.time())),
    )


def get_recent_session_summaries(db: Database, limit: int = 2) -> list[str]:
    """Retrieve the most recent distilled session summaries."""
    rows = db.query(
        "SELECT summary FROM session_summaries ORDER BY created_at DESC, id DESC LIMIT ?",
        (limit,),
    )
    return [r["summary"] for r in rows if r["summary"].strip()]



def render_summaries_digest(summaries: Sequence[str]) -> str:
    """Render session summaries as an inert data block for the chat system prompt."""
    if not summaries:
        return ""
    lines = ["<past_sessions>"]
    for s in summaries:
        clean = " ".join(s.split())[:200].strip()
        lines.append(f"- {clean}")
    lines.append("</past_sessions>")
    return "\n".join(lines)
