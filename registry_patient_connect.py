# -*- coding: utf-8 -*-
"""
registry_patient_connect.py  — Result Schedule + Runner Dispatch (v2, roles + roster)

อัปเกรดตามคำขอ:
- เพิ่ม "ทะเบียนเวรเปล" (Runner Master) และ "Roster รายกะ" (P1,P2,P3,Outer)
- นโยบายจัดคิวตามบทบาท/ช่วงกะ:
    * จ-ศ เวรเช้า 08:30–16:30 → base order = [P3, P1, P2] (Outer = fallback)
    * จ-ศ เวรบ่าย 16:30–00:30 → base order = [P1, P2] (Outer = fallback)
    * จ-ศ เวรดึก 00:30–08:30 → base order = [P1]
    * ส-อา/นักขัตฤกษ์ เช้า → [P1]; บ่าย → [P1, P2]; ดึก → [P1]
- เครื่องยนต์ Fair-Dispatch (RR) แบบ "policy-aware": ข้ามคน busy, เคารพ base order,
  และคง pointer ต่อกะเพื่อความยุติธรรม
- แบนเนอร์สำหรับพยาบาล: บอกชัดว่า "มือ 1 / 2 / 3" และ "คิวถัดไป (Next 3)"
- มุมมอง Runner: ดึงตะกร้างานต่อคนจาก RunnerBoard เพื่อให้แต่ละคนเปิดดูได้ว่า
  มีงานอะไรที่ "รอรับ/กำลังไปรับ/ถึง OR" ของตัวเอง
- Hook ใช้งานง่ายกับ UI เดิม (ไม่ผูก PySide6): ฟังก์ชัน PUBLIC API พร้อมใช้งาน

ผู้พัฒนา: NBHPY helper
"""
from __future__ import annotations

import os
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, date
from typing import Callable, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------
RETURNING_GRACE_SEC = int(os.getenv("RETURNING_GRACE_SEC", "180"))  # 3 นาที
TURNOVER_BUFFER_MIN = int(os.getenv("TURNOVER_BUFFER_MIN", "12"))   # buffer เปลี่ยนห้อง

# เดิม: ชื่อเริ่มต้นทั้งหมด (ใช้เป็น Master ถ้ายังไม่ตั้งค่า)
DEFAULT_RUNNERS: List[str] = [
    "นาที",
    "อนุพันธ์",
    "กฤษณพงษ์",
    "จีระวัฒน์",
    "นัฐพงษ์",
    "ศราวุธ",
    "รัตนพล",
    "อนุพงษ์",
]

ROSTER_FILE = os.getenv("RUNNER_ROSTER_FILE", "runner_roster.json")

# สถานะบน Runner board ที่ถือว่า "งานอยู่บนมือแล้ว/บนบอร์ดแล้ว"
RUNNER_PUSHED_STATES = {"waiting", "picking", "arrived"}

# ---------------------------------------------------------------------
# ENUMS & MODELS
# ---------------------------------------------------------------------


class SurgeryStatus(str):
    WAITING = "WAITING"
    IN_SURGERY = "IN_SURGERY"
    RECOVERY = "RECOVERY"
    RETURNING = "RETURNING"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"
    DONE = "DONE"


@dataclass
class ScheduleEntry:
    case_id: str
    hn: str
    name: str
    age: Optional[int] = None
    diagnosis: str = ""
    operation: str = ""
    surgeon: str = ""
    ward: str = ""
    or_room: str = ""
    schedule_time: Optional[datetime] = None
    expected_duration_min: int = 60
    status: str = SurgeryStatus.WAITING
    # timestamps
    start_time: Optional[datetime] = None
    finish_time: Optional[datetime] = None
    recovery_start: Optional[datetime] = None
    returning_started_at: Optional[datetime] = None
    returned_to_ward_at: Optional[datetime] = None
    done_time: Optional[datetime] = None
    # aux
    assist1: str = ""
    assist2: str = ""
    scrub: str = ""
    cir: str = ""
    dept: str = ""
    size: str = ""
    # internal flags
    pushed_to_runner: bool = False
    extra: Dict = field(default_factory=dict)


