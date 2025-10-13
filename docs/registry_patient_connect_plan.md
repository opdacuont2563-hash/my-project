# Registry Patient Connect — ORNBH (Describe & Task)

## Describe (วางในช่อง Describe ของ PR/Issue ได้ทันที)
Registry Patient Connect — ORNBH เป็นแอปเดสก์ท็อป PySide6 สำหรับ “ลงทะเบียน/จัดคิวผ่าตัด” ที่เชื่อมต่อจอ Monitor แบบเรียลไทม์และเก็บข้อมูลไว้บนฐานข้อมูลภายในเครื่องอย่างปลอดภัย แอปมุ่งเน้น UX ที่อ่านง่ายและตอบสนองไวเพื่อให้ทีม OR/วอร์ดเห็นสถานะคิว ช่วยลดความผิดพลาด ลดเวลาค้นหาเคส และต่อยอดได้ทั้งงาน QI และ Clinical Analytics ภายใต้ข้อกำกับ PDPA

เวอร์ชันนี้เน้น
- ปรับโทน UI ทันสมัย เพิ่มคอมโพเนนต์ค้นหา/เลือก ICD และ Operation พร้อมคำแนะนำตามสาขา
- รองรับการจัดคิวแบบ "เลขคิว 1–9" หรือ "ตามเวลา" จากตารางผลลัพธ์
- ปรับ logic ขีดฆ่า (strike-through) ให้ทำงานเฉพาะเคสที่ “เคยเห็นใน Monitor มาก่อน” และหายจาก Monitor พร้อมทั้งบันทึกข้อมูลหลังผ่าตัดครบ (เวลาเริ่ม/จบ + บทบาทพยาบาล)
- เพิ่ม Local logging ด้วย SQLite + ลำดับ QSettings sync เพื่อแชร์ค่าระหว่างหลายอินสแตนซ์
- วางโครงเตรียมวิเคราะห์ต่อ ด้วยตารางเชิงโครงสร้าง และเส้นทาง “สรุปแบบไม่ระบุตัวตน (de-identified)” สำหรับงาน QI/วิจัย

เป้าหมายคุณภาพ
- ลดความผิดพลาดการนัด OR ลดเวลาค้นหาเคส และช่วยทีมเห็นภาระงาน/เวลารอแบบเรียลไทม์
- สร้างเส้นทางข้อมูลเพื่อวิเคราะห์ระยะเวลาผ่าตัดจริง turnaround utilization ของ OR และงานพยาบาลต่อเคส เพื่ออัปเดต KPI

## Task (แตกงานเป็น Checklist ทำได้เป็น Sprint)
### A. Core (MVP)
- [ ] ย้าย `LocalDBLogger` ไปใช้ ORM (SQLAlchemy) พร้อมสคีมาตามด้านล่างและเพิ่ม Alembic migration
- [ ] จัดการคอนฟิก/ความลับด้วย `pydantic-settings` และเก็บคีย์เข้ารหัสผ่าน OS Keyring
- [ ] เปิดฟีเจอร์ Export (de-identified) เป็น CSV/Parquet พร้อม hash HN ด้วย salt
- [ ] แยกชั้น Data/Domain/GUI ด้วย service layer สำหรับการอ่าน/เขียน schedule + events
- [ ] เพิ่ม unit tests (pytest) + lint (ruff) + type-check (mypy)

### B. Security & PDPA
- [ ] เข้ารหัสฐานข้อมูล (SQLite + SQLCipher หรือ Postgres + pgcrypto) หรืออย่างน้อยเข้ารหัสฟิลด์อ่อนไหว (ชื่อ, HN)
- [ ] ทำ role-based access (อย่างต่ำ OR nurse/registrar และ Admin/QI) พร้อม PIN/Password lock หน้าจอ
- [ ] แสดง Consent & Notice: แบนเนอร์ PDPA สรุปวัตถุประสงค์/Retention/สิทธิ์
- [ ] ทำ audit log (ใครทำอะไรเมื่อไร) โดยเก็บเฉพาะ metadata ที่จำเป็น (data minimization)
- [ ] Redact logs ให้ไม่มี HN/ชื่อจริง

### C. Analytics & QI
- [ ] เพิ่มตาราง Event (start/end/arrived/leave PACU) สำหรับคำนวณ duration/turnover/delay
- [ ] สร้างแดชบอร์ดเบื้องต้นแบบออฟไลน์ด้วย DuckDB/Pandas (CSV/HTML)
- [ ] คำนวณ metric ตัวอย่าง: OR utilization, on-time start %, average case duration by specialty/doctor, PACU LOS

