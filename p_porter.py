# -*- coding: utf-8 -*-
"""
P-Porter: Patient-Porter Dispatch System (Flask + SQLite, LAN-only deployment)
-----------------------------------------------------------------------------
- Entities: PorterProfile (porters), PorterStats, DailyRoster, Tasks, ShiftState
- Shift policies (weekday/weekend) + special rules:
  * Weekday Morning (08:30–16:30): roles = เปล 1, เปล 2, เปล 3  (first job -> เปล 3 if available)
  * Weekend  Morning (08:30–16:30): roles = เปล 1 (one porter)
  * Afternoon (16:30–00:30): roles = เปล 1, เปล 2, รอบนอก  (outer helps only if both mains unavailable)
  * Night     (00:30–08:30): roles = เปล 1 (one porter)
- Fairness Dispatcher: tasks_assigned_count -> last_available_time -> proximity
- Optional schedule DB integration (lookup name/ward by HN) if available.
- Designed for hospital LAN; keep behind firewall/VPN.

Run server:
    python p_porter.py

Environment vars (optional, for testing/demo):
    PPORTER_PORT=5005
    PPORTER_DB=p_porter.db
    REGISTRY_SCHEDULE_ELECTIVE=./schedule_elective.db
    REGISTRY_SCHEDULE_EMERGENCY=./schedule_emergency.db
    PPORTER_FORCE_SHIFT=Morning|Afternoon|Night
    PPORTER_FORCE_WEEKDAY=1
"""

from __future__ import annotations
import os, sqlite3, json
from datetime import datetime, date, time
from typing import Dict, Any, Optional, Tuple, List

from flask import Flask, jsonify, request, abort

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
APP_PORT = int(os.getenv("PPORTER_PORT", "5005"))
DB_PATH   = os.getenv("PPORTER_DB", "p_porter.db")

SCHEDULE_DB_PATHS = [
    os.getenv("REGISTRY_SCHEDULE_ELECTIVE", "schedule_elective.db"),
    os.getenv("REGISTRY_SCHEDULE_EMERGENCY", "schedule_emergency.db"),
]

# Proximity map (lower is nearer to OR Area)
PROXIMITY_TO_OR: Dict[str, int] = {
    "OR Area": 0,
    "หอผู้ป่วย ICU รวม": 1,
    "หอผู้ป่วยศัลยกรรมหญิง": 2,
    "หอผู้ป่วยศัลยกรรมชาย": 2,
    "หอผู้ป่วยศัลยกรรมกระดูกและข้อ": 3,
    "หอผู้ป่วยพิเศษศัลยกรรม ชั้น 4": 3,
    "หอผู้ป่วยพิเศษอายุรกรรม ชั้น 5": 4,
}
DEFAULT_PROXIMITY = 5

# ----------------------------------------------------------------------------
# Shift definitions & flags
# ----------------------------------------------------------------------------
FORCE_WEEKDAY = os.getenv("PPORTER_FORCE_WEEKDAY", "0") == "1"   # test only
FORCE_MORNING = os.getenv("PPORTER_FORCE_MORNING", "0") == "1"   # backward-compat test
FORCE_SHIFT   = os.getenv("PPORTER_FORCE_SHIFT")                 # 'Morning'|'Afternoon'|'Night'|None

SHIFT_DEFS = [
    {"name": "Morning",   "start": time(8, 30),  "end": time(16, 30)},  # 08:30–16:30
    {"name": "Afternoon", "start": time(16, 30), "end": time(0, 30)},   # 16:30–00:30 (wrap)
    {"name": "Night",     "start": time(0, 30),  "end": time(8, 30)},   # 00:30–08:30
]

# Roles policy per shift (weekday/weekend)
ROLES_WEEKDAY = {
    "Morning":   ["เปล 1", "เปล 2", "เปล 3"],       # first job → เปล 3
    "Afternoon": ["เปล 1", "เปล 2", "รอบนอก"],
    "Night":     ["เปล 1"],
}
ROLES_WEEKEND = {
    "Morning":   ["เปล 1"],                          # weekend morning = one porter
    "Afternoon": ["เปล 1", "เปล 2", "รอบนอก"],
    "Night":     ["เปล 1"],
}

