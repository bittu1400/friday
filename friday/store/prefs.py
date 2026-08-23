"""Preferences: key slugging, canonical aliases, CRUD, and digest render.

Key model (ADR-035, option d): the model supplies a free-text key; code
slugs it to `[a-z0-9_]` (the dedup mechanism — `My Name` and `my  name`
both fold to `my_name`) and a curated ALIAS map folds common synonyms onto
canonical keys so the digest is deterministic for the frequent cases. A
slug not in the map is stored as-is (the learned tail).

The VALUE is stored raw (ADR-035) but RENDERED inert (ADR / architecture
§4): a preference value is the durable-injection vector — written once, it
would steer every later turn — so the digest strips newlines, control
characters, and the fence tokens, and caps length. Storage keeps the user's
words; rendering keeps them from ever reading as an instruction (FR-55).
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from typing import Final, Mapping

from ..llm.validate import SchemaError
from .db import Database

# Curated synonym -> canonical anchor (ADR-035). Data, not schema: extend it
# when a near-dupe shows up; no migration needed.
ALIAS: Final[Mapping[str, str]] = {
    "my_name": "name",
    "call_me": "name",
    "text_editor": "editor",
    "code_editor": "editor",
    "web_browser": "browser",
    "music_player": "media_player",
    "music": "media_player",
    "media": "media_player",
    "terminal_emulator": "terminal",
}

_SLUG_STRIP = re.compile(r"[^a-z0-9_]+")


def slugify_key(raw: str) -> str:
    """NFKC, casefold, spaces/hyphens -> `_`, drop everything else, collapse
    repeats. Raises `SchemaError` if nothing survives (fail closed)."""
    s = unicodedata.normalize("NFKC", raw).casefold().strip()
    s = re.sub(r"[\s\-]+", "_", s)
    s = _SLUG_STRIP.sub("", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        raise SchemaError(f"preference key slugs to empty: {raw!r}")
    return s


def canonical_key(raw: str) -> str:
    """The slug, folded through the alias anchors."""
    slug = slugify_key(raw)
    return ALIAS.get(slug, slug)


def _est_tokens(s: str) -> int:
    """Cheap token estimate (~4 chars/token) for the digest budget. A proxy,
    not a tokenizer — the budget is a soft guard, not an exact accounting."""
    return max(1, len(s) // 4)


_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def render_value(value: str, *, cap: int = 200) -> str:
    """Neutralize a value for the digest: no newlines, no control chars, no
    fence tokens, length-capped. This is the injection control, not cosmetics."""
    v = unicodedata.normalize("NFKC", value)
    v = _CTRL.sub(" ", v)
    v = v.replace("<preferences>", " ").replace("</preferences>", " ")
    v = " ".join(v.split())  # collapse whitespace runs
    return v[:cap]


class PendingPreference:
    """A resolved-but-unwritten preference (ADR-037 confirm-first). Pure:
    holds the canonical key and raw value; no DB touched until confirmed."""

    __slots__ = ("key", "value")

    def __init__(self, key: str, value: str) -> None:
        self.key = key
        self.value = value

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, PendingPreference)
            and other.key == self.key
            and other.value == self.value
        )

    def __repr__(self) -> str:
        return f"PendingPreference(key={self.key!r}, value={self.value!r})"


def resolve(key: str, value: str) -> PendingPreference:
    """Resolve a model-supplied key+value to the canonical, unwritten form.
    Raises `SchemaError` on an empty slug — the caller fails closed to none."""
    if not value.strip():
        raise SchemaError("preference value is empty")
    return PendingPreference(canonical_key(key), value)


class PrefStore:
    """Preference CRUD over the single-writer `Database`."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def put(self, pending: PendingPreference, *, source: str = "user_confirmed") -> str:
        """Upsert. A rewrite bumps `revision` and clears any soft-expiry."""
        now = int(time.time())
        self._db.write(
            "INSERT INTO preferences"
            "(key, value_json, source, updated_at, expires_at, revision) "
            "VALUES (?, ?, ?, ?, NULL, 1) "
            "ON CONFLICT(key) DO UPDATE SET "
            "  value_json = excluded.value_json, "
            "  source     = excluded.source, "
            "  updated_at = excluded.updated_at, "
            "  expires_at = NULL, "
            "  revision   = preferences.revision + 1",
            (pending.key, json.dumps(pending.value), source, now),
        )
        return pending.key

    def forget_soft(self, key: str) -> int:
        """Voice/safe path (ADR-036): stop injecting now, keep the row.
        Returns rows affected (0 if the key was unknown or already expired)."""
        now = int(time.time())
        ck = canonical_key(key)
        return self._db.write(
            "UPDATE preferences SET expires_at = ? "
            "WHERE key = ? AND (expires_at IS NULL OR expires_at > ?)",
            (now, ck, now),
        )

    def forget_hard(self, key: str) -> int:
        """Keyboard-only explicit path (ADR-036, `--hard`). Irreversible."""
        return self._db.write(
            "DELETE FROM preferences WHERE key = ?", (canonical_key(key),)
        )

    def reset_hard(self) -> int:
        """Keyboard-only `reset --yes`. Clears every preference."""
        return self._db.write("DELETE FROM preferences", ())

    def active(self) -> dict[str, str]:
        """Non-expired preferences, key -> raw value, ordered by key."""
        now = int(time.time())
        rows = self._db.query(
            "SELECT key, value_json FROM preferences "
            "WHERE expires_at IS NULL OR expires_at > ? ORDER BY key",
            (now,),
        )
        return {r["key"]: json.loads(r["value_json"]) for r in rows}

    def export(self) -> str:
        """Active preferences as pretty JSON (FR-56 export)."""
        return json.dumps(self.active(), indent=2, ensure_ascii=False) + "\n"

    def digest(self, *, token_budget: int = 300) -> str:
        """The `<preferences>` region (FR-55, diagram 07): fenced `key=value`
        DATA, one per line, values rendered inert, capped at ~`token_budget`
        tokens. Selection is deterministic — `pinned DESC, updated_at DESC,
        key` — so the highest-priority preferences survive an overflow; the
        chosen set is then rendered sorted by key for a stable snapshot.
        Empty string when there are none.

        `pinned` orders digest OVERFLOW here; it is separate from retention
        (ADR-038, where it is inert). No Phase-1 surface sets it yet, so in
        practice this reduces to most-recently-updated-first."""
        now = int(time.time())
        rows = self._db.query(
            "SELECT key, value_json FROM preferences "
            "WHERE expires_at IS NULL OR expires_at > ? "
            "ORDER BY pinned DESC, updated_at DESC, key ASC",
            (now,),
        )
        if not rows:
            return ""
        used = _est_tokens("<preferences>\n</preferences>")
        chosen: list[str] = []
        for r in rows:
            line = f"{r['key']}={render_value(json.loads(r['value_json']))}"
            cost = _est_tokens(line) + 1
            if chosen and used + cost > token_budget:
                break  # keep at least one; drop the lowest-priority overflow
            used += cost
            chosen.append(line)
        chosen.sort()
        return "<preferences>\n" + "\n".join(chosen) + "\n</preferences>"
