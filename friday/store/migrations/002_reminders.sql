-- 002_reminders — proactive reminders and timers table (G11, ADR-056).

CREATE TABLE reminders (
  id          TEXT PRIMARY KEY,
  created_at  REAL NOT NULL,
  fire_at     REAL NOT NULL,
  kind        TEXT NOT NULL CHECK (kind IN ('timer', 'reminder')),
  message     TEXT NOT NULL,
  state       TEXT NOT NULL CHECK (state IN ('active', 'fired', 'cancelled'))
);
CREATE INDEX idx_reminders_fire_state ON reminders(fire_at, state);
