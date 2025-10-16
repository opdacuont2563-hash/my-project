"""Embedded FastAPI server that powers the OR runner workflow."""
from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import date, datetime, timedelta, time as dtime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode

import qrcode
import requests
import sqlite3
import uvicorn
from fastapi import (
    Body,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

DB_PATH = Path(__file__).resolve().with_name("pickups.db")
_ROW_KEYS = [
    "pickup_id",
    "date",
    "hn",
    "name",
    "ward_from",
    "or_to",
    "call_time",
    "due_time",
    "status",
    "assignee",
    "ack_time",
    "start_time",
    "arrive_time",
    "note",
]

_DB_LOCK = threading.Lock()
_DB_INITIALIZED = False
_SERVER_LOCK = threading.Lock()
_server_thread: Optional[threading.Thread] = None


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the pickups table when it does not exist."""
    global _DB_INITIALIZED
    with _DB_LOCK:
        with _conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pickups(
                  pickup_id TEXT PRIMARY KEY,
                  date TEXT,
                  hn TEXT,
                  name TEXT,
                  ward_from TEXT,
                  or_to TEXT,
                  call_time TEXT,
                  due_time TEXT,
                  status TEXT,
                  assignee TEXT,
                  ack_time TEXT,
                  start_time TEXT,
                  arrive_time TEXT,
                  note TEXT
                )
                """
            )
        _DB_INITIALIZED = True


def _ensure_db() -> None:
    if not _DB_INITIALIZED:
        init_db()


def _normalize_row(row: Dict[str, Any]) -> Dict[str, str]:
    normalised: Dict[str, str] = {}
    for key in _ROW_KEYS:
        value = row.get(key, "") if isinstance(row, dict) else ""
        if value is None:
            value = ""
        normalised[key] = str(value)
    if not normalised["pickup_id"].strip():
        raise ValueError("pickup_id is required")
    if not normalised["date"].strip():
        normalised["date"] = date.today().isoformat()
    return normalised


