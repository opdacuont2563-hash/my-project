"""Migration utilities for consolidating OR registry data."""
from __future__ import annotations

import argparse
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, Tuple

from utils_time_windows import decide_service_window

DB_PATH = Path.cwd() / "or_registry.sqlite3"

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS surgery_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL UNIQUE,
    or_room TEXT,
    hn TEXT NOT NULL,
    patient_name TEXT NOT NULL,
    age INTEGER,
    diagnosis TEXT,
    operation TEXT,
    surgeon TEXT,
    ward TEXT,
    case_size TEXT,
    department TEXT,
    start_time TEXT,
    end_time TEXT,
    urgency TEXT NOT NULL CHECK (urgency IN ('Elective','Emergency')),
    service_window TEXT NOT NULL CHECK (service_window IN ('InHours','OutOfHours')),
    assist1 TEXT,
    assist2 TEXT,
    scrub TEXT,
    cir TEXT,
    status TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled','in-progress','done','cancelled','postponed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

TIME_SLOT_MAP: Dict[str, str] = {
    "ในเวลา": "Elective",
    "เช้า": "Elective",
    "บ่าย": "Elective",
    "นอกเวลา": "Emergency",
    "ดึก": "Emergency",
    "OT": "Emergency",
    "ฉุกเฉิน": "Emergency",
}


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)


def _parse_datetime(date_text: str | None, time_text: str | None) -> datetime | None:
    if not date_text or not time_text:
        return None
    try:
        if len(date_text.split("-")) == 3:
            base = datetime.fromisoformat(date_text)
        else:
            base = datetime.strptime(date_text, "%Y-%m-%d")
    except Exception:
        try:
            base = datetime.strptime(date_text, "%d/%m/%Y")
        except Exception:
            return None
    try:
        hour, minute = [int(part) for part in time_text.split(":")[:2]]
    except Exception:
        return None
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _decide_urgency(raw: str | None, fallback: str) -> str:
    if raw:
        text = raw.strip().title()
        if text in {"Elective", "Emergency"}:
            return text
    return fallback


def _migrate_rows(conn: sqlite3.Connection, rows: Iterable[Dict[str, object]], default_urgency: str) -> int:
    migrated = 0
    for row in rows:
        urgency = _decide_urgency(str(row.get("urgency", "")), default_urgency)
        if "time_slot" in row and urgency == default_urgency:
            slot = str(row.get("time_slot", "")).strip()
            urgency = TIME_SLOT_MAP.get(slot, urgency)
        start_dt = None
        end_dt = None
        if row.get("time_start_dt"):
            try:
                start_dt = datetime.fromisoformat(str(row.get("time_start_dt")).replace("Z", ""))
            except Exception:
                start_dt = None
        if row.get("time_end_dt"):
            try:
                end_dt = datetime.fromisoformat(str(row.get("time_end_dt")).replace("Z", ""))
            except Exception:
                end_dt = None
        if start_dt is None:
            start_dt = _parse_datetime(str(row.get("date") or row.get("surgery_date")), str(row.get("time_start") or row.get("start_time") or row.get("time")))
        if end_dt is None:
            end_dt = _parse_datetime(str(row.get("date") or row.get("surgery_date")), str(row.get("time_end") or row.get("end_time")))
        if start_dt and not end_dt:
            end_dt = start_dt + timedelta(minutes=60)
        if not (start_dt and end_dt):
            continue
        service_window = decide_service_window(urgency, start_dt, end_dt)
        record_uuid = str(row.get("uuid") or row.get("case_uid") or uuid.uuid4())
        payload = (
            record_uuid,
            row.get("or_room") or row.get("or"),
            row.get("hn") or row.get("patient_id"),
            row.get("name") or row.get("patient_name") or "",
            int(row.get("age") or 0),
            row.get("diagnosis") or "",
            row.get("operation") or "",
            row.get("doctor") or row.get("surgeon") or "",
            row.get("ward") or "",
            row.get("case_size") or "",
            row.get("dept") or row.get("department") or "",
            start_dt.strftime("%Y-%m-%d %H:%M"),
            end_dt.strftime("%Y-%m-%d %H:%M"),
            urgency,
            service_window,
            row.get("assist1") or "",
            row.get("assist2") or "",
            row.get("scrub") or "",
            row.get("cir") or row.get("circulate") or "",
            row.get("status") or "scheduled",
        )
        conn.execute(
            """
            INSERT INTO surgery_cases (
                uuid, or_room, hn, patient_name, age, diagnosis, operation,
                surgeon, ward, case_size, department, start_time, end_time,
                urgency, service_window, assist1, assist2, scrub, cir, status, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, datetime('now'))
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
                assist1=excluded.assist1,
                assist2=excluded.assist2,
                scrub=excluded.scrub,
                cir=excluded.cir,
                status=excluded.status,
                updated_at=datetime('now')
            """,
            payload,
        )
        migrated += 1
    return migrated