# ----------------------------------------------------------------------------
# App / DB helpers
# ----------------------------------------------------------------------------
app = Flask(__name__)

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.executescript("""
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS porters(
            porter_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT,
            last_area TEXT DEFAULT 'OR Area',
            status TEXT DEFAULT 'Available', -- Available | Busy
            last_available_time TEXT
        );

        CREATE TABLE IF NOT EXISTS porter_stats(
            porter_id TEXT PRIMARY KEY,
            tasks_assigned_count INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(porter_id) REFERENCES porters(porter_id)
        );

        CREATE TABLE IF NOT EXISTS daily_roster(
            date TEXT NOT NULL,
            shift TEXT NOT NULL,
            role TEXT NOT NULL,          -- เปล 1 | เปล 2 | เปล 3 | รอบนอก
            porter_id TEXT NOT NULL,
            PRIMARY KEY(date, shift, role),
            FOREIGN KEY(porter_id) REFERENCES porters(porter_id)
        );

        CREATE TABLE IF NOT EXISTS tasks(
            task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            hn TEXT,
            patient_name TEXT,
            target_ward TEXT,
            source_area TEXT DEFAULT 'OR Area',
            task_type TEXT NOT NULL,     -- OR_to_WARD | WARD_to_OR
            status TEXT NOT NULL,        -- New|Dispatched|Accepted|InProgress|Completed|Cancelled
            assigned_porter_id TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(assigned_porter_id) REFERENCES porters(porter_id)
        );

        CREATE TABLE IF NOT EXISTS shift_state(
            date TEXT NOT NULL,
            shift TEXT NOT NULL,
            first_job_assigned INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(date, shift)
        );
    """)
    conn.commit()
    conn.close()

def seed_porters_if_empty() -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM porters")
    cnt = cur.fetchone()[0]
    if cnt and cnt > 0:
        conn.close()
        return
    names = [
        "นาที", "อนุพันธ์", "กฤษณพงษ์", "จีระวัฒน์",
        "นัฐพงษ์", "ศราวุธ", "รัตนพล", "อนุพงษ์",
    ]
    for i, name in enumerate(names, start=1):
        pid = f"P{i:02d}"
        cur.execute(
            "INSERT INTO porters(porter_id, name, role, last_area, status, last_available_time) "
            "VALUES(?, ?, NULL, 'OR Area', 'Available', ?)",
            (pid, name, iso_now()),
        )
        cur.execute(
            "INSERT OR IGNORE INTO porter_stats(porter_id, tasks_assigned_count) VALUES(?, 0)",
            (pid,),
        )
    conn.commit()
    conn.close()

# ----------------------------------------------------------------------------
# Utils
# ----------------------------------------------------------------------------
def today_str() -> str:
    return date.today().strftime("%Y-%m-%d")

def iso_now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

def is_weekday(d: Optional[date] = None) -> bool:
    if FORCE_WEEKDAY:
        return True
    d = d or date.today()
    return d.weekday() < 5  # Mon..Fri

def _time_in_range(t: time, start: time, end: time) -> bool:
    if end > start:
        return start <= t < end
    return t >= start or t < end  # wrap across midnight

def get_current_shift_info(now: Optional[datetime] = None) -> Tuple[str, str]:
    now = now or datetime.now()
    if FORCE_SHIFT in {"Morning", "Afternoon", "Night"}:
        return FORCE_SHIFT, now.strftime("%Y-%m-%d")
    t = now.time()
    for s in SHIFT_DEFS:
        if _time_in_range(t, s["start"], s["end"]):
            return s["name"], now.strftime("%Y-%m-%d")
    return "Morning", now.strftime("%Y-%m-%d")

def expected_roles(weekday: bool, shift_name: str) -> List[str]:
    policy = ROLES_WEEKDAY if weekday else ROLES_WEEKEND
    return policy.get(shift_name, ["เปล 1"])