### D. Realtime/Integration
- [ ] เพิ่มเสถียรภาพ WebSocket ด้วย auto-reconnect + backoff และ health indicator ใน UI
- [ ] แยก service layer สำหรับ monitor provider (HTTP/WS) เพื่อสลับ backend ได้ง่าย

## ข้อเสนอ Tech Stack + ไลบรารี
- **ภาษา/รันไทม์**: Python 3.11+
- **Desktop/UI**: PySide6 (ต่อยอดจากของเดิม), qasync (ถ้าต้องผสาน asyncio/WS กับ event loop), QtAwesome หรือ SVG icons เบา ๆ
- **Data/ORM/ETL**: SQLAlchemy + Alembic, SQLite (dev/edge) + SQLCipher (production) หรือ PostgreSQL + pgcrypto, Pydantic/pydantic-settings, Pandas หรือ Polars + DuckDB สำหรับงานวิเคราะห์
- **Security**: cryptography สำหรับฟิลด์เข้ารหัส, keyring เก็บคีย์, python-dotenv สำหรับ dev, structlog/loguru เพื่อทำ logging พร้อม redaction
- **API/Realtime**: FastAPI + websockets/uvicorn สำหรับบริการเสริม, httpx/requests ฝั่ง client
- **Packaging/Quality**: ruff + black + mypy + pytest, pyinstaller สำหรับแจกจ่ายภายใน

## แบบร่างสถาปัตยกรรม
```
+------------------------+       +--------------------+
|  PySide6 Presentation  |<----->|  Service Layer     |
|  (หน้าลงทะเบียน/คิว) |       |  (Schedule & Event |
|                        |       |   Facade, Monitor  |
+-----------+------------+       |   Adapter)         |
            |                    +---------+----------+
            |                              |
            v                              v
+--------------------+        +-----------------------------+
| Domain Models      |        | Data Layer (SQLAlchemy ORM) |
| (Case, Patient,    |<------>| + Encryption Helpers        |
|  Staff, Event)     |        | + Local/Remote DB           |
+--------------------+        +---------------+-------------+
                                                |
                                                v
                                    +----------------------+
                                    | Analytics Pipelines  |
                                    | (DuckDB/Pandas,      |
                                    |  de-identified views)|
                                    +----------------------+
```

## สคีมา (ย่อ)
- `patient`: id, hn_enc (unique, encrypted), name_enc, age, sex, ward, created_at
- `or_room`: id, code
- `staff`: id, full_name_enc, role (doctor/scrub/assist/circulate)
- `case`: id, patient_id, or_room_id, dept, doctor_id, scheduled_date/time, period, queue, time_start/end, assist/scrub/circulate ids
- `case_diag`: case_id, text (รองรับหลายรายการ)
- `case_op`: case_id, text
- `event_log`: id, case_id, event_type (created/updated/start/end/pacu_in/pacu_out/etc.), at
- มุมมอง `v_case_anonymized`: case_id, hn_hash (SHA-256(HN + SALT)), dept, doctor_role_only, scheduled_dt, start_dt, end_dt, duration_min, queue, period, or_code, age_band

> หลักการ PDPA: เก็บให้น้อยที่สุด แยกตารางผู้ป่วย (PHI) ออกจากข้อมูลทางคลินิก และสร้าง view แบบ de-identified สำหรับงานวิเคราะห์ โดยเก็บ salt ใน keyring/secret ไม่ push ลง Git

## โค้ดตัวอย่าง (สั้น กระชับ ต่อกับโค้ดเดิมได้ทันที)
```python
# config.py
from pydantic_settings import BaseSettings
import keyring, secrets

SERVICE = "ORNBH_SurgiBot"

class Settings(BaseSettings):
    db_url: str = "sqlite:///./schedule.db"  # production: sqlite+pysqlcipher://... หรือ postgres://
    hn_hash_salt_key: str = "hn_salt"

    class Config:
        env_file = ".env"

settings = Settings()


def get_secret(name: str) -> str:
    value = keyring.get_password(SERVICE, name)
    if not value:
        value = secrets.token_hex(32)  # dev-only bootstrap
        keyring.set_password(SERVICE, name, value)
    return value
```

```python
# logging_setup.py
import logging

SENSITIVE_KEYS = {"hn", "name", "patient"}


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for key in SENSITIVE_KEYS:
            msg = msg.replace(key, f"{key}[*]")
        record.msg = msg
        return True


logger = logging.getLogger("ornbh")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.addFilter(RedactFilter())
logger.addHandler(handler)
```

