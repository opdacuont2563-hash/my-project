"""Schema migration and diagnostics utilities for the OR registry."""
from __future__ import annotations

import argparse
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence

from utils_time_windows import categorize_timebucket, decide_service_window

DB_PATH = Path.cwd() / "ornbh.db"

ALLOWED_STATUSES: Sequence[str] = (
    "saved",
    "postponed",
    "offcase",
    "scheduled",
    "in-progress",
    "done",
    "cancelled",
)

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS surgery_cases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid            TEXT NOT NULL UNIQUE,
    or_room         TEXT,
    hn              TEXT NOT NULL,
    patient_name    TEXT NOT NULL,
    age             INTEGER,
    diagnosis       TEXT,
    operation       TEXT,
    surgeon         TEXT,
    ward            TEXT,
    case_size       TEXT,
    department      TEXT,
    start_time      TEXT,
    end_time        TEXT,
    urgency         TEXT NOT NULL CHECK (urgency IN ('Elective','Emergency')),
    service_window  TEXT NOT NULL CHECK (service_window IN ('InHours','OutOfHours')),
    time_bucket     TEXT NOT NULL DEFAULT 'ในเวลา'
                    CHECK (time_bucket IN ('ในเวลา','นอกเวลา')),
    assist1         TEXT,
    assist2         TEXT,
    scrub           TEXT,
    cir             TEXT,
    status          TEXT NOT NULL DEFAULT 'saved'
                    CHECK (
                        status IN (
                            'saved','postponed','offcase',
                            'scheduled','in-progress','done','cancelled'
                        )
                    ),
    reason          TEXT,
    repeat_24h      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    saved_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_cases_hn ON surgery_cases (hn);
CREATE INDEX IF NOT EXISTS idx_cases_start ON surgery_cases (start_time);
CREATE INDEX IF NOT EXISTS idx_cases_hn_start ON surgery_cases (hn, start_time);
CREATE INDEX IF NOT EXISTS idx_cases_urgency ON surgery_cases (urgency);
CREATE INDEX IF NOT EXISTS idx_cases_service_window ON surgery_cases (service_window);
CREATE INDEX IF NOT EXISTS idx_cases_time_bucket ON surgery_cases (time_bucket);
CREATE INDEX IF NOT EXISTS idx_cases_status ON surgery_cases (status);
"""

VIEW_SQL = """
CREATE VIEW IF NOT EXISTS v_cases_today AS
SELECT * FROM surgery_cases
WHERE date(start_time) = date('now','localtime')
ORDER BY urgency DESC, time_bucket DESC, start_time, or_room;
"""

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

{table}

{indexes}

{view}
""".format(table=TABLE_SQL.strip(), indexes=INDEX_SQL.strip(), view=VIEW_SQL.strip())

EXPECTED_COLUMNS = {
    "id",
    "uuid",
    "or_room",
    "hn",
    "patient_name",
    "age",
    "diagnosis",
    "operation",
    "surgeon",
    "ward",
    "case_size",
    "department",
    "start_time",
    "end_time",
    "urgency",
    "service_window",
    "time_bucket",
    "assist1",
    "assist2",
    "scrub",
    "cir",
    "status",
    "reason",
    "repeat_24h",
    "created_at",
    "updated_at",
    "saved_at",
}


def _normalize_status(value: str | None) -> str:
    if not value:
        return "saved"
    text = str(value).strip().lower()
    mapping = {
        "off case": "offcase",
        "off-case": "offcase",
        "offcase": "offcase",
        "postponed": "postponed",
        "เลื่อน": "postponed",
        "เลื่อนผ่าตัด": "postponed",
        "saved": "saved",
        "done": "done",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "in-progress": "in-progress",
        "in progress": "in-progress",
        "scheduled": "scheduled",
    }
    if text in mapping:
        return mapping[text]
    if text in ALLOWED_STATUSES:
        return text
    return "saved"