def in_morning_shift(now: Optional[datetime] = None) -> bool:
    if FORCE_MORNING:
        return True
    shift, _ = get_current_shift_info(now)
    return shift == "Morning"

def proximity_score(area: Optional[str]) -> int:
    if not area:
        return DEFAULT_PROXIMITY
    return PROXIMITY_TO_OR.get(area, DEFAULT_PROXIMITY)

# ----------------------------------------------------------------------------
# Optional: Integration with schedule DBs (if present)
# ----------------------------------------------------------------------------
def lookup_patient_from_schedule(hn: str) -> Tuple[Optional[str], Optional[str]]:
    if not hn:
        return (None, None)
    for path in SCHEDULE_DB_PATHS:
        if not path or not os.path.exists(path):
            continue
        try:
            c = sqlite3.connect(path)
            c.row_factory = sqlite3.Row
            cur = c.cursor()
            cur.execute(
                "SELECT name, ward, date FROM schedule WHERE hn=? AND date=? ORDER BY id DESC LIMIT 1",
                (hn, today_str()),
            )
            row = cur.fetchone()
            if not row:
                cur.execute(
                    "SELECT name, ward, date FROM schedule WHERE hn=? ORDER BY id DESC LIMIT 1",
                    (hn,),
                )
                row = cur.fetchone()
            c.close()
            if row:
                return (row["name"], row["ward"])
        except Exception:
            pass
    return (None, None)

# ----------------------------------------------------------------------------
# Ward aliases / normalization
# ----------------------------------------------------------------------------
WARD_ALIASES = {
    "หอผ้ป่วย ICU รวม": "หอผู้ป่วย ICU รวม",
    "ICU รวม": "หอผู้ป่วย ICU รวม",
}
def normalize_ward(w: Optional[str]) -> Optional[str]:
    if not w:
        return w
    return WARD_ALIASES.get(w, w)