def migrate_legacy() -> int:
    total = 0
    conn = sqlite3.connect(str(DB_PATH))
    try:
        ensure_schema(conn)
        conn.execute("BEGIN")
        legacy_pairs: Tuple[Tuple[Path, str], ...] = (
            (Path.cwd() / "schedule_elective.db", "Elective"),
            (Path.cwd() / "schedule_emergency.db", "Emergency"),
        )
        for path, default_urgency in legacy_pairs:
            if not path.exists():
                continue
            try:
                conn.execute("DETACH DATABASE legacy")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ATTACH DATABASE ? AS legacy", (str(path),))
                cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schedule'")
                if cur.fetchone():
                    info = conn.execute("PRAGMA legacy.table_info(schedule)").fetchall()
                    columns = [col[1] for col in info]
                    rows = [dict(zip(columns, r)) for r in conn.execute("SELECT * FROM legacy.schedule").fetchall()]
                    total += _migrate_rows(conn, rows, default_urgency)
            finally:
                try:
                    conn.execute("DETACH DATABASE legacy")
                except sqlite3.OperationalError:
                    pass
        postop_legacy = Path.cwd() / "ornbh_postop.sqlite3"
        if postop_legacy.exists():
            try:
                conn.execute("ATTACH DATABASE ? AS postop", (str(postop_legacy),))
                info = conn.execute("PRAGMA postop.table_info(postop_records)").fetchall()
                if info:
                    columns = [col[1] for col in info]
                    rows = [dict(zip(columns, r)) for r in conn.execute("SELECT * FROM postop.postop_records").fetchall()]
                    total += _migrate_rows(conn, rows, "Elective")
            finally:
                try:
                    conn.execute("DETACH DATABASE postop")
                except sqlite3.OperationalError:
                    pass
        conn.commit()
    finally:
        conn.close()
    return total


def run_diagnostics(insert_samples: bool = True) -> None:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        ensure_schema(conn)
        cur = conn.execute("SELECT COUNT(*), SUM(CASE WHEN urgency='Elective' THEN 1 ELSE 0 END), SUM(CASE WHEN urgency='Emergency' THEN 1 ELSE 0 END) FROM surgery_cases")
        total, elective, emergency = cur.fetchone()
        cur = conn.execute("SELECT SUM(CASE WHEN service_window='InHours' THEN 1 ELSE 0 END), SUM(CASE WHEN service_window='OutOfHours' THEN 1 ELSE 0 END) FROM surgery_cases")
        in_hours, out_hours = cur.fetchone()
        print(f"Total cases: {total}")
        print(f"Elective: {elective or 0} | Emergency: {emergency or 0}")
        print(f"InHours: {in_hours or 0} | OutOfHours: {out_hours or 0}")
        if insert_samples:
            now = datetime.now().replace(minute=30, second=0, microsecond=0)
            elective_uuid = str(uuid.uuid4())
            emergency_uuid = str(uuid.uuid4())
            elective_start = now.replace(hour=9)
            elective_end = elective_start + timedelta(hours=2)
            emergency_start = now.replace(hour=20)
            emergency_end = emergency_start + timedelta(hours=1, minutes=30)
            samples = [
                {
                    "uuid": elective_uuid,
                    "or_room": "OR1",
                    "hn": "TEST001",
                    "patient_name": "Sample Elective",
                    "age": 30,
                    "diagnosis": "DX",
                    "operation": "OP",
                    "surgeon": "Dr. Elective",
                    "ward": "Ward A",
                    "case_size": "Minor",
                    "department": "Surgery",
                    "start": elective_start,
                    "end": elective_end,
                    "urgency": "Elective",
                },
                {
                    "uuid": emergency_uuid,
                    "or_room": "OR2",
                    "hn": "TEST002",
                    "patient_name": "Sample Emergency",
                    "age": 55,
                    "diagnosis": "Trauma",
                    "operation": "Fixation",
                    "surgeon": "Dr. Emergency",
                    "ward": "Ward B",
                    "case_size": "Major",
                    "department": "Orthopedics",
                    "start": emergency_start,
                    "end": emergency_end,
                    "urgency": "Emergency",
                },
            ]
            for sample in samples:
                service_window = decide_service_window(sample["urgency"], sample["start"], sample["end"])
                conn.execute(
                    """
                    INSERT OR REPLACE INTO surgery_cases (
                        uuid, or_room, hn, patient_name, age, diagnosis, operation,
                        surgeon, ward, case_size, department, start_time, end_time,
                        urgency, service_window, status, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, datetime('now'))
                    """,
                    (
                        sample["uuid"],
                        sample["or_room"],
                        sample["hn"],
                        sample["patient_name"],
                        sample["age"],
                        sample["diagnosis"],
                        sample["operation"],
                        sample["surgeon"],
                        sample["ward"],
                        sample["case_size"],
                        sample["department"],
                        sample["start"].strftime("%Y-%m-%d %H:%M"),
                        sample["end"].strftime("%Y-%m-%d %H:%M"),
                        sample["urgency"],
                        service_window,
                        "scheduled",
                    ),
                )
            conn.commit()
            for sample in samples:
                cur = conn.execute("SELECT uuid, urgency, service_window, start_time, end_time FROM surgery_cases WHERE uuid=?", (sample["uuid"],))
                print("Inserted sample:", cur.fetchone())
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="OR registry migration helpers")
    parser.add_argument("action", choices=["migrate", "diagnostics"], help="Action to perform")
    parser.add_argument("--no-samples", dest="samples", action="store_false", default=True, help="Skip inserting sample rows during diagnostics")
    args = parser.parse_args()
    if args.action == "migrate":
        migrated = migrate_legacy()
        print(f"Migrated {migrated} records into {DB_PATH}")
    else:
        run_diagnostics(insert_samples=args.samples)


if __name__ == "__main__":
    main()
