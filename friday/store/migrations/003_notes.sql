-- 003_notes — notes capture and reading table (G12, ADR-057).

CREATE TABLE IF NOT EXISTS notes (
  id          TEXT PRIMARY KEY,
  created_at  REAL NOT NULL,
  content     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_created ON notes(created_at);