# ----------------------------------------------------------------------------
# Dispatcher
# ----------------------------------------------------------------------------
def dispatch_or_to_ward(new_task: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
    """
    Smart dispatcher for OR→WARD respecting shift policies.
    Steps:
      - Filter: rostered & Available for current shift
      - Weekday Morning: first job → เปล 3 (if available)
      - Afternoon: prefer main roles (เปล 1, เปล 2); use 'รอบนอก' only if both mains unavailable
      - Tie-breakers: tasks_assigned_count → last_available_time → proximity
    """
    conn = get_db()
    cur = conn.cursor()
    shift_name, shift_date = get_current_shift_info()

    # roster of this shift
    cur.execute(
        "SELECT role, porter_id FROM daily_roster WHERE date=? AND shift=?",
        (shift_date, shift_name),
    )
    roster = {r["role"]: r["porter_id"] for r in cur.fetchall()}
    if not roster:
        conn.close()
        return {"ok": False, "reason": "Roster not set for this shift"}

    def query_available(ids: List[str]) -> List[Dict[str, Any]]:
        ids = [i for i in ids if i]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        q = f"""
        SELECT p.porter_id, p.name, p.role, p.last_area, p.status, p.last_available_time,
               COALESCE(s.tasks_assigned_count,0) AS cnt
          FROM porters p
          LEFT JOIN porter_stats s ON s.porter_id = p.porter_id
         WHERE p.porter_id IN ({placeholders}) AND p.status='Available'
        """
        cur.execute(q, ids)
        return [dict(row) for row in cur.fetchall()]

    # build candidates per shift rules
    if shift_name == "Afternoon":
        main_ids = [pid for r, pid in roster.items() if r in ("เปล 1", "เปล 2")]
        outer_id = [roster.get("รอบนอก")] if roster.get("รอบนอก") else []
        candidates = query_available(main_ids)
        if not candidates:
            candidates = query_available(outer_id)
    else:
        candidates = query_available(list(roster.values()))

    if not candidates:
        conn.close()
        return {"ok": False, "reason": "No Available porter"}

    chosen: Optional[Dict[str, Any]] = None

    # Weekday-Morning first job → เปล 3
    now = datetime.now()
    if shift_name == "Morning" and is_weekday(now.date()):
        cur.execute(
            "SELECT first_job_assigned FROM shift_state WHERE date=? AND shift=?",
            (shift_date, shift_name),
        )
        row = cur.fetchone()
        first_done = bool(row[0]) if row else False
        if not first_done:
            pid_pref = roster.get("เปล 3")
            if pid_pref:
                for c in candidates:
                    if c["porter_id"] == pid_pref:
                        chosen = c
                        cur.execute(
                            "INSERT INTO shift_state(date,shift,first_job_assigned) VALUES(?,?,1) "
                            "ON CONFLICT(date,shift) DO UPDATE SET first_job_assigned=1",
                            (shift_date, shift_name),
                        )
                        break

    # Fairness & tie-breakers
    if not chosen:
        def key_fn(c: Dict[str, Any]):
            try:
                ts = datetime.fromisoformat(c.get("last_available_time") or "1970-01-01T00:00:00")
            except Exception:
                ts = datetime(1970, 1, 1)
            prox = proximity_score(c.get("last_area"))
            return (int(c.get("cnt", 0)), ts, prox, c.get("porter_id"))
        candidates.sort(key=key_fn)
        chosen = candidates[0]

    porter_id = chosen["porter_id"]
    cur.execute(
        "UPDATE tasks SET assigned_porter_id=?, status='Dispatched', updated_at=? WHERE task_id=?",
        (porter_id, iso_now(), new_task["task_id"]),
    )
    cur.execute(
        "INSERT INTO porter_stats(porter_id, tasks_assigned_count) VALUES(?, 1) "
        "ON CONFLICT(porter_id) DO UPDATE SET tasks_assigned_count = tasks_assigned_count + 1",
        (porter_id,),
    )
    conn.commit()
    conn.close()

    print(f"[Dispatcher] Assign task#{new_task['task_id']} to {porter_id} ({chosen['name']})")
    print(f"[Push→Porter] 📲 {chosen['name']} รับเคสใหม่: HN {new_task['hn']} → {new_task['target_ward']}")
    print(f"[Notify→Ward] 🏥 แจ้งวอร์ด {new_task['target_ward']} ว่ามีเปล {chosen['name']} ไปรับผู้ป่วยจาก OR")

    return {"ok": True, "assigned_porter_id": porter_id, "porter_name": chosen["name"]}

# ----------------------------------------------------------------------------
# API Endpoints
# ----------------------------------------------------------------------------
@app.get("/api/health")
def api_health():
    return jsonify({"ok": True, "time": iso_now()})

@app.get("/")
def root():
    return jsonify({
        "ok": True,
        "service": "P-Porter",
        "time": iso_now(),
        "endpoints": [
            "/api/health",
            "/api/porters",
            "POST /api/porters/add",
            "POST /api/porters/update",
            "/api/roster/today?shift=Morning|Afternoon|Night",
            "POST /api/roster/set",
            "POST /api/request_move",
            "/api/tasks",
            "POST /api/task/<id>/accept",
            "POST /api/task/<id>/complete",
            "/api/config/proximity"
        ]
    })

@app.get("/favicon.ico")
def favicon():
    return ("", 204)

@app.get("/api/porters")
def api_porters_list():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM porters ORDER BY porter_id")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)

@app.post("/api/porters/add")
def api_porters_add():
    payload = request.get_json(force=True) or {}
    name = str(payload.get("name") or "").strip()
    if not name:
        abort(400, "name required")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT porter_id FROM porters ORDER BY porter_id DESC LIMIT 1")
    row = cur.fetchone()
    next_num = int(row["porter_id"][1:]) + 1 if row else 1
    new_id = f"P{next_num:02d}"
    cur.execute(
        "INSERT INTO porters(porter_id,name,role,last_area,status,last_available_time) "
        "VALUES(?, ?, NULL, 'OR Area', 'Available', ?)",
        (new_id, name, iso_now()),
    )
    cur.execute("INSERT INTO porter_stats(porter_id,tasks_assigned_count) VALUES(?,0)", (new_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "porter_id": new_id, "name": name})

@app.post("/api/porters/update")
def api_porters_update():
    payload = request.get_json(force=True) or {}
    pid = (payload.get("porter_id") or "").strip()
    name = (payload.get("name") or "").strip()
    if not pid or not name:
        abort(400, "porter_id and name required")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE porters SET name=? WHERE porter_id=?", (name, pid))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "porter_id": pid, "name": name})

@app.post("/api/roster/set")
def api_roster_set():
    """
    Set roster for a shift.
    Forms:
      (A) Backward compatible (no shift key) -> applies to current shift
          {"เปล 1":"P01","เปล 2":"P02","เปล 3":"P03"}
      (B) Explicit: {"shift":"Afternoon","mapping":{"เปล 1":"P01","เปล 2":"P02","รอบนอก":"P08"}}
    """
    payload = request.get_json(force=True) or {}
    if "mapping" in payload or "shift" in payload:
        shift_name = (payload.get("shift") or "").strip() or get_current_shift_info()[0]
        mapping = payload.get("mapping") or {}
    else:
        shift_name, _ = get_current_shift_info()
        mapping = payload

    wd = is_weekday()
    required = expected_roles(wd, shift_name)
    missing = [r for r in required if r not in mapping]
    if missing:
        abort(400, f"missing role(s): {', '.join(missing)}")

    shift_name, shift_date = get_current_shift_info()
    conn = get_db()
    cur = conn.cursor()

    # Clear all role labels (simple approach)
    cur.execute("UPDATE porters SET role=NULL")

    for role, pid in mapping.items():
        cur.execute(
            "INSERT INTO daily_roster(date,shift,role,porter_id) VALUES(?,?,?,?) "
            "ON CONFLICT(date,shift,role) DO UPDATE SET porter_id=excluded.porter_id",
            (shift_date, shift_name, role, pid),
        )
        cur.execute(
            "UPDATE porters SET role=?, status='Available', last_available_time=? WHERE porter_id=?",
            (role, iso_now(), pid),
        )
        cur.execute("INSERT OR IGNORE INTO porter_stats(porter_id,tasks_assigned_count) VALUES(?,0)", (pid,))
        cur.execute("UPDATE porter_stats SET tasks_assigned_count=0 WHERE porter_id=?", (pid,))

    cur.execute(
        "INSERT INTO shift_state(date,shift,first_job_assigned) VALUES(?, ?, 0) "
        "ON CONFLICT(date,shift) DO UPDATE SET first_job_assigned=0",
        (shift_date, shift_name),
    )
    conn.commit()
    conn.close()

    print(f"[Roster] {shift_date} {shift_name} → {json.dumps(mapping, ensure_ascii=False)}")
    return jsonify({"ok": True, "date": shift_date, "shift": shift_name, "roster": mapping})

@app.get("/api/roster/today")
def api_roster_today():
    # Optional: ?shift=Morning|Afternoon|Night ; default = current shift
    arg_shift = (request.args.get("shift") or "").strip()
    if arg_shift:
        shift_name = arg_shift
        shift_date = today_str()
    else:
        shift_name, shift_date = get_current_shift_info()

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT role, porter_id FROM daily_roster WHERE date=? AND shift=? ORDER BY role",
        (shift_date, shift_name),
    )
    data = {r["role"]: r["porter_id"] for r in cur.fetchall()}
    conn.close()
    return jsonify({"date": shift_date, "shift": shift_name, "roster": data})