def upsert_pickups(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Insert or update pickup rows and return the persisted payloads."""
    _ensure_db()
    rows = list(rows)
    if not rows:
        return []

    persisted: List[Dict[str, str]] = []
    with _conn() as conn:
        for row in rows:
            normalised = _normalize_row(row)
            placeholders = ",".join(["?"] * len(_ROW_KEYS))
            assignments = ",".join(f"{key}=excluded.{key}" for key in _ROW_KEYS[1:])
            conn.execute(
                f"INSERT INTO pickups({','.join(_ROW_KEYS)}) VALUES({placeholders}) "
                f"ON CONFLICT(pickup_id) DO UPDATE SET {assignments}",
                [normalised[key] for key in _ROW_KEYS],
            )
            persisted.append(normalised)
    return persisted


def list_pickups(filters: Dict[str, Any]) -> List[Dict[str, str]]:
    """Return pickups filtered by date and optional ward/status."""
    _ensure_db()
    date_str = str(filters.get("date", "")).strip()
    if not date_str:
        raise ValueError("date is required")

    query = "SELECT * FROM pickups WHERE date=?"
    params: List[Any] = [date_str]

    ward = str(filters.get("ward", "")).strip()
    if ward:
        query += " AND ward_from=?"
        params.append(ward)

    status = str(filters.get("status", "")).strip()
    if status:
        query += " AND status=?"
        params.append(status)

    query += " ORDER BY due_time"

    with _conn() as conn:
        cur = conn.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


_ALLOWED_STAMPS = {"ack_time", "arrive_time", "start_time"}


def set_status(
    pickup_id: str,
    status: str,
    who: str,
    stamp_field: str,
) -> Optional[Dict[str, str]]:
    """Update a pickup status and return the updated row."""
    _ensure_db()
    if stamp_field not in _ALLOWED_STAMPS:
        raise ValueError("invalid stamp field")

    pickup_id = str(pickup_id)
    status = str(status)
    who = str(who or "")

    stamp = datetime.now().strftime("%H:%M")
    with _conn() as conn:
        cur = conn.execute(
            f"UPDATE pickups SET status=?, assignee=?, {stamp_field}=? WHERE pickup_id=?",
            (status, who, stamp, pickup_id),
        )
        if cur.rowcount == 0:
            return None
        cur = conn.execute("SELECT * FROM pickups WHERE pickup_id=?", (pickup_id,))
        row = cur.fetchone()
    return dict(row) if row else None


class PickupRowPayload(BaseModel):
    pickup_id: str
    date: Optional[str] = None
    hn: Optional[str] = None
    name: Optional[str] = None
    ward_from: Optional[str] = None
    or_to: Optional[str] = None
    call_time: Optional[str] = None
    due_time: Optional[str] = None
    status: Optional[str] = None
    assignee: Optional[str] = None
    ack_time: Optional[str] = None
    start_time: Optional[str] = None
    arrive_time: Optional[str] = None
    note: Optional[str] = None

    class Config:
        extra = "allow"


class StatusChangePayload(BaseModel):
    pickup_id: str
    user: str


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _on_startup() -> None:  # pragma: no cover - FastAPI hook
    _ensure_db()


live_clients: List[WebSocket] = []


@app.get("/health")
def health() -> Dict[str, bool]:
    return {"ok": True}


@app.get("/runner", response_class=HTMLResponse)
def runner_page() -> str:
    return HTML_TEMPLATE


@app.get("/runner/list")
def runner_list(date: str, ward: str = "", status: str = "") -> List[Dict[str, str]]:
    try:
        return list_pickups({"date": date, "ward": ward, "status": status})
    except ValueError as exc:  # pragma: no cover - validation path
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/runner/update")
async def runner_update(row: PickupRowPayload = Body(...)) -> Dict[str, Any]:
    try:
        persisted = upsert_pickups([row.dict(exclude_unset=True)])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    stored = persisted[0] if persisted else {}
    await _broadcast({"type": "upsert", "row": stored})
    return {"ok": True, "row": stored}


@app.post("/runner/ack")
async def runner_ack(payload: StatusChangePayload) -> Dict[str, Any]:
    updated = set_status(payload.pickup_id, "picking", payload.user, "ack_time")
    if updated is None:
        raise HTTPException(status_code=404, detail="pickup not found")
    await _broadcast({"type": "status", "row": updated})
    return {"ok": True, "row": updated}


@app.post("/runner/arrive")
async def runner_arrive(payload: StatusChangePayload) -> Dict[str, Any]:
    updated = set_status(payload.pickup_id, "arrived", payload.user, "arrive_time")
    if updated is None:
        raise HTTPException(status_code=404, detail="pickup not found")
    await _broadcast({"type": "status", "row": updated})
    return {"ok": True, "row": updated}


@app.websocket("/runner/live")
async def runner_live(ws: WebSocket) -> None:
    await ws.accept()
    live_clients.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:  # pragma: no cover - network path
        pass
    except Exception:  # pragma: no cover - defensive
        pass
    finally:
        if ws in live_clients:
            live_clients.remove(ws)


@app.get("/runner/qr")
def runner_qr(request: Request, ward: str = "") -> StreamingResponse:
    today = date.today().isoformat()
    params = {"date": today}
    if ward:
        params["ward"] = ward
    target_url = f"{str(request.base_url).rstrip('/')}/runner?{urlencode(params)}"

    qr = qrcode.QRCode(box_size=8, border=4)
    qr.add_data(target_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    filename = f"runner_{ward or 'all'}.png"
    return StreamingResponse(
        buffer,
        media_type="image/png",
        headers={"Content-Disposition": f"inline; filename={filename}"},
    )


async def _broadcast(message: Dict[str, Any]) -> None:
    if not live_clients:
        return
    payload = json.dumps(message, ensure_ascii=False)
    stale: List[WebSocket] = []
    for ws in list(live_clients):
        try:
            await ws.send_text(payload)
        except Exception:  # pragma: no cover - network path
            stale.append(ws)
    for ws in stale:
        if ws in live_clients:
            live_clients.remove(ws)


HTML_TEMPLATE = """
<!doctype html>
<html lang=\"th\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Runner Board</title>
  <link href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css\" rel=\"stylesheet\">
  <style>
    body { background:#f5f7fb; padding:16px; font-family: 'Sarabun', 'Segoe UI', sans-serif; }
    .filter-card { background:#fff; border-radius:18px; padding:16px; box-shadow:0 8px 20px rgba(15,23,42,.08); }
    .late-row { background:rgba(255,193,7,.15); }
    .overdue-row { background:rgba(220,53,69,.18); }
    .table thead th { white-space:nowrap; }
    .status-badge { font-size:0.75rem; }
  </style>
</head>
<body>
  <div class=\"container-fluid\">
    <div class=\"filter-card mb-3\">
      <div class=\"row g-3 align-items-end\">
        <div class=\"col-12 col-sm-4 col-md-3 col-lg-2\">
          <label class=\"form-label mb-1\" for=\"filter-date\">วันที่</label>
          <input type=\"date\" class=\"form-control\" id=\"filter-date\">
        </div>
        <div class=\"col-12 col-sm-4 col-md-3 col-lg-2\">
          <label class=\"form-label mb-1\" for=\"filter-ward\">Ward</label>
          <input type=\"text\" class=\"form-control\" id=\"filter-ward\" placeholder=\"เช่น SICU\">
        </div>
        <div class=\"col-12 col-sm-4 col-md-3 col-lg-2\">
          <label class=\"form-label mb-1\" for=\"filter-status\">สถานะ</label>
          <select class=\"form-select\" id=\"filter-status\">
            <option value=\"\">ทั้งหมด</option>
            <option value=\"waiting\">รอรับ</option>
            <option value=\"picking\">กำลังนำส่ง</option>
            <option value=\"arrived\">ถึง OR</option>
          </select>
        </div>
        <div class=\"col-12 col-sm-6 col-md-3 col-lg-3\">
          <label class=\"form-label mb-1\" for=\"filter-user\">ผู้ไปรับ</label>
          <input type=\"text\" class=\"form-control\" id=\"filter-user\" placeholder=\"ชื่อผู้ไปรับ\">
        </div>
        <div class=\"col-12 col-sm-6 col-md-3 col-lg-3 text-sm-end\">
          <button class=\"btn btn-primary mt-3 mt-sm-0\" id=\"btn-reload\">โหลดรายการ</button>
        </div>
      </div>
    </div>

    <div class=\"table-responsive shadow-sm\">
      <table class=\"table table-hover align-middle mb-0\" id=\"pickup-table\">
        <thead class=\"table-primary\">
          <tr>
            <th scope=\"col\">HN</th>
            <th scope=\"col\">ชื่อ</th>
            <th scope=\"col\">Ward จาก</th>
            <th scope=\"col\">OR ปลายทาง</th>
            <th scope=\"col\">เวลาเรียก</th>
            <th scope=\"col\">ถึงกำหนด</th>
            <th scope=\"col\">สถานะ</th>
            <th scope=\"col\" class=\"text-end\">การทำงาน</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <script>
  const tableBody = document.querySelector('#pickup-table tbody');
  const dateInput = document.getElementById('filter-date');
  const wardInput = document.getElementById('filter-ward');
  const statusInput = document.getElementById('filter-status');
  const userInput = document.getElementById('filter-user');
  const reloadBtn = document.getElementById('btn-reload');

  const STATUS_BADGES = {
    waiting: 'bg-secondary',
    picking: 'bg-warning text-dark',
    arrived: 'bg-success'
  };

  function todayISO(){
    return new Date().toISOString().slice(0,10);
  }

  function restoreFiltersFromQuery(){
    const params = new URLSearchParams(window.location.search);
    const dateVal = params.get('date');
    const wardVal = params.get('ward');
    const statusVal = params.get('status');
    if(dateVal){ dateInput.value = dateVal; }
    if(wardVal){ wardInput.value = wardVal; }
    if(statusVal){ statusInput.value = statusVal; }
    if(!dateInput.value){ dateInput.value = todayISO(); }
    const savedUser = localStorage.getItem('runnerName') || '';
    if(savedUser){ userInput.value = savedUser; }
  }

  function getFilters(){
    return {
      date: dateInput.value || todayISO(),
      ward: wardInput.value.trim(),
      status: statusInput.value.trim()
    };
  }

  function updateQueryString(filters){
    const params = new URLSearchParams();
    if(filters.date){ params.set('date', filters.date); }
    if(filters.ward){ params.set('ward', filters.ward); }
    if(filters.status){ params.set('status', filters.status); }
    const newUrl = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState({}, '', newUrl);
  }

  async function loadList(){
    const filters = getFilters();
    updateQueryString(filters);
    const params = new URLSearchParams();
    params.set('date', filters.date);
    if(filters.ward){ params.set('ward', filters.ward); }
    if(filters.status){ params.set('status', filters.status); }
    try{
      const res = await fetch(`/runner/list?${params.toString()}`);
      if(!res.ok){ throw new Error('โหลดรายการไม่สำเร็จ'); }
      const data = await res.json();
      renderRows(Array.isArray(data) ? data : []);
    }catch(err){
      console.error(err);
    }
  }

  function renderRows(rows){
    tableBody.innerHTML = '';
    rows.forEach(row => {
      const tr = document.createElement('tr');
      const dueInfo = computeDueInfo(row);
      if(dueInfo.state === 'late'){ tr.classList.add('late-row'); }
      if(dueInfo.state === 'over'){ tr.classList.add('overdue-row'); }
      tr.innerHTML = `
        <td>${row.hn || ''}</td>
        <td>${row.name || ''}</td>
        <td>${row.ward_from || ''}</td>
        <td>${row.or_to || ''}</td>
        <td>${row.call_time || ''}</td>
        <td>${row.due_time || ''}${dueInfo.badge}</td>
        <td>${renderStatusBadge(row.status || '')}</td>
        <td class="text-end text-nowrap">
          <button class="btn btn-sm btn-success me-2" onclick="ack('${row.pickup_id}')">รับเคส</button>
          <button class="btn btn-sm btn-secondary" onclick="arrive('${row.pickup_id}')">ถึง OR</button>
        </td>`;
      tableBody.appendChild(tr);
    });
  }

  function renderStatusBadge(status){
    const cls = STATUS_BADGES[status] || 'bg-light text-dark';
    let label = 'ไม่ทราบ';
    if(status === 'waiting'){ label = 'รอรับ'; }
    else if(status === 'picking'){ label = 'กำลังนำส่ง'; }
    else if(status === 'arrived'){ label = 'ถึง OR'; }
    return `<span class="badge ${cls} status-badge">${label}</span>`;
  }

  function computeDueInfo(row){
    const dueRaw = row.due_time;
    const rowDate = row.date || todayISO();
    let dueDate = null;
    if(dueRaw){
      if(typeof dueRaw === 'string' && dueRaw.includes('T')){
        const parsed = new Date(dueRaw);
        if(!isNaN(parsed)){ dueDate = parsed; }
      }else{
        const parts = String(dueRaw).split(':');
        if(parts.length >= 2){
          const base = new Date(rowDate);
          if(!isNaN(base)){
            base.setHours(parseInt(parts[0],10) || 0, parseInt(parts[1],10) || 0, 0, 0);
            dueDate = base;
          }
        }
      }
    }
    if(!dueDate){
      return { state: '', badge: '' };
    }
    const diffMinutes = (dueDate - new Date()) / 60000;
    if(diffMinutes < 0){
      return { state: 'over', badge: ' <span class="badge bg-danger">เลยเวลา</span>' };
    }
    if(diffMinutes < 15){
      return { state: 'late', badge: ' <span class="badge bg-warning text-dark">ใกล้กำหนด</span>' };
    }
    return { state: '', badge: '' };
  }

  function ensureUser(){
    const value = userInput.value.trim();
    if(value){
      localStorage.setItem('runnerName', value);
      return value;
    }
    const stored = localStorage.getItem('runnerName');
    if(stored){
      userInput.value = stored;
      return stored;
    }
    alert('กรอกชื่อผู้ไปรับก่อนทำรายการ');
    userInput.focus();
    return '';
  }

  async function ack(id){
    const user = ensureUser();
    if(!user){ return; }
    try{
      await fetch('/runner/ack', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pickup_id: id, user })
      });
      scheduleReload();
    }catch(err){ console.error(err); }
  }
  window.ack = ack;

  async function arrive(id){
    const user = ensureUser();
    if(!user){ return; }
    try{
      await fetch('/runner/arrive', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pickup_id: id, user })
      });
      scheduleReload();
    }catch(err){ console.error(err); }
  }
  window.arrive = arrive;

  let reloadTimer = null;
  function scheduleReload(){
    clearTimeout(reloadTimer);
    reloadTimer = setTimeout(loadList, 300);
  }

  let ws = null;
  let keepAlive = null;
  function connectWS(){
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${window.location.host}/runner/live`);
    ws.onopen = () => {
      if(keepAlive){ clearInterval(keepAlive); }
      keepAlive = setInterval(() => {
        if(ws && ws.readyState === WebSocket.OPEN){ ws.send('ping'); }
      }, 25000);
    };
    ws.onmessage = () => scheduleReload();
    ws.onclose = () => {
      if(keepAlive){ clearInterval(keepAlive); keepAlive = null; }
      setTimeout(connectWS, 3000);
    };
    ws.onerror = () => ws.close();
  }

  reloadBtn.addEventListener('click', loadList);
  dateInput.addEventListener('change', loadList);
  wardInput.addEventListener('change', loadList);
  statusInput.addEventListener('change', loadList);
  userInput.addEventListener('change', () => {
    const value = userInput.value.trim();
    if(value){ localStorage.setItem('runnerName', value); }
  });

  restoreFiltersFromQuery();
  if(!dateInput.value){ dateInput.value = todayISO(); }
  connectWS();
  loadList();
  </script>
</body>
</html>
"""


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, dtime):
        return datetime.combine(date.today(), value)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            if "T" in value:
                return datetime.fromisoformat(value)
            return datetime.combine(
                date.today(),
                datetime.strptime(value, "%H:%M").time(),
            )
        except ValueError:
            return None
    return None


class RunnerPickupClient:
    """Lightweight HTTP client for the embedded runner service."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8777",
        *,
        timeout: float = 3.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.s = session or requests.Session()

    # ------------------------------------------------------------------
    # Liveness helpers
    # ------------------------------------------------------------------
    def _health_ok(self) -> bool:
        try:
            response = self.s.get(
                f"{self.base}/health",
                timeout=min(self.timeout, 0.8),
            )
            return response.ok
        except requests.RequestException:
            return False

    def ensure_runner_alive(self) -> bool:
        if self._health_ok():
            return True

        try:
            start_embedded_server()
        except Exception:
            pass

        for _ in range(10):
            if self._health_ok():
                return True
            time.sleep(0.5)
        return False

    # ------------------------------------------------------------------
    # Payload helpers
    # ------------------------------------------------------------------
    def push_entries(self, rows: Iterable[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
        endpoint = f"{self.base}/runner/update"
        succeeded: List[str] = []
        failed: List[str] = []

        for row in rows:
            if not isinstance(row, dict):
                failed.append("")
                continue

            pickup_id = str(row.get("pickup_id") or "")

            try:
                response = self.s.post(endpoint, json=row, timeout=self.timeout)
                response.raise_for_status()
            except requests.RequestException:
                failed.append(pickup_id)
                continue

            succeeded.append(pickup_id)

        return succeeded, failed


def push_today_pickups(
    rows: Iterable[Dict[str, Any]],
    *,
    base_url: str = "http://127.0.0.1:8777",
    timeout: float = 3.0,
) -> List[str]:
    """Push operating room rows into the pickup runner service.

    Args:
        rows: Iterable of dictionaries describing OR cases.
        base_url: Base URL of the runner service.
        timeout: Timeout per HTTP request in seconds.

    Returns:
        List of pickup IDs that were successfully upserted.
    """

    today = date.today().isoformat()
    payloads: List[Dict[str, Any]] = []

    for raw in rows:
        if raw is None:
            continue
        pickup_id = str(raw.get("pickup_id") or raw.get("id") or "")
        if not pickup_id:
            pickup_id = str(uuid.uuid4())

        start_candidate = (
            raw.get("start_time")
            or raw.get("start")
            or raw.get("เริ่ม")
            or raw.get("Start")
            or raw.get("เวลาเริ่ม")
            or ""
        )
        start_dt = _coerce_datetime(start_candidate)
        due_time = ""
        if start_dt is not None:
            due_time = (start_dt - timedelta(minutes=15)).strftime("%H:%M")

        payloads.append(
            {
                "pickup_id": pickup_id,
                "date": raw.get("date") or today,
                "hn": raw.get("HN") or raw.get("hn") or "",
                "name": raw.get("ชื่อ-สกุล") or raw.get("name") or "",
                "ward_from": raw.get("Ward") or raw.get("ward_from") or raw.get("ward") or "",
                "or_to": raw.get("OR") or raw.get("or_to") or raw.get("or") or "",
                "call_time": datetime.now().strftime("%H:%M"),
                "due_time": due_time,
                "status": "waiting",
                "assignee": "",
                "ack_time": "",
                "start_time": start_dt.strftime("%H:%M") if start_dt else (start_candidate or ""),
                "arrive_time": "",
                "note": raw.get("หมายเหตุ") or raw.get("note") or "",
            }
        )

    if not payloads:
        return []

    client = RunnerPickupClient(base_url=base_url, timeout=timeout)
    if not client.ensure_runner_alive():
        return []

    succeeded, _ = client.push_entries(payloads)
    return succeeded


__all__ = [
    "app",
    "init_db",
    "list_pickups",
    "RunnerPickupClient",
    "push_today_pickups",
    "set_status",
    "start_embedded_server",
    "upsert_pickups",
]


def start_embedded_server(host: str = "127.0.0.1", port: int = 8777) -> threading.Thread:
    """Start the FastAPI server in a daemon thread and return immediately."""
    init_db()
    global _server_thread
    with _SERVER_LOCK:
        if _server_thread and _server_thread.is_alive():
            return _server_thread

        def _run() -> None:
            uvicorn.run(app, host=host, port=port, log_level="warning")

        thread = threading.Thread(target=_run, name="RunnerFastAPI", daemon=True)
        thread.start()
        _server_thread = thread
        return thread