```python
# db.py
from datetime import datetime
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Time,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

engine = create_engine("sqlite:///./schedule.db", future=True)
SessionLocal = sessionmaker(engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


class Patient(Base):
    __tablename__ = "patient"
    id = Column(Integer, primary_key=True)
    hn_enc = Column(String, unique=True, index=True)
    name_enc = Column(String)
    age = Column(Integer)
    ward = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class ORRoom(Base):
    __tablename__ = "or_room"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True)


class Staff(Base):
    __tablename__ = "staff"
    id = Column(Integer, primary_key=True)
    full_name_enc = Column(String)
    role = Column(String)


class Case(Base):
    __tablename__ = "case"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patient.id"))
    or_room_id = Column(Integer, ForeignKey("or_room.id"))
    dept = Column(String)
    doctor_id = Column(Integer, ForeignKey("staff.id"))
    scheduled_date = Column(Date)
    scheduled_time = Column(Time)
    period = Column(String)
    queue = Column(Integer, default=0)
    time_start = Column(Time, nullable=True)
    time_end = Column(Time, nullable=True)

    patient = relationship("Patient")
    or_room = relationship("ORRoom")
    doctor = relationship("Staff", foreign_keys=[doctor_id])


class CaseDiag(Base):
    __tablename__ = "case_diag"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("case.id"))
    text = Column(String)


class CaseOp(Base):
    __tablename__ = "case_op"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("case.id"))
    text = Column(String)


def init_db() -> None:
    Base.metadata.create_all(engine)
```

```python
# crypto_utils.py
import base64
from hashlib import sha256
from cryptography.fernet import Fernet

from config import get_secret


def _fernet() -> Fernet:
    key_hex = get_secret("fernet_key")
    key_bytes = key_hex.encode()
    if len(key_bytes) != 44:
        # สร้าง base64 urlsafe key จากความลับ 32 ไบต์แรก
        key_bytes = base64.urlsafe_b64encode(key_bytes[:32])
    return Fernet(key_bytes)


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def hn_hash(hn: str) -> str:
    salt = get_secret("hn_salt")
    return sha256((hn + salt).encode()).hexdigest()
```

```python
# export_anonymized.py
import pandas as pd
from sqlalchemy.orm import joinedload

from crypto_utils import decrypt, hn_hash
from db import Case, ORRoom, Patient, SessionLocal


def export_cases_csv(path: str = "cases_deid.csv") -> None:
    with SessionLocal() as session:
        cases = (
            session.query(Case)
            .options(joinedload(Case.patient), joinedload(Case.or_room))
            .all()
        )

    rows = []
    for case in cases:
        try:
            hn_plain = decrypt(case.patient.hn_enc)
        except Exception:  # ป้องกันข้อมูลเสีย
            hn_plain = ""

        rows.append(
            {
                "case_id": case.id,
                "hn_hash": hn_hash(hn_plain) if hn_plain else None,
                "dept": case.dept,
                "or_code": case.or_room.code,
                "period": case.period,
                "queue": case.queue,
                "scheduled_date": str(case.scheduled_date),
                "scheduled_time": str(case.scheduled_time),
                "time_start": str(case.time_start) if case.time_start else None,
                "time_end": str(case.time_end) if case.time_end else None,
            }
        )

    df = pd.DataFrame(rows)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    # df.to_parquet("cases_deid.parquet") ได้เช่นกัน
```

## แนวทาง PDPA/ความปลอดภัย
- Data minimization: เก็บ PHI เฉพาะเท่าที่จำเป็น แยกตาราง `patient` ออกจาก `case` และใช้ view de-identified สำหรับ analytics
- Encryption at rest: ใช้ SQLCipher หรือ PostgreSQL + pgcrypto; หากยังไม่พร้อมให้เข้ารหัสฟิลด์สำคัญ (ชื่อ, HN) ด้วย `cryptography`
- Access control: PIN/Password ก่อนเข้าแอป + timeout ล็อกหน้าจอ และ role-based access ขั้นต่ำ 2 ระดับ
- Audit log: บันทึกเหตุการณ์ (create/update/delete/export) พร้อม user/time โดยไม่เก็บค่า PHI ใน log
- Consent/Notice: แสดงแบนเนอร์ PDPA ระบุวัตถุประสงค์, retention, สิทธิ์ผู้ป่วย และคู่มือการติดต่อ DPO
- Data retention: กำหนดรอบการลบ/ทำลายข้อมูลจากเครื่องภายในหลังสรุปรายงานหรือส่งต่อสำเร็จ
- Secure config: เก็บ token/secret ใน keyring หรือ vault ไม่ hard-code; ใช้ `.env` เฉพาะ dev และไม่ push สู่ Git
- Logging hygiene: ทำ redaction สำหรับ HN/ชื่อก่อนบันทึกลงไฟล์ log หรือระบบแจ้งเตือน
