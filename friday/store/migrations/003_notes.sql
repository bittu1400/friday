-- 003_notes — notes capture and reading table (G12, ADR-057).

CREATE TABLE notes (
  id          TEXT PRIMARY KEY,
  created_at  REAL NOT NULL,
  content     TEXT NOT NULL
);
CREATE INDEX idx_notes_created ON notes(created_at);
