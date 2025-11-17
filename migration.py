"""Database schema management for the OR registry."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path.cwd() / "ornbh.db"

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS surgery_cases (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  uuid           TEXT NOT NULL UNIQUE,
  or_room        TEXT,
  hn             TEXT NOT NULL,
  patient_name   TEXT NOT NULL,
  age            INTEGER,
  diagnosis      TEXT,
  operation      TEXT,
  surgeon        TEXT,
  ward           TEXT,
  case_size      TEXT,
  department     TEXT,
  start_time     TEXT,
  end_time       TEXT,
  urgency        TEXT NOT NULL CHECK (urgency IN ('Elective','Emergency')),
  service_window TEXT NOT NULL CHECK (service_window IN ('InHours','OutOfHours')),
  assist1        TEXT,
  assist2        TEXT,
  scrub          TEXT,
  cir            TEXT,
  status         TEXT NOT NULL DEFAULT 'saved' CHECK (status IN ('saved','postponed','offcase')),
  reason         TEXT,
  repeat_24h     INTEGER DEFAULT 0,
  saved_at       TEXT NOT NULL DEFAULT (datetime('now')),
  created_at     TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cases_hn       ON surgery_cases(hn);
CREATE INDEX IF NOT EXISTS idx_cases_start    ON surgery_cases(start_time);
CREATE INDEX IF NOT EXISTS idx_cases_urgency  ON surgery_cases(urgency);
CREATE INDEX IF NOT EXISTS idx_cases_window   ON surgery_cases(service_window);
CREATE INDEX IF NOT EXISTS idx_cases_status   ON surgery_cases(status);

CREATE VIEW IF NOT EXISTS v_cases_today AS
SELECT * FROM surgery_cases
WHERE date(start_time) = date('now','localtime')
ORDER BY urgency DESC, service_window DESC, start_time, or_room;
"""


def ensure_schema(conn: sqlite3.Connection | None = None) -> None:
    """Ensure the unified registry schema exists on the configured database."""
    if conn is None:
        with sqlite3.connect(DB_PATH) as connection:
            connection.executescript(SCHEMA_SQL)
            connection.commit()
        return

    conn.executescript(SCHEMA_SQL)


def ensure_schema_at_path(path: Path | None = None) -> None:
    """Convenience helper to ensure the schema on the provided database path."""
    target = Path(path or DB_PATH)
    with sqlite3.connect(target) as connection:
        connection.executescript(SCHEMA_SQL)
        connection.commit()


if __name__ == "__main__":
    ensure_schema_at_path()
    print(f"✅ Schema ensured at {DB_PATH}")
