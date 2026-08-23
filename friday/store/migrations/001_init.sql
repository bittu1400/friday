-- 001_init — the persistence schema (friday.md §6, G4).
--
-- Forward-only. Applied by store/db.py when the DB's recorded version is
-- below 1. Pure DDL: pragmas (WAL, busy_timeout) and the version row are
-- set in code so this file stays a declarative schema and nothing else.
--
-- No column exists for `thought`, raw prompts, raw audio, key events, or
-- unredacted payloads. That is FR-57 enforced by schema, not by discipline.

CREATE TABLE schema_version (version INTEGER NOT NULL);

-- Preferences. `key` is a slug (ADR-035, [a-z0-9_]); `value_json` is the
-- raw user value JSON-encoded. `expires_at` NULL = active; a soft-expire
-- (ADR-036) sets it to a timestamp. `pinned` is inert under ADR-038 (kept
-- so retention policy can change without a migration).
CREATE TABLE preferences (
  key        TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  source     TEXT NOT NULL CHECK (source IN ('user_confirmed','user_typed')),
  pinned     INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL,
  expires_at INTEGER,
  revision   INTEGER NOT NULL DEFAULT 1
);

-- One row per dispatch (FR-58). `args_redacted` has already had home paths
-- stripped before it reaches here (FR-57 / obs redaction).
CREATE TABLE action_audit (
  request_id       TEXT PRIMARY KEY,
  tool_id          TEXT NOT NULL,
  args_redacted    TEXT NOT NULL,
  policy_decision  TEXT NOT NULL,
  outcome          TEXT NOT NULL,
  duration_ms      INTEGER NOT NULL,
  created_at       INTEGER NOT NULL
);
CREATE INDEX idx_audit_created ON action_audit(created_at);

CREATE TABLE session_summaries (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id  TEXT NOT NULL,
  summary     TEXT NOT NULL,
  created_at  INTEGER NOT NULL
);
CREATE INDEX idx_summ_session ON session_summaries(session_id, created_at);
