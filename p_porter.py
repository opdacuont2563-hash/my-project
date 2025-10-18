# -*- coding: utf-8 -*-
"""
P-Porter — Patient-Porter Dispatch System (LAN-only mock)

- Python 3 (Flask) + SQLite
- Fair, proximity-aware dispatcher for OR -> Ward transfers
- Designed for weekday Morning shift having 3 porters: เปล 1, เปล 2, เปล 3
  with เปล 3 given FIRST pick when all else ties.
- Includes in-file console mockups and a demo() that uses Flask test_client
  to simulate the workflow from roster set -> request move -> accept -> complete.

Run:
  python p_porter.py            # start API server (http://127.0.0.1:5007)
  python p_porter.py --demo     # run the demo flow (no server)

Author: NBHPY
"""

from __future__ import annotations
import os, sqlite3, json, argparse, threading, time
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from flask import Flask, request, jsonify, g

# --------------------------- Config ---------------------------

DB_PATH = os.environ.get("P_PORTER_DB", "p_porter.db")
APP = Flask(__name__)

# Proximity score from last_area to OR (lower = nearer to OR)
# Feel free to adjust for your hospital topology.
PROXIMITY_TO_OR: Dict[str, int] = {
    "OR Area": 0,
    "หอผู้ป่วย ICU รวม": 1,
    "หอผู้ป่วยพิเศษศัลยกรรม ชั้น 4": 1,
    "หอผู้ป่วยพิเศษอายุรกรรม ชั้น 4": 2,
    "หอผู้ป่วยศัลยกรรมชาย": 2,
    "หอผู้ป่วยศัลยกรรมหญิง": 2,
    "หอผู้ป่วยพิเศษอายุรกรรม ชั้น 5": 3,
    "หอผู้ป่วยศัลยกรรมกระดูกและข้อ": 3,
    "Default": 9,
}

ROLE_PRIORITY = {"เปล 3": 0, "เปล 1": 1, "เปล 2": 2}  # เปล 3 เป็นคิว 1 (tie-breaker)


# --------------------------- DB helpers ---------------------------

def conn() -> sqlite3.Connection:
    # Use Flask 'g' if in app context; otherwise keep a module-level fallback connection.
    from flask import has_app_context
    if has_app_context():
        if "db" not in g:
            g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
            g.db.row_factory = sqlite3.Row
        return g.db
    # Fallback for CLI/demo segments executed outside requests
    global _global_db_conn
    try:
        _global_db_conn
    except NameError:
        _global_db_conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
        _global_db_conn.row_factory = sqlite3.Row
    return _global_db_conn