def _check_repeat_24h(conn: sqlite3.Connection, hn: str, start_dt: datetime) -> int:
    if not hn or not start_dt:
        return 0
    window_start = (start_dt - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M")
    window_end = start_dt.strftime("%Y-%m-%d %H:%M")
    cur = conn.execute(
        """
        SELECT COUNT(*) FROM surgery_cases
        WHERE hn = ? AND start_time BETWEEN ? AND ?
    """,
        (hn, window_start, window_end),
    )
    return 1 if cur.fetchone()[0] else 0


def ensure_schema(conn: sqlite3.Connection) -> None:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='surgery_cases'")
    existing = cur.fetchone()
    needs_upgrade = False
    if existing:
        info = conn.execute("PRAGMA table_info(surgery_cases)").fetchall()
        have_cols = {row[1] for row in info}
        missing = EXPECTED_COLUMNS.difference(have_cols)
        needs_upgrade = bool(missing)
        if not needs_upgrade:
            schema_sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='surgery_cases'"
            ).fetchone()
            if schema_sql:
                sql_text = schema_sql[0] or ""
                for status in ("'saved'", "'offcase'", "'postponed'"):
                    if status not in sql_text:
                        needs_upgrade = True
                        break
                if "time_bucket" not in sql_text:
                    needs_upgrade = True
    if needs_upgrade:
        _upgrade_schema(conn)
    conn.executescript(SCHEMA_SQL)


def _upgrade_schema(conn: sqlite3.Connection) -> None:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='surgery_cases'")
    if not cur.fetchone():
        return

    old_factory = conn.row_factory
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM surgery_cases").fetchall()
    except sqlite3.Error:
        rows = []
    finally:
        conn.row_factory = old_factory

    conn.execute("DROP TABLE IF EXISTS surgery_cases_new")
    table_sql = TABLE_SQL.replace("surgery_cases", "surgery_cases_new", 1)
    conn.executescript(table_sql)

    insert_sql = """
        INSERT INTO surgery_cases_new (
            uuid, or_room, hn, patient_name, age, diagnosis, operation,
            surgeon, ward, case_size, department, start_time, end_time,
            urgency, service_window, time_bucket, assist1, assist2, scrub,
            cir, status, reason, repeat_24h, created_at, updated_at, saved_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """

    for row in rows:
        row_dict = dict(row)
        start_iso = row_dict.get("start_time")
        start_dt: datetime | None = None
        if start_iso:
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
                try:
                    start_dt = datetime.strptime(start_iso, fmt)
                    break
                except Exception:
                    continue
            if start_dt is None:
                try:
                    start_dt = datetime.fromisoformat(start_iso)
                except Exception:
                    start_dt = None
        time_bucket = row_dict.get("time_bucket")
        if not time_bucket:
            time_bucket = categorize_timebucket(start_dt) if start_dt else "นอกเวลา"
        status_val = row_dict.get("status") or "saved"
        if status_val not in ALLOWED_STATUSES:
            status_val = "saved"
        created_at = row_dict.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M")
        updated_at = row_dict.get("updated_at") or created_at
        saved_at = row_dict.get("saved_at") or created_at
        reason = row_dict.get("reason")
        repeat_flag = int(row_dict.get("repeat_24h") or 0)

        values = (
            row_dict.get("uuid"),
            row_dict.get("or_room"),
            row_dict.get("hn"),
            row_dict.get("patient_name"),
            row_dict.get("age"),
            row_dict.get("diagnosis"),
            row_dict.get("operation"),
            row_dict.get("surgeon"),
            row_dict.get("ward"),
            row_dict.get("case_size"),
            row_dict.get("department"),
            row_dict.get("start_time"),
            row_dict.get("end_time"),
            row_dict.get("urgency"),
            row_dict.get("service_window"),
            time_bucket,
            row_dict.get("assist1"),
            row_dict.get("assist2"),
            row_dict.get("scrub"),
            row_dict.get("cir"),
            status_val,
            reason,
            repeat_flag,
            created_at,
            updated_at,
            saved_at,
        )
        conn.execute(insert_sql, values)

    conn.execute("DROP TABLE IF EXISTS surgery_cases")
    conn.execute("ALTER TABLE surgery_cases_new RENAME TO surgery_cases")
    conn.commit()


