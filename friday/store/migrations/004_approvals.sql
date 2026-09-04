-- 004_approvals — the first-use allowlist (Phase 3, criterion 3.9,
-- design-2026-09-02.md §3.3).
--
-- A FIRST_USE capability asks once per subject and remembers the answer. The
-- row is written ONLY from a completed confirm handshake; no planner output
-- reaches this table, and `subject` is a closed-enum id, never free text.
--
-- `argv_sha256` is NOT optional and v1 of the design omitted it. App ids are
-- derived from the `.desktop` Name (`desktop.app_key`) and `scan()` resolves a
-- key collision with `setdefault` — first wins. Two applications can therefore
-- normalise to one id, and an uninstall followed by an install can hand a
-- stored approval to a DIFFERENT binary. The fingerprint closes that: if the
-- argv behind an approved id has changed, the approval does not apply.
--
-- Never swept by retention (`store/audit.py::sweep_retention` names its three
-- tables and this is not one of them): an approval is user intent, like a
-- preference, not machine exhaust.

CREATE TABLE IF NOT EXISTS approvals (
  kind        TEXT NOT NULL,     -- 'app' | 'recipe' | 'device'
  subject     TEXT NOT NULL,     -- closed-enum id, never free text
  argv_sha256 TEXT NOT NULL,     -- fingerprint of what was approved
  approved_at INTEGER NOT NULL,
  PRIMARY KEY (kind, subject)
);