@app.post("/api/request_move")
def api_request_move():
    payload = request.get_json(force=True) or {}
    task_type = str(payload.get("task_type") or "").strip() or "OR_to_WARD"
    if task_type not in ("OR_to_WARD", "WARD_to_OR"):
        abort(400, "invalid task_type")
    hn = str(payload.get("hn") or "").strip()
    target_ward = str(payload.get("target_ward") or "").strip()
    patient_name = str(payload.get("patient_name") or "").strip()

    # Autofill from schedule DBs when possible
    if (not patient_name or not target_ward) and hn:
        name2, ward2 = lookup_patient_from_schedule(hn)
        patient_name = patient_name or (name2 or "")
        target_ward = target_ward or (ward2 or "")

    target_ward = normalize_ward(target_ward)

    if not hn:
        abort(400, "hn required")
    if task_type == "OR_to_WARD" and not target_ward:
        abort(400, "target_ward required for OR_to_WARD")

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tasks(hn,patient_name,target_ward,source_area,task_type,status,assigned_porter_id,created_at,updated_at) "
        "VALUES(?,?,?,?, ?, 'New', NULL, ?, ?)",
        (hn, patient_name, target_ward or None, 'OR Area', task_type, iso_now(), iso_now()),
    )
    task_id = cur.lastrowid
    cur.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,))
    new_task = cur.fetchone()
    conn.commit()
    conn.close()

    result = dispatch_or_to_ward(new_task)
    return jsonify({"task_id": task_id, **result})