# ---------------------------------------------------------------------
# ROSTER / ROLES
# ---------------------------------------------------------------------


class RosterStore:
    """จัดการทะเบียนเวรเปล (master + roster รายกะ) บนไฟล์ JSON."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or ROSTER_FILE
        self.data = self._load_or_init()

    def _load_or_init(self) -> Dict:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    if isinstance(d, dict):
                        return d
            except Exception:
                pass
        d = {
            "master": list(DEFAULT_RUNNERS),
            "shift_pointers": {},
            "roster": {},
        }
        self._save(d)
        return d

    def _save(self, d: Optional[Dict] = None) -> None:
        if d is not None:
            self.data = d
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    # --- Master list ---
    def set_master(self, names: List[str]) -> None:
        clean: List[str] = []
        seen: Set[str] = set()
        for name in names:
            s = (name or "").strip()
            if s and s not in seen:
                clean.append(s)
                seen.add(s)
        if not clean:
            clean = list(DEFAULT_RUNNERS)
        self.data["master"] = clean
        self._save()

    def get_master(self) -> List[str]:
        return list(self.data.get("master", []))

    # --- Roster per shift key ---
    def set_shift(self, key: str, P1: str = "", P2: str = "", P3: str = "", OUTER: str = "") -> None:
        key = str(key)
        roster = self.data.get("roster", {})
        roster[key] = {"P1": P1, "P2": P2, "P3": P3, "OUTER": OUTER}
        self.data["roster"] = roster
        self._save()

    def get_shift(self, key: str) -> Dict[str, str]:
        roster = self.data.get("roster", {})
        r = roster.get(key) or {}
        return {
            "P1": r.get("P1", ""),
            "P2": r.get("P2", ""),
            "P3": r.get("P3", ""),
            "OUTER": r.get("OUTER", ""),
        }

    # --- RR pointer per shift ---
    def get_ptr(self, key: str) -> int:
        try:
            return int(self.data.get("shift_pointers", {}).get(key, 0))
        except Exception:
            return 0

    def set_ptr(self, key: str, idx: int) -> None:
        pointers = self.data.get("shift_pointers", {})
        pointers[key] = int(idx)
        self.data["shift_pointers"] = pointers
        self._save()


# ---------------------------------------------------------------------
# SHIFT RULES
# ---------------------------------------------------------------------


def is_holiday_today(dt: Optional[datetime] = None) -> bool:
    dt = dt or datetime.now()
    return dt.weekday() >= 5  # เสาร์-อาทิตย์ถือเป็นวันหยุด


def shift_key_now(dt: Optional[datetime] = None) -> str:
    dt = dt or datetime.now()
    hhmm = int(dt.strftime("%H%M"))
    if 830 <= hhmm < 1630:
        base = "morning"
    elif 1630 <= hhmm < 2400:
        base = "evening"
    else:
        base = "night"
    return f"holiday_{base}" if is_holiday_today(dt) else base


def base_role_order(shift_key: str) -> List[str]:
    if shift_key == "morning":
        return ["P3", "P1", "P2"]
    if shift_key == "evening":
        return ["P1", "P2"]
    if shift_key == "night":
        return ["P1"]
    if shift_key == "holiday_morning":
        return ["P1"]
    if shift_key == "holiday_evening":
        return ["P1", "P2"]
    if shift_key == "holiday_night":
        return ["P1"]
    return ["P1", "P2", "P3"]


# ---------------------------------------------------------------------
# RUNNER BOARD (Mockable)
# ---------------------------------------------------------------------


class RunnerBoard:
    def __init__(self):
        self._store: Dict[str, Dict] = {}

    def fetch_status_map(self) -> Dict[str, Dict]:
        return dict(self._store)

    def push_entries(self, entries: List[ScheduleEntry]) -> Tuple[bool, List[str]]:
        errs: List[str] = []
        for entry in entries:
            pid = pickup_id_for_entry(entry)
            if pid in self._store and self._store[pid]["status"] in RUNNER_PUSHED_STATES:
                continue
            self._store[pid] = {
                "status": "waiting",
                "assignee": None,
                "payload": asdict(entry),
            }
        return True, errs

    def ack(self, pickup_id: str, runner_name: str) -> None:
        if pickup_id not in self._store:
            self._store[pickup_id] = {"status": "waiting", "assignee": None, "payload": {}}
        self._store[pickup_id]["assignee"] = runner_name
        self._store[pickup_id]["status"] = "picking"


# ---------------------------------------------------------------------
# UTILS
# ---------------------------------------------------------------------


def fmt_hhmm(dt: Optional[datetime]) -> str:
    if not dt:
        return "-"
    return dt.strftime("%H:%M")


def format_countdown(delta: timedelta) -> str:
    secs = max(0, int(delta.total_seconds()))
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    seconds = secs % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def compute_eta(entry: ScheduleEntry) -> Tuple[Optional[datetime], Optional[str]]:
    now = datetime.now()
    if entry.status == SurgeryStatus.WAITING:
        if entry.schedule_time:
            return entry.schedule_time, format_countdown(entry.schedule_time - now)
        return None, None
    if entry.status == SurgeryStatus.IN_SURGERY:
        if not entry.start_time:
            return None, None
        eta = entry.start_time + timedelta(minutes=entry.expected_duration_min)
        if (now - entry.start_time).total_seconds() > entry.expected_duration_min * 60:
            eta = now + timedelta(seconds=int(entry.expected_duration_min * 60 * 0.15))
        return eta, format_countdown(eta - now)
    if entry.status == SurgeryStatus.RECOVERY:
        if entry.finish_time:
            eta = entry.finish_time + timedelta(minutes=TURNOVER_BUFFER_MIN)
            return eta, format_countdown(eta - now)
        return None, None
    if entry.status == SurgeryStatus.RETURNING:
        if entry.returning_started_at:
            eta = entry.returning_started_at + timedelta(seconds=RETURNING_GRACE_SEC)
            return eta, format_countdown(eta - now)
        return None, None
    return None, None


def close_case(entry: ScheduleEntry) -> None:
    now = datetime.now()
    entry.status = SurgeryStatus.DONE
    entry.done_time = now
    entry.returned_to_ward_at = entry.returned_to_ward_at or now


def pickup_id_for_entry(entry: ScheduleEntry, override_or: Optional[str] = None) -> str:
    or_code = (override_or or entry.or_room or "-").strip()
    day_str = entry.schedule_time.strftime("%Y%m%d") if entry.schedule_time else date.today().strftime("%Y%m%d")
    return f"{or_code}-{day_str}-{entry.case_id}"


# ---------------------------------------------------------------------
# DISPATCH ENGINE
# ---------------------------------------------------------------------


class DispatchEngine:
    def __init__(self, roster: Optional[RosterStore] = None, board: Optional[RunnerBoard] = None):
        self.roster = roster or RosterStore()
        self.board = board or RunnerBoard()

    def busy_names(self) -> Set[str]:
        busy: Set[str] = set()
        for row in self.board.fetch_status_map().values():
            name = str(row.get("assignee") or "").strip()
            status = str(row.get("status") or "").strip().lower()
            if name and status in RUNNER_PUSHED_STATES:
                busy.add(name)
        return busy

    def _names_by_role(self, shift_key: str) -> Dict[str, str]:
        roster = self.roster.get_shift(shift_key)
        if any(roster.values()):
            return roster
        master = self.roster.get_master()
        mapped = {"P1": "", "P2": "", "P3": "", "OUTER": ""}
        for role, idx in zip(["P1", "P2", "P3", "OUTER"], range(4)):
            mapped[role] = master[idx] if idx < len(master) else ""
        return mapped

    def next_runner(self, shift_key: Optional[str] = None) -> Optional[str]:
        key = shift_key or shift_key_now()
        names_by_role = self._names_by_role(key)
        order = base_role_order(key)
        busy = self.busy_names()

        main = [names_by_role.get(role, "") for role in order if names_by_role.get(role, "")]
        outer = names_by_role.get("OUTER", "")

        if not main and not outer:
            main = self.roster.get_master()

        ptr = self.roster.get_ptr(key)
        n = len(main)
        if n == 0:
            return outer or None

        for i in range(n):
            idx = (ptr + i) % n
            cand = main[idx]
            if cand and cand not in busy:
                self.roster.set_ptr(key, idx + 1)
                return cand

        if outer and outer not in busy:
            self.roster.set_ptr(key, (ptr + 1) % n if n else 0)
            return outer

        self.roster.set_ptr(key, (ptr + 1) % n if n else 0)
        return main[ptr % n] if n else (outer or None)

    def peek_next_k(self, k: int = 3, shift_key: Optional[str] = None) -> List[str]:
        key = shift_key or shift_key_now()
        names_by_role = self._names_by_role(key)
        order = base_role_order(key)
        busy = self.busy_names()

        main = [names_by_role.get(role, "") for role in order if names_by_role.get(role, "")]
        outer = names_by_role.get("OUTER", "")

        if not main and not outer:
            main = self.roster.get_master()

        ptr = self.roster.get_ptr(key)
        n = len(main)
        results: List[str] = []
        seen: Set[str] = set()

        for i in range(n * 2 if n else 1):
            if len(results) >= k:
                break
            idx = (ptr + i) % max(1, n)
            cand = main[idx] if n else outer
            if not cand or cand in seen or cand in busy:
                continue
            results.append(cand)
            seen.add(cand)

        if len(results) < k and outer and outer not in busy and outer not in seen:
            results.append(outer)

        return results


# ---------------------------------------------------------------------
# PUBLIC API — การเปลี่ยนสถานะ/Auto close/Auto dispatch
# ---------------------------------------------------------------------


def apply_transition(entry: ScheduleEntry, event: str, at: Optional[datetime] = None) -> None:
    at = at or datetime.now()
    if event == "start_surgery" and entry.status in {SurgeryStatus.WAITING}:
        entry.status = SurgeryStatus.IN_SURGERY
        entry.start_time = at
    elif event == "finish_surgery" and entry.status == SurgeryStatus.IN_SURGERY:
        entry.status = SurgeryStatus.RECOVERY
        entry.finish_time = at
        entry.recovery_start = at
    elif event == "start_return" and entry.status in {SurgeryStatus.RECOVERY}:
        entry.status = SurgeryStatus.RETURNING
        entry.returning_started_at = at
    elif event == "postpone":
        entry.status = SurgeryStatus.POSTPONED
    elif event == "cancel":
        entry.status = SurgeryStatus.CANCELLED


def is_entry_completed(entry: ScheduleEntry) -> bool:
    return bool(entry.finish_time)


def tick_returning_cron(
    entries: List[ScheduleEntry],
    engine: DispatchEngine,
    on_db_insert: Optional[Callable[[ScheduleEntry], None]] = None,
    on_banner: Optional[Callable[[str, ScheduleEntry], None]] = None,
) -> None:
    """
    เรียกเป็นระยะ (30–60s):
    - ถ้า entry อยู่ใน RETURNING ครบ 3 นาที → ปิดเคส + on_db_insert()
    - แล้ว auto-dispatch เคสถัดไปตามกะ/บทบาท
    """
    now = datetime.now()

    for entry in entries:
        if entry.status != SurgeryStatus.RETURNING or not entry.returning_started_at:
            continue
        if (now - entry.returning_started_at).total_seconds() < RETURNING_GRACE_SEC:
            continue

        entry.returned_to_ward_at = entry.returned_to_ward_at or now
        if is_entry_completed(entry):
            close_case(entry)
            if on_db_insert:
                on_db_insert(entry)
            if on_banner:
                on_banner("ok", entry)
            try:
                auto_dispatch_after_return(entries, entry, engine)
            except Exception as exc:
                if on_banner:
                    on_banner(f"warn: {exc}", entry)
        else:
            if on_banner:
                on_banner("postop_pending", entry)


def pick_next_waiting_case(entries: List[ScheduleEntry], board: RunnerBoard) -> Optional[ScheduleEntry]:
    status_map = board.fetch_status_map()

    def pushed(entry: ScheduleEntry) -> bool:
        pid = pickup_id_for_entry(entry)
        row = status_map.get(pid)
        if not row:
            return False
        status = str(row.get("status") or "").strip().lower()
        return status in RUNNER_PUSHED_STATES

    candidates: List[ScheduleEntry] = []
    for entry in entries:
        if entry.status in {SurgeryStatus.WAITING, SurgeryStatus.IN_SURGERY, SurgeryStatus.RECOVERY} and not pushed(entry):
            candidates.append(entry)

    if not candidates:
        return None

    def sort_key(entry: ScheduleEntry) -> str:
        if entry.schedule_time:
            return entry.schedule_time.strftime("%H%M")
        return "9999"

    candidates.sort(key=sort_key)
    return candidates[0]


def auto_dispatch_after_return(entries: List[ScheduleEntry], just_returned: ScheduleEntry, engine: DispatchEngine) -> None:
    board = engine.board
    next_case = pick_next_waiting_case(entries, board)
    if not next_case:
        return

    ok, _ = board.push_entries([next_case])
    if not ok:
        return

    runner = engine.next_runner()
    if runner:
        pid = pickup_id_for_entry(next_case)
        board.ack(pid, runner)
    next_case.pushed_to_runner = True


# ---------------------------------------------------------------------
# Nurse/Runner Facing Helpers
# ---------------------------------------------------------------------


def nurse_roster_banner(engine: DispatchEngine, when: Optional[datetime] = None) -> Dict:
    key = shift_key_now(when or datetime.now())
    roles = engine._names_by_role(key)
    return {
        "shift_key": key,
        "roles": roles,
        "base_order": base_role_order(key),
        "next3": engine.peek_next_k(3, key),
        "busy": sorted(engine.busy_names()),
    }


def runner_inboxes(engine: DispatchEngine) -> Dict[str, List[Dict]]:
    out: Dict[str, List[Dict]] = {}
    for pid, row in engine.board.fetch_status_map().items():
        who = str(row.get("assignee") or "").strip() or "-"
        payload = dict(row.get("payload") or {})
        item = {
            "pickup_id": pid,
            "status": str(row.get("status") or ""),
            "hn": payload.get("hn") or payload.get("HN") or "",
            "name": payload.get("name") or payload.get("patient") or "",
            "or": payload.get("or_room") or payload.get("or") or "",
            "ward": payload.get("ward") or payload.get("ward_from") or "",
        }
        out.setdefault(who, []).append(item)
    return out


__all__ = [
    "ScheduleEntry",
    "SurgeryStatus",
    "RosterStore",
    "DispatchEngine",
    "RunnerBoard",
    "RETURNING_GRACE_SEC",
    "DEFAULT_RUNNERS",
    "ROSTER_FILE",
    "RUNNER_PUSHED_STATES",
    "apply_transition",
    "compute_eta",
    "close_case",
    "fmt_hhmm",
    "format_countdown",
    "tick_returning_cron",
    "auto_dispatch_after_return",
    "pick_next_waiting_case",
    "pickup_id_for_entry",
    "nurse_roster_banner",
    "runner_inboxes",
    "shift_key_now",
    "base_role_order",
]