@APP.teardown_appcontext
def teardown(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db(reset: bool = False):
    c = conn()
    if reset:
        for t in ("porter_profile","patient_move_task","daily_roster","porter_stats"):
            c.execute(f"DROP TABLE IF EXISTS {t}")
        c.commit()

    c.execute("""
    CREATE TABLE IF NOT EXISTS porter_profile(
        porter_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        role TEXT DEFAULT NULL,              -- today's assigned role (เปล 1/2/3) if any
        last_area TEXT DEFAULT 'OR Area',
        status TEXT DEFAULT 'Available',     -- Available/Busy
        last_available_time TEXT             -- ISO datetime
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS patient_move_task(
        task_id INTEGER PRIMARY KEY AUTOINCREMENT,
        hn TEXT,
        patient_name TEXT,
        target_ward TEXT,
        source_area TEXT,
        task_type TEXT,                      -- OR_to_WARD / WARD_to_OR
        status TEXT,                         -- Pending/Assigned/InProgress/Completed
        assigned_porter_id TEXT,
        created_at TEXT,
        accepted_at TEXT,
        completed_at TEXT
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS daily_roster(
        date TEXT,                           -- YYYY-MM-DD
        shift TEXT,                          -- Morning (we focus this)
        role TEXT,                           -- เปล 1/เปล 2/เปล 3
        porter_id TEXT,
        PRIMARY KEY(date, shift, role)
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS porter_stats(
        porter_id TEXT PRIMARY KEY,
        tasks_assigned_count INTEGER DEFAULT 0
    )
    """)
    c.commit()

def _fmt_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _iso_date_today() -> str:
    return date.today().strftime("%Y-%m-%d")

def _weekday_morning(dt: Optional[datetime]=None) -> bool:
    dt = dt or datetime.now()
    is_weekday = dt.weekday() < 5  # Mon-Fri
    is_morning = 6 <= dt.hour < 14  # tweakable
    return is_weekday and is_morning

def _ensure_porter_stats(pid: str):
    c = conn()
    r = c.execute("SELECT 1 FROM porter_stats WHERE porter_id=?", (pid,)).fetchone()
    if not r:
        c.execute("INSERT OR IGNORE INTO porter_stats(porter_id, tasks_assigned_count) VALUES(?,0)", (pid,))
        c.commit()

def _next_porter_id() -> str:
    c = conn()
    r = c.execute("SELECT porter_id FROM porter_profile ORDER BY porter_id DESC LIMIT 1").fetchone()
    if not r:
        return "P01"
    last = str(r["porter_id"]).upper().replace("P","")
    try:
        n = int(last) + 1
    except Exception:
        n = 1
    return f"P{n:02d}"

# --------------------------- Seed / Maintenance ---------------------------

DEFAULT_PORTER_NAMES = [
    "นาที","อนุพันธ์","กฤษณพงษ์","จีระวัฒน์","นัฐพงษ์","ศราวุธ","รัตนพล","อนุพงษ์"
]

def seed_porters(names: List[str] = DEFAULT_PORTER_NAMES):
    c = conn()
    for name in names:
        # skip if exists
        r = c.execute("SELECT porter_id FROM porter_profile WHERE name=?", (name,)).fetchone()
        if r: 
            _ensure_porter_stats(r["porter_id"])
            continue
        pid = _next_porter_id()
        c.execute("""
            INSERT INTO porter_profile(porter_id, name, role, last_area, status, last_available_time)
            VALUES(?,?,NULL,'OR Area','Available',?)
        """,(pid, name, _fmt_now()))
        _ensure_porter_stats(pid)
    c.commit()

# --------------------------- Dispatcher ---------------------------

def _proximity_score(area: Optional[str]) -> int:
    if not area:
        return PROXIMITY_TO_OR["Default"]
    return PROXIMITY_TO_OR.get(area, PROXIMITY_TO_OR["Default"])

def dispatch_or_to_ward(task_row: sqlite3.Row) -> Optional[str]:
    """
    Smart dispatcher for OR -> WARD tasks.
    Returns assigned porter_id or None.
    """
    c = conn()
    today = _iso_date_today()
    # 1) Filter — Available and rostered today (Morning)
    rows = c.execute("""
        SELECT p.porter_id, p.name, p.role, p.last_area, p.status, p.last_available_time,
               COALESCE(s.tasks_assigned_count,0) AS cnt
        FROM porter_profile p
        JOIN daily_roster r ON r.porter_id = p.porter_id
        LEFT JOIN porter_stats s ON s.porter_id = p.porter_id
        WHERE p.status='Available' AND r.date=? AND r.shift='Morning'
    """,(today,)).fetchall()

    if not rows:
        print("🚫 Dispatcher: ไม่มีเปลว่างในกะนี้ (หรือยังไม่ได้ตั้งเวร)")
        return None

    # 2) Sort — fairness (cnt), time (older first), proximity (lower), role priority (เปล3 first)
    def parse_time(t: Optional[str]) -> float:
        if not t: 
            return 0.0
        try:
            return datetime.fromisoformat(t).timestamp()
        except Exception:
            try:
                return datetime.strptime(t, "%Y-%m-%d %H:%M:%S").timestamp()
            except Exception:
                return 0.0

    def sort_key(r: sqlite3.Row) -> Tuple[int,float,int,int]:
        cnt = int(r["cnt"] or 0)
        last_avail_ts = parse_time(r["last_available_time"])
        prox = _proximity_score(r["last_area"])
        role_bias = ROLE_PRIORITY.get(r["role"] or "", 9)
        return (cnt, last_avail_ts, prox, role_bias)

    ranked = sorted(rows, key=sort_key)
    chosen = ranked[0]
    pid = chosen["porter_id"]

    # 3) Assign & Update
    c.execute("UPDATE patient_move_task SET status='Assigned', assigned_porter_id=? WHERE task_id=?", (pid, task_row["task_id"]))
    c.execute("UPDATE porter_stats SET tasks_assigned_count=COALESCE(tasks_assigned_count,0)+1 WHERE porter_id=?", (pid,))
    c.commit()

    # 4) Notifications (mock)
    print(f"🔔 [WARD Notification] มอบหมายให้ '{chosen['name']}' ({chosen['role']}) ไปรับผู้ป่วย HN {task_row['hn']} ที่ OR -> {task_row['target_ward']}")
    print(f"📣 [Porter App] งานใหม่สำหรับ {chosen['name']} ({pid}) — ไปรับ HN {task_row['hn']} ส่งไป {task_row['target_ward']} (tap เพื่อ Accept)")
    return pid

# --------------------------- API ---------------------------

@APP.route("/api/porters", methods=["GET"])
def list_porters():
    rows = conn().execute("SELECT * FROM porter_profile ORDER BY porter_id").fetchall()
    return jsonify([dict(r) for r in rows])

@APP.route("/api/porters/add", methods=["POST"])
def add_porter():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error":"name is required"}), 400
    c = conn()
    r = c.execute("SELECT porter_id FROM porter_profile WHERE name=?", (name,)).fetchone()
    if r:
        return jsonify({"message":"exists","porter_id": r["porter_id"]})
    pid = _next_porter_id()
    c.execute("""
        INSERT INTO porter_profile(porter_id,name,role,last_area,status,last_available_time)
        VALUES(?,?,NULL,'OR Area','Available',?)
    """,(pid, name, _fmt_now()))
    _ensure_porter_stats(pid)
    c.commit()
    return jsonify({"message":"ok","porter_id":pid,"name":name})

@APP.route("/api/roster/set", methods=["POST"])
def set_roster():
    """
    Payload examples:
    {
      "shift": "Morning",
      "roles": {"เปล 1":"P01","เปล 2":"P02","เปล 3":"P03"}   # you can also send porter names instead of ids
    }
    Weekday-Morning rule: must have 3 roles; เปล 3 gets first pick on ties (role_bias).
    """
    data = request.get_json(force=True, silent=True) or {}
    shift = (data.get("shift") or "Morning").strip()
    roles: Dict[str,str] = data.get("roles") or {}
    today = _iso_date_today()
    if shift != "Morning":
        return jsonify({"error":"Only Morning shift is supported in this mock"}), 400
    if _weekday_morning():
        # enforce 3 porters
        for key in ("เปล 1","เปล 2","เปล 3"):
            if key not in roles:
                return jsonify({"error":f"Weekday Morning ต้องระบุ {key}"}), 400

    # Normalize: map names -> porter_ids if needed
    c = conn()
    normalized: Dict[str,str] = {}
    for role, val in roles.items():
        val = (val or "").strip()
        pid = None
        if val.upper().startswith("P") and val[1:].isdigit():
            pid = val.upper()
        else:
            row = c.execute("SELECT porter_id FROM porter_profile WHERE name=?", (val,)).fetchone()
            if row: pid = row["porter_id"]
        if not pid:
            return jsonify({"error":f"ไม่พบพนักงานสำหรับ '{val}'"}), 400
        normalized[role] = pid

    # Upsert roster and update porter_profile.role
    for role, pid in normalized.items():
        c.execute("""
            INSERT INTO daily_roster(date,shift,role,porter_id)
            VALUES(?,?,?,?)
            ON CONFLICT(date,shift,role) DO UPDATE SET porter_id=excluded.porter_id
        """,(today, shift, role, pid))
    # clear roles first
    c.execute("UPDATE porter_profile SET role=NULL")
    for role, pid in normalized.items():
        c.execute("UPDATE porter_profile SET role=? WHERE porter_id=?", (role, pid))
    c.commit()

    # Console mockup
    print("🗂️ [Roster App] ตั้งเวรเช้า: ", ", ".join([f"{r}→{normalized[r]}" for r in ("เปล 1","เปล 2","เปล 3") if r in normalized]))
    return jsonify({"message":"ok","date":today,"shift":shift,"roles":normalized})

@APP.route("/api/request_move", methods=["POST"])
def request_move():
    """
    OR Nurse call (OR_to_WARD only in this mock)
    Payload: { "task_type":"OR_to_WARD", "hn":"45012345", "patient_name":"นาย ก", "target_ward":"หอผู้ป่วย..." }
    """
    data = request.get_json(force=True, silent=True) or {}
    task_type = (data.get("task_type") or "OR_to_WARD").strip()
    hn = (data.get("hn") or "").strip()
    name = (data.get("patient_name") or "").strip()
    target = (data.get("target_ward") or "").strip()
    if not (hn and target):
        return jsonify({"error":"hn and target_ward are required"}), 400

    c = conn()
    c.execute("""
        INSERT INTO patient_move_task(hn,patient_name,target_ward,source_area,task_type,status,assigned_porter_id,created_at)
        VALUES(?,?,?,?,?,'Pending',NULL,?)
    """,(hn, name, target, "OR Area", task_type, _fmt_now()))
    task_id = c.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    task = c.execute("SELECT * FROM patient_move_task WHERE task_id=?", (task_id,)).fetchone()

    # Console mockup (Caller)
    print(f"📟 [Caller (OR)] เรียกรับส่ง: HN {hn} → {target} (task_id={task_id})")
    # Dispatch
    assigned = dispatch_or_to_ward(task)
    return jsonify({"message":"ok","task_id":task_id,"assigned_porter_id":assigned})

@APP.route("/api/task/<int:task_id>/accept", methods=["POST"])
def accept_task(task_id: int):
    data = request.get_json(force=True, silent=True) or {}
    pid = (data.get("porter_id") or "").strip().upper()
    c = conn()
    task = c.execute("SELECT * FROM patient_move_task WHERE task_id=?", (task_id,)).fetchone()
    if not task:
        return jsonify({"error":"task not found"}), 404
    if task["assigned_porter_id"] and task["assigned_porter_id"] != pid:
        return jsonify({"error":"assigned to another porter"}), 403
    # accept/lock
    c.execute("UPDATE patient_move_task SET status='InProgress', assigned_porter_id=?, accepted_at=? WHERE task_id=?",
              (pid or task["assigned_porter_id"], _fmt_now(), task_id))
    c.execute("UPDATE porter_profile SET status='Busy' WHERE porter_id=?", (pid,))
    c.commit()
    print(f"✅ [Porter App] {pid} กดรับงาน task#{task_id}")
    return jsonify({"message":"ok","task_id":task_id,"porter_id":pid})

@APP.route("/api/task/<int:task_id>/complete", methods=["POST"])
def complete_task(task_id: int):
    c = conn()
    task = c.execute("SELECT * FROM patient_move_task WHERE task_id=?", (task_id,)).fetchone()
    if not task: return jsonify({"error":"task not found"}), 404
    pid = task["assigned_porter_id"]
    if not pid: return jsonify({"error":"task not yet assigned"}), 400

    # update task
    c.execute("UPDATE patient_move_task SET status='Completed', completed_at=? WHERE task_id=?", (_fmt_now(), task_id))
    # update porter availability + last_area
    c.execute("""
        UPDATE porter_profile
           SET status='Available', last_area=?, last_available_time=?
         WHERE porter_id=?
    """,(task["target_ward"], _fmt_now(), pid))
    c.commit()

    # Console mockups
    porter = c.execute("SELECT name, role FROM porter_profile WHERE porter_id=?", (pid,)).fetchone()
    print(f"🏁 [Porter App] {porter['name']} ส่งผู้ป่วยเสร็จที่ {task['target_ward']} (คืนสถานะ Available)")
    print(f"📊 [Dispatcher Log] last_area[{pid}] → {task['target_ward']} (proximity seed for next job)")
    return jsonify({"message":"ok","task_id":task_id})

@APP.route("/api/tasks", methods=["GET"])
def list_tasks():
    rows = conn().execute("SELECT * FROM patient_move_task ORDER BY task_id DESC").fetchall()
    return jsonify([dict(r) for r in rows])

@APP.route("/api/roster/today", methods=["GET"])
def roster_today():
    today = _iso_date_today()
    rows = conn().execute("""
        SELECT r.*, p.name FROM daily_roster r
        LEFT JOIN porter_profile p ON p.porter_id=r.porter_id
        WHERE r.date=? AND r.shift='Morning'
        ORDER BY CASE role WHEN 'เปล 1' THEN 1 WHEN 'เปล 2' THEN 2 WHEN 'เปล 3' THEN 3 ELSE 9 END
    """,(today,)).fetchall()
    return jsonify([dict(r) for r in rows])

# --------------------------- Health & Root ---------------------------
@APP.route("/", methods=["GET"])
def root():
    return (
        "<h1>P-Porter API</h1>"
        "<ul>"
        "<li>GET /health</li>"
        "<li>GET /api/porters</li>"
        "<li>POST /api/porters/add</li>"
        "<li>POST /api/roster/set</li>"
        "<li>GET /api/roster/today</li>"
        "<li>POST /api/request_move</li>"
        "<li>POST /api/task/&lt;id&gt;/accept</li>"
        "<li>POST /api/task/&lt;id&gt;/complete</li>"
        "<li>GET /api/tasks</li>"
        "</ul>",
        200,
        {"Content-Type": "text/html; charset=utf-8"},
    )


@APP.route("/health", methods=["GET"])
def health():
    return {
        "status": "ok",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# --------------------------- Console Mockups / Demo ---------------------------

TODAY_OPERATIONS = [
    # Minimal mock rows derived from the screenshot: (hn, name, dest ward)
    ("450194242", "น.ส.ธิติกานต์ 39", "หอผู้ป่วยพิเศษศัลยกรรม ชั้น 4"),
    ("460234678", "นายสมชาติ 78", "หอผู้ป่วยศัลยกรรมรวมทั่วไปรวม/หอผู้ป่วยพิเศษรวมกันใจ"),  # free text ok
    ("450033779", "นายสุพล 75", "หอผู้ป่วย ICU รวม"),
]

def roster_app_mock():
    today = _iso_date_today()
    rows = conn().execute("""
        SELECT r.role, r.porter_id, p.name
        FROM daily_roster r LEFT JOIN porter_profile p ON p.porter_id=r.porter_id
        WHERE r.date=? AND r.shift='Morning'
        ORDER BY role
    """,(today,)).fetchall()
    print("📋 [Roster App] เวรเช้า (วันนี้)")
    for r in rows:
        print(f"   - {r['role']}: {r['name']} ({r['porter_id']})")

def caller_app_mock():
    print("🖥️ [Caller (OR)] หน้าติดตามงาน")
    rows = conn().execute("""
        SELECT task_id, hn, patient_name, target_ward, status, assigned_porter_id
        FROM patient_move_task ORDER BY task_id
    """).fetchall()
    for r in rows:
        p = (
            conn()
            .execute(
                "SELECT name, last_area FROM porter_profile WHERE porter_id=?",
                (r["assigned_porter_id"],),
            )
            .fetchone()
            if r["assigned_porter_id"]
            else None
        )
        porter_info = f"{p['name']} (last_area: {p['last_area']})" if p else "-"
        print(f"   • task#{r['task_id']} HN {r['hn']} → {r['target_ward']} | status={r['status']} | assigned={porter_info}")

def porter_app_mock():
    rows = conn().execute("SELECT * FROM porter_profile ORDER BY porter_id").fetchall()
    print("📱 [Porter App] สถานะพนักงาน")
    for r in rows:
        print(f"   • {r['name']} ({r['porter_id']}) role={r['role'] or '-'} status={r['status']} last_area={r['last_area']}")

def ward_notification_mock(msg: str):
    print(f"🏥 [Ward Notification] {msg}")

def demo_flow():
    """
    Full workflow demo using Flask's test client (no external HTTP):
    - Seed -> Set roster -> Request 3 moves -> Accept/Complete first -> Request another -> Show fairness rotation
    """
    print("\n===== P-Porter DEMO START =====\n")
    # Ensure app context for DB setup in CLI demo
    with APP.app_context():
        init_db(reset=True)
        seed_porters()

    with APP.test_client() as cli:
        # Set weekday-morning roster: pick any 3 porters from our list.
        roster_payload = {
            "shift":"Morning",
            "roles": { "เปล 1":"นาที", "เปล 2":"อนุพันธ์", "เปล 3":"กฤษณพงษ์" }  # names accepted
        }
        print("-> Set roster:", roster_payload)
        print(cli.post("/api/roster/set", json=roster_payload).json)
        roster_app_mock()
        porter_app_mock()
        print()

        # Request moves (derived from TODAY_OPERATIONS)
        for hn, name, ward in TODAY_OPERATIONS:
            print("-> OR request:", hn, name, ward)
            cli.post("/api/request_move", json={"task_type":"OR_to_WARD","hn":hn,"patient_name":name,"target_ward":ward})
        caller_app_mock()
        print()
        porter_app_mock()
        print()

        # Porter accepts the first task (whoever got assigned first)
        tasks = cli.get("/api/tasks").json
        first = tasks[-1] if tasks else None
        if first:
            pid = first["assigned_porter_id"]
            print(f"-> Porter {pid} ACCEPT task#{first['task_id']}")
            print(cli.post(f"/api/task/{first['task_id']}/accept", json={"porter_id":pid}).json)
            # complete
            print(f"-> Porter {pid} COMPLETE task#{first['task_id']}")
            print(cli.post(f"/api/task/{first['task_id']}/complete").json)
        print()
        porter_app_mock()
        print()

        # Request one more task to see rotation (เปล 3 bias only applies on ties)
        print("-> OR request (new): HN 99999999 -> หอผู้ป่วยศัลยกรรมชาย")
        cli.post("/api/request_move", json={"task_type":"OR_to_WARD","hn":"99999999","patient_name":"นายทดสอบ","target_ward":"หอผู้ป่วยศัลยกรรมชาย"})
        caller_app_mock()
        print()
        porter_app_mock()
        print()

    print("===== P-Porter DEMO END =====\n")

# --------------------------- Entrypoint ---------------------------

def run_server():
    # Push app context before DB set-up when running as a server script
    with APP.app_context():
        init_db()
        seed_porters()  # safe if already inserted
    print("P-Porter is running at http://127.0.0.1:5007")
    APP.run(host="127.0.0.1", port=5007, debug=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="run demo with console mockups instead of HTTP server")
    args = parser.parse_args()
    if args.demo:
        demo_flow()
    else:
        run_server()