@app.post("/api/task/<int:task_id>/accept")
def api_task_accept(task_id: int):
    payload = request.get_json(force=True) or {}
    porter_id = str(payload.get("porter_id") or "").strip()
    if not porter_id:
        abort(400, "porter_id required")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT assigned_porter_id, status FROM tasks WHERE task_id=?", (task_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        abort(404, "task not found")
    if row["assigned_porter_id"] != porter_id:
        conn.close()
        abort(403, "not assignee")

    cur.execute("UPDATE tasks SET status='Accepted', updated_at=? WHERE task_id=?", (iso_now(), task_id))
    cur.execute("UPDATE porters SET status='Busy' WHERE porter_id=?", (porter_id,))
    conn.commit()
    conn.close()

    print(f"[Porter Action] {porter_id} accepted task#{task_id}")
    return jsonify({"ok": True})

@app.post("/api/task/<int:task_id>/complete")
def api_task_complete(task_id: int):
    payload = request.get_json(force=True) or {}
    porter_id = str(payload.get("porter_id") or "").strip()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT assigned_porter_id, target_ward, task_type FROM tasks WHERE task_id=?", (task_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        abort(404, "task not found")
    assigned = row["assigned_porter_id"]
    target_ward = row["target_ward"]
    task_type = row["task_type"]
    if porter_id and assigned and porter_id != assigned:
        conn.close()
        abort(403, "not assignee")

    # Complete task, free porter, update last_area + last_available_time
    cur.execute("UPDATE tasks SET status='Completed', updated_at=? WHERE task_id=?", (iso_now(), task_id))
    if assigned:
        last_area = "OR Area" if task_type == "WARD_to_OR" else (target_ward or "OR Area")
        cur.execute(
            "UPDATE porters SET status='Available', last_area=?, last_available_time=? WHERE porter_id=?",
            (last_area, iso_now(), assigned),
        )
    conn.commit()
    conn.close()

    print(f"[Porter Action] {assigned or porter_id or '-'} completed task#{task_id} at {target_ward}")
    return jsonify({"ok": True, "last_area": target_ward})

@app.get("/api/tasks")
def api_tasks_list():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT t.*, p.name as porter_name FROM tasks t "
        "LEFT JOIN porters p ON p.porter_id = t.assigned_porter_id "
        "ORDER BY t.task_id DESC"
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)

@app.get("/api/config/proximity")
def api_proximity():
    return jsonify(PROXIMITY_TO_OR)

# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    seed_porters_if_empty()
    print("P-Porter — Flask started (LAN mode).")
    print("Porters seeded:")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT porter_id, name FROM porters ORDER BY porter_id")
    for row in cur.fetchall():
        print("  ", row["porter_id"], row["name"])
    conn.close()
    print("\nTry the API root → http://127.0.0.1:%d/" % APP_PORT)
    app.run(host="0.0.0.0", port=APP_PORT, debug=False)