def insert_sample_cases(conn: sqlite3.Connection) -> None:
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    elective_start = now.replace(hour=9)
    elective_end = elective_start + timedelta(hours=2)
    emergency_start = now.replace(hour=20)
    emergency_end = emergency_start + timedelta(hours=3)

    samples = [
        dict(
            uuid=str(uuid.uuid4()),
            hn="999001",
            patient_name="Sample Elective",
            age=45,
            diagnosis="Cholelithiasis",
            operation="Laparoscopic Cholecystectomy",
            surgeon="Dr. Demo",
            ward="ศัลยกรรม",
            case_size="Major",
            department="Surgery",
            or_room="OR1",
            start_time=elective_start,
            end_time=elective_end,
            urgency="Elective",
            assist1="RN A",
            assist2="RN B",
            scrub="Nurse C",
            cir="Nurse D",
        ),
        dict(
            uuid=str(uuid.uuid4()),
            hn="999002",
            patient_name="Sample Emergency",
            age=63,
            diagnosis="Trauma",
            operation="Exploratory Laparotomy",
            surgeon="Dr. Demo",
            ward="ER",
            case_size="Major",
            department="Trauma",
            or_room="OR2",
            start_time=emergency_start,
            end_time=emergency_end,
            urgency="Emergency",
            assist1="RN E",
            assist2="RN F",
            scrub="Nurse G",
            cir="Nurse H",
        ),
    ]

    insert_sql = """
        INSERT INTO surgery_cases (
            uuid, or_room, hn, patient_name, age, diagnosis, operation,
            surgeon, ward, case_size, department, start_time, end_time,
            urgency, service_window, time_bucket, assist1, assist2, scrub,
            cir, status, reason, repeat_24h, saved_at, updated_at
        ) VALUES (
            ?,?,?,?,?,?,?,?,?,?,
            ?,?,?,?,?,?,?,?,?,?,
            ?,?,?,?, datetime('now')
        )
        ON CONFLICT(uuid) DO UPDATE SET
            or_room=excluded.or_room,
            hn=excluded.hn,
            patient_name=excluded.patient_name,
            age=excluded.age,
            diagnosis=excluded.diagnosis,
            operation=excluded.operation,
            surgeon=excluded.surgeon,
            ward=excluded.ward,
            case_size=excluded.case_size,
            department=excluded.department,
            start_time=excluded.start_time,
            end_time=excluded.end_time,
            urgency=excluded.urgency,
            service_window=excluded.service_window,
            time_bucket=excluded.time_bucket,
            assist1=excluded.assist1,
            assist2=excluded.assist2,
            scrub=excluded.scrub,
            cir=excluded.cir,
            status=excluded.status,
            reason=excluded.reason,
            repeat_24h=excluded.repeat_24h,
            saved_at=excluded.saved_at,
            updated_at=datetime('now')
    """

    for sample in samples:
        start_dt: datetime = sample["start_time"]
        end_dt: datetime = sample["end_time"]
        service_window = decide_service_window(sample["urgency"], start_dt, end_dt)
        time_bucket = categorize_timebucket(start_dt)
        repeat_flag = _check_repeat_24h(conn, sample["hn"], start_dt)
        saved_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        values = (
            sample["uuid"],
            sample.get("or_room"),
            sample["hn"],
            sample["patient_name"],
            sample.get("age"),
            sample.get("diagnosis"),
            sample.get("operation"),
            sample.get("surgeon"),
            sample.get("ward"),
            sample.get("case_size"),
            sample.get("department"),
            start_dt.strftime("%Y-%m-%d %H:%M"),
            end_dt.strftime("%Y-%m-%d %H:%M"),
            sample["urgency"],
            service_window,
            time_bucket,
            sample.get("assist1"),
            sample.get("assist2"),
            sample.get("scrub"),
            sample.get("cir"),
            "saved",
            None,
            repeat_flag,
            saved_at,
        )
        conn.execute(insert_sql, values)
    conn.commit()


def diagnostics(conn: sqlite3.Connection) -> None:
    cur = conn.execute("SELECT COUNT(*) FROM surgery_cases")
    total = cur.fetchone()[0]

    cur = conn.execute(
        "SELECT urgency, COUNT(*) FROM surgery_cases GROUP BY urgency ORDER BY urgency"
    )
    urgency_counts = {row[0]: row[1] for row in cur.fetchall()}

    cur = conn.execute(
        "SELECT time_bucket, COUNT(*) FROM surgery_cases GROUP BY time_bucket ORDER BY time_bucket"
    )
    time_buckets = {row[0]: row[1] for row in cur.fetchall()}

    cur = conn.execute(
        "SELECT status, COUNT(*) FROM surgery_cases GROUP BY status ORDER BY status"
    )
    status_counts = {row[0]: row[1] for row in cur.fetchall()}

    print("Total cases:", total)
    print("By urgency:", urgency_counts)
    print("By time bucket:", time_buckets)
    print("By status:", status_counts)


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="OR registry schema migration tool")
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Print aggregate counts after ensuring the schema",
    )
    parser.add_argument(
        "--insert-samples",
        action="store_true",
        help="Insert sample elective/emergency cases for verification",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    conn = sqlite3.connect(str(DB_PATH))
    try:
        ensure_schema(conn)
        if args.insert_samples:
            insert_sample_cases(conn)
        if args.diagnostics:
            diagnostics(conn)
        else:
            conn.commit()
            print("✅ DB migrated/ready.")
    finally:
        conn.close()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
