"""Embedded FastAPI server that powers the OR runner workflow."""
from __future__ import annotations

import os
import json
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, time as dtime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode, urlparse

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
from pydantic import BaseModel, ConfigDict

# ------------------ Config ------------------
DB_PATH = Path(__file__).resolve().with_name("pickups.db")
_ROW_KEYS = [
    "pickup_id", "date", "hn", "name", "ward_from", "or_to",
    "call_time", "due_time", "status", "assignee",
    "ack_time", "start_time", "arrive_time", "note",
]
_DB_LOCK = threading.Lock()
_DB_INITIALIZED = False
_SERVER_LOCK = threading.Lock()
_server_thread: Optional[threading.Thread] = None

def _default_runner_host() -> str:
    # ค่าเริ่มต้นฟังทุกอินเตอร์เฟซ เพื่อให้มือถือใน LAN เข้าได้
    return os.getenv("SURGIBOT_CLIENT_HOST", "0.0.0.0").strip() or "0.0.0.0"

def _default_runner_port() -> int:
    raw = os.getenv("SURGIBOT_RUNNER_PORT", "8777").strip()
    try:
        return int(raw)
    except ValueError:
        return 8777

def _default_runner_base_url() -> str:
    base = os.getenv("SURGIBOT_RUNNER_BASE_URL", "").strip()
    if base:
        return base.rstrip("/")
    return f"http://127.0.0.1:{_default_runner_port()}"

# ------------------ DB helpers ------------------
def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
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
    pickup_id: str, status: str, who: str, stamp_field: str,
) -> Optional[Dict[str, str]]:
    _ensure_db()
    if stamp_field not in _ALLOWED_STAMPS:
        raise ValueError("invalid stamp field")
    pickup_id = str(pickup_id); status = str(status); who = str(who or "")
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

# ------------------ Schemas ------------------
class PickupRowPayload(BaseModel):
    pickup_id: str
    date: str | None = None
    hn: str | None = None
    name: str | None = None
    ward_from: str | None = None
    or_to: str | None = None
    call_time: str | None = None
    due_time: str | None = None
    status: str | None = None
    assignee: str | None = None
    ack_time: str | None = None
    start_time: str | None = None
    arrive_time: str | None = None
    note: str | None = None

    model_config = ConfigDict(extra="allow")

class StatusChangePayload(BaseModel):
    pickup_id: str
    user: str

# ------------------ App ------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_db()
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

live_clients: List[WebSocket] = []

@app.get("/health")
def health() -> Dict[str, bool]:
    return {"ok": True}

# --------- Desktop Runner Board ----------
HTML_TEMPLATE = """
<!doctype html>
<html lang="th">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Runner Board</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
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
  <div class="container-fluid">
    <div class="filter-card mb-3">
      <div class="row g-3 align-items-end">
        <div class="col-12 col-sm-4 col-md-3 col-lg-2">
          <label class="form-label mb-1" for="filter-date">วันที่</label>
          <input type="date" class="form-control" id="filter-date">
        </div>
        <div class="col-12 col-sm-4 col-md-3 col-lg-2">
          <label class="form-label mb-1" for="filter-ward">Ward</label>
          <input type="text" class="form-control" id="filter-ward" placeholder="เช่น SICU">
        </div>
        <div class="col-12 col-sm-4 col-md-3 col-lg-2">
          <label class="form-label mb-1" for="filter-status">สถานะ</label>
          <select class="form-select" id="filter-status">
            <option value="">ทั้งหมด</option>
            <option value="waiting">รอรับ</option>
            <option value="picking">กำลังนำส่ง</option>
            <option value="arrived">ถึง OR</option>
          </select>
        </div>
        <div class="col-12 col-sm-6 col-md-3 col-lg-3">
          <label class="form-label mb-1" for="filter-user">ผู้ไปรับ</label>
          <input type="text" class="form-control" id="filter-user" placeholder="ชื่อผู้ไปรับ">
        </div>
        <div class="col-12 col-sm-6 col-md-3 col-lg-3 text-sm-end">
          <button class="btn btn-primary mt-3 mt-sm-0" id="btn-reload">โหลดรายการ</button>
        </div>
      </div>
    </div>

    <div class="table-responsive shadow-sm">
      <table class="table table-hover align-middle mb-0" id="pickup-table">
        <thead class="table-primary">
          <tr>
            <th scope="col">HN</th>
            <th scope="col">ชื่อ</th>
            <th scope="col">Ward จาก</th>
            <th scope="col">OR ปลายทาง</th>
            <th scope="col">เวลาเรียก</th>
            <th scope="col">ถึงกำหนด</th>
            <th scope="col">สถานะ</th>
            <th scope="col" class="text-end">การทำงาน</th>
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

  function todayISO(){ return new Date().toISOString().slice(0,10); }

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
    if(!dueDate){ return { state: '', badge: '' }; }
    const diffMinutes = (dueDate - new Date()) / 60000;
    if(diffMinutes < 0){ return { state: 'over', badge: ' <span class="badge bg-danger">เลยเวลา</span>' }; }
    if(diffMinutes < 15){ return { state: 'late', badge: ' <span class="badge bg-warning text-dark">ใกล้กำหนด</span>' }; }
    return { state: '', badge: '' };
  }

  function ensureUser(){
    const value = userInput.value.trim();
    if(value){ localStorage.setItem('runnerName', value); return value; }
    const stored = localStorage.getItem('runnerName');
    if(stored){ userInput.value = stored; return stored; }
    alert('กรอกชื่อผู้ไปรับก่อนทำรายการ'); userInput.focus(); return '';
  }

  async function ack(id){
    const user = ensureUser(); if(!user){ return; }
    try{
      await fetch('/runner/ack',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ pickup_id:id, user })});
      scheduleReload();
    }catch(err){ console.error(err); }
  }
  window.ack = ack;

  async function arrive(id){
    const user = ensureUser(); if(!user){ return; }
    try{
      await fetch('/runner/arrive',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ pickup_id:id, user })});
      scheduleReload();
    }catch(err){ console.error(err); }
  }
  window.arrive = arrive;

  let reloadTimer = null;
  function scheduleReload(){ clearTimeout(reloadTimer); reloadTimer = setTimeout(loadList, 300); }

  let ws = null, keepAlive = null;
  function connectWS(){
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${window.location.host}/runner/live`);
    ws.onopen = () => {
      if(keepAlive){ clearInterval(keepAlive); }
      keepAlive = setInterval(() => { if(ws && ws.readyState === WebSocket.OPEN){ ws.send('ping'); } }, 25000);
    };
    ws.onmessage = () => scheduleReload();
    ws.onclose = () => { if(keepAlive){ clearInterval(keepAlive); keepAlive = null; } setTimeout(connectWS, 3000); };
    ws.onerror = () => ws.close();
  }

  reloadBtn.addEventListener('click', loadList);
  dateInput.addEventListener('change', loadList);
  wardInput.addEventListener('change', loadList);
  statusInput.addEventListener('change', loadList);
  userInput.addEventListener('change', () => { const v = userInput.value.trim(); if(v){ localStorage.setItem('runnerName', v); } });

  restoreFiltersFromQuery();
  if(!dateInput.value){ dateInput.value = todayISO(); }
  connectWS(); loadList();
  </script>
</body></html>
"""

@app.get("/runner", response_class=HTMLResponse)
def runner_page() -> str:
    return HTML_TEMPLATE

@app.get("/runner/list")
def runner_list(date: str, ward: str = "", status: str = "") -> List[Dict[str, str]]:
    try:
        return list_pickups({"date": date, "ward": ward, "status": status})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/runner/update")
async def runner_update(row: PickupRowPayload = Body(...)) -> Dict[str, Any]:
    try:
        persisted = upsert_pickups([row.model_dump(exclude_unset=True)])
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
    except WebSocketDisconnect:
        pass
    except Exception:
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
    qr.add_data(target_url); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO(); img.save(buffer, format="PNG"); buffer.seek(0)
    filename = f"runner_{ward or 'all'}.png"
    return StreamingResponse(buffer, media_type="image/png",
        headers={"Content-Disposition": f"inline; filename={filename}"})

# --------- Mobile view ----------
MOBILE_TEMPLATE = """<!doctype html>
<html lang="th"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Runner Mobile</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
<style>
  :root{
    --bg:#f5f7fb;
    --header:#ffffff;
    --text:#0f172a;
    --muted:#64748b;
    --primary:#2563eb;
    --success:#16a34a;
    --warning:#f59e0b;
    --chip:#eef2ff;
    --card:#ffffff;
    --border:#e5e7eb;
    --shadow:0 10px 24px rgba(2,6,23,.08);
  }
  html,body{height:100%}
  body{margin:0;background:var(--bg);color:var(--text);font-family:"Sarabun","Segoe UI",system-ui,-apple-system,sans-serif}

  /* Topbar */
  .topbar{
    position:sticky; top:0; z-index:1000; background:var(--header);
    border-bottom:1px solid var(--border);
  }
  .brand{display:flex; align-items:center; gap:.5rem; font-weight:700}
  .brand .dot{width:10px;height:10px;border-radius:999px;background:var(--success)}

  .btn-ghost{color:var(--text);border:1px solid var(--border);background:#fff}
  .btn-ghost:hover{background:#f8fafc}

  /* Filter panel */
  .filter-panel{padding:.75rem .75rem .5rem .75rem}
  .chip{
    display:inline-flex; align-items:center; gap:.35rem;
    padding:.25rem .6rem; border-radius:999px;
    background:var(--chip); color:#334155; font-size:.8rem;
    border:1px solid var(--border)
  }

  /* List */
  .page{padding:12px}
  .cardx{
    background:var(--card); border:1px solid var(--border);
    border-radius:14px; padding:14px; box-shadow:var(--shadow);
    animation:fadeIn .18s ease;
  }
  .subtitle{color:var(--muted);font-size:.88rem}
  .divider{border-top:1px dashed var(--border);margin:.5rem 0}
  .btn-pill{border-radius:12px; padding:.35rem .75rem}
  .badge-soft{border:1px solid var(--border); background:#f8fafc}
  .status-badge{font-size:.8rem}

  /* Floating refresh */
  .fab{
    position:fixed; right:14px; bottom:18px; z-index:1001;
    border-radius:999px; padding:.7rem .9rem; font-size:1.05rem;
    background:var(--primary); border:none; color:white; box-shadow:0 10px 24px rgba(37,99,235,.35);
  }

  /* Animations (เน้นนุ่ม ไม่กระพริบ) */
  @keyframes fadeIn{from{opacity:0; transform:translateY(4px)} to{opacity:1; transform:none}}
</style>
</head>
<body>

<!-- Topbar -->
<div class="topbar">
  <div class="container-fluid py-2 px-3">
    <div class="d-flex align-items-center justify-content-between">
      <div class="brand"><span class="dot"></span> Runner <span class="d-none d-sm-inline">Mobile</span></div>
      <div class="d-flex gap-2">
        <button class="btn btn-sm btn-ghost" id="btn-toggle"><i class="bi bi-sliders"></i> ตัวกรอง</button>
      </div>
    </div>

    <!-- Filters -->
    <div id="filters" class="filter-panel">
      <div class="row g-2 align-items-end">
        <div class="col-5">
          <label class="form-label mb-1">วันที่</label>
          <input id="d" type="date" class="form-control form-control-sm">
        </div>
        <div class="col-7">
          <label class="form-label mb-1">วอร์ด</label>
          <input id="w" class="form-control form-control-sm" placeholder="เช่น SICU">
        </div>
        <div class="col-6">
          <label class="form-label mb-1">สถานะ</label>
          <select id="s" class="form-select form-select-sm">
            <option value="">ทั้งหมด</option>
            <option value="waiting">รอรับ</option>
            <option value="picking">กำลังนำส่ง</option>
            <option value="arrived">ถึง OR</option>
          </select>
        </div>
        <div class="col-6">
          <label class="form-label mb-1">ชื่อผู้ไปรับ</label>
          <input id="u" class="form-control form-control-sm" placeholder="เช่น สมชาย">
        </div>
        <div class="col-12 text-end">
          <button id="b" class="btn btn-primary btn-sm mt-1"><span class="btn-text"><i class="bi bi-cloud-download"></i> โหลดรายการ</span><span class="btn-wait d-none"><span class="spinner-border spinner-border-sm me-1"></span>กำลังโหลด</span></button>
        </div>
      </div>
      <div class="pt-2">
        <span class="chip me-2"><i class="bi bi-calendar-date"></i> <span id="chip-date">วันนี้</span></span>
        <span class="chip me-2"><i class="bi bi-building"></i> <span id="chip-ward">ทุกวอร์ด</span></span>
        <span class="chip"><i class="bi bi-activity"></i> <span id="chip-status">ทุกสถานะ</span></span>
      </div>
    </div>
  </div>
</div>

<!-- List -->
<div class="page container-fluid" id="list"></div>

<!-- Floating refresh -->
<button class="fab" id="fab"><i class="bi bi-arrow-clockwise"></i></button>

<script>
  const elD=document.getElementById('d'), elW=document.getElementById('w'),
        elS=document.getElementById('s'), elU=document.getElementById('u'),
        elB=document.getElementById('b'), elList=document.getElementById('list'),
        elFab=document.getElementById('fab'), elToggle=document.getElementById('btn-toggle'),
        chipDate=document.getElementById('chip-date'), chipWard=document.getElementById('chip-ward'), chipStatus=document.getElementById('chip-status'),
        btnText=elB.querySelector('.btn-text'), btnWait=elB.querySelector('.btn-wait');

  const STATUS_CLS = {
    waiting:  'badge-soft text-secondary',
    picking:  'bg-warning text-dark',
    arrived:  'bg-success'
  };

  /* ---------- helpers ---------- */
  function todayISO(){ return new Date().toISOString().slice(0,10) }
  function saveName(){ localStorage.setItem('runnerName', elU.value.trim()); }
  function ensureName(){
    let n=elU.value.trim() || localStorage.getItem('runnerName')||'';
    if(!elU.value) elU.value=n; return n;
  }
  function toastOK(msg){
    Swal.fire({toast:true,position:'top',icon:'success',title:msg,showConfirmButton:false,timer:1300});
  }
  function toastErr(msg){
    Swal.fire({toast:true,position:'top',icon:'error',title:msg,showConfirmButton:false,timer:1600});
  }
  function confirmAction(title, text, confirmTxt='ยืนยัน'){
    return Swal.fire({icon:'question', title, text, showCancelButton:true, confirmButtonText:confirmTxt, cancelButtonText:'ยกเลิก', confirmButtonColor:'#2563eb'});
  }
  function updateChips(){
    chipDate.textContent = elD.value ? elD.value : 'วันนี้';
    chipWard.textContent = elW.value.trim() || 'ทุกวอร์ด';
    chipStatus.textContent = elS.value || 'ทุกสถานะ';
  }
  function setBtnLoading(loading){
    if(loading){ btnText.classList.add('d-none'); btnWait.classList.remove('d-none'); elB.disabled=true; }
    else { btnText.classList.remove('d-none'); btnWait.classList.add('d-none'); elB.disabled=false; }
  }

  /* ---------- load list (ลดกระพริบ: ไม่ล้างก่อน, ค่อยแทนที่เมื่อได้ข้อมูล) ---------- */
  async function loadList(){
    updateChips(); setBtnLoading(true);
    const date=elD.value||todayISO(), ward=elW.value.trim(), status=elS.value.trim();
    const q=new URLSearchParams({date}); if(ward) q.set('ward',ward); if(status) q.set('status',status);
    try{
      const res=await fetch('/runner/list?'+q.toString());
      if(!res.ok) throw new Error('โหลดรายการไม่สำเร็จ');
      const rows=await res.json();
      render(rows);
    }catch(e){ toastErr('โหลดรายการไม่สำเร็จ'); console.error(e) }
    finally{ setBtnLoading(false); }
  }

  function chip(txt){return `<span class="chip ms-1">${txt}</span>`}
  function badgeStatus(st){ const cls=STATUS_CLS[st]||'badge-soft text-secondary'; const name=st==='arrived'?'ถึง OR':st==='picking'?'กำลังนำส่ง':st? 'รอรับ' : '-'; return `<span class="badge ${cls} status-badge">${name}</span>` }

  function render(rows){
    if(!rows || rows.length===0){
      elList.innerHTML = `
        <div class="cardx">
          <div class="text-center py-4">
            <i class="bi bi-inbox fs-1 text-secondary"></i>
            <div class="mt-2">ยังไม่มีรายการ</div>
            <div class="subtitle">ตรวจสอบวันที่/วอร์ด หรือกดรีเฟรชอีกครั้ง</div>
          </div>
        </div>`;
      return;
    }
    // สร้าง DOM ใหม่แล้วค่อยแทนที่ (ลดเฟลช/กระพริบ)
    const wrapper = document.createElement('div');
    rows.forEach(r=>{
      const card=document.createElement('div');
      card.className='cardx mb-2';

      const due = r.due_time ? `<span class="badge text-dark bg-warning ms-2">${r.due_time}</span>` : '';
      const top = `
        <div class="d-flex justify-content-between">
          <div>
            <div class="fw-bold">${r.name||''} ${r.hn?chip(r.hn):''}</div>
            <div class="subtitle mt-1"><i class="bi bi-stopwatch"></i> เรียก ${r.call_time||'-'} ${due}</div>
          </div>
          <div>${badgeStatus(r.status||'')}</div>
        </div>`;

      const mid = `
        <div class="divider"></div>
        <div class="row g-2 small">
          <div class="col-6"><i class="bi bi-building"></i> จาก: <span class="fw-semibold">${r.ward_from||'-'}</span></div>
          <div class="col-6"><i class="bi bi-door-open"></i> ส่ง: <span class="fw-semibold">${r.or_to||'-'}</span></div>
        </div>`;

      const btns = `
        <div class="mt-2 d-flex gap-2">
          <button class="btn btn-success btn-sm btn-pill" data-action="ack"><i class="bi bi-check2-circle"></i> รับเคส</button>
          <button class="btn btn-secondary btn-sm btn-pill" data-action="arrive"><i class="bi bi-flag"></i> ถึง OR</button>
        </div>`;

      card.innerHTML = top + mid + btns;

      // Handlers
      card.querySelector('[data-action="ack"]').onclick = async ()=>{
        const user=ensureName(); if(!user){ toastErr('กรอกชื่อผู้ไปรับก่อน'); elU.focus(); return }
        const ok = await confirmAction('ยืนยันรับเคส?', `${r.name||''} (${r.hn||''})`, 'รับเคส');
        if(!ok.isConfirmed) return;
        try{
          await fetch('/runner/ack',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pickup_id:r.pickup_id,user})});
          toastOK('รับเคสเรียบร้อย'); loadList();
        }catch(e){ toastErr('ทำรายการไม่สำเร็จ'); }
      };

      card.querySelector('[data-action="arrive"]').onclick = async ()=>{
        const user=ensureName(); if(!user){ toastErr('กรอกชื่อผู้ไปรับก่อน'); elU.focus(); return }
        const ok = await confirmAction('ยืนยันถึง OR?', `${r.name||''} (${r.hn||''})`, 'บันทึกถึง OR');
        if(!ok.isConfirmed) return;
        try{
          await fetch('/runner/arrive',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pickup_id:r.pickup_id,user})});
          toastOK('บันทึกถึง OR แล้ว'); loadList();
        }catch(e){ toastErr('ทำรายการไม่สำเร็จ'); }
      };

      wrapper.appendChild(card);
    });
    elList.replaceChildren(...wrapper.childNodes);
  }

  /* ---------- events ---------- */
  elB.onclick=loadList; elFab.onclick=loadList;
  elD.onchange=()=>{updateChips(); loadList()}; elW.onchange=()=>{updateChips(); loadList()}; elS.onchange=()=>{updateChips(); loadList()};
  elU.onchange=saveName;
  elToggle.onclick=()=>{ const f=document.getElementById('filters'); f.style.display= (f.style.display==='none'?'block':'none'); };

  // init
  elD.value=todayISO();
  const p=new URLSearchParams(location.search);
  if(p.get('ward')) elW.value=p.get('ward');
  if(localStorage.getItem('runnerName')) elU.value=localStorage.getItem('runnerName');
  updateChips();

  // WebSocket live update (เหมือนจอใหญ่)
  let ws=null, keepAlive=null;
  function connectWS(){
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/runner/live`);
    ws.onopen = () => {
      if(keepAlive) clearInterval(keepAlive);
      keepAlive = setInterval(()=>{ if(ws && ws.readyState===WebSocket.OPEN) ws.send('ping'); }, 25000);
    };
    ws.onmessage = () => loadList();
    ws.onclose = () => { if(keepAlive) clearInterval(keepAlive); keepAlive=null; setTimeout(connectWS, 2500); };
    ws.onerror  = () => ws.close();
  }
  connectWS();
  loadList();
</script>
</body></html>
"""

@app.get("/m", response_class=HTMLResponse)
def mobile_page() -> str:
    return MOBILE_TEMPLATE

@app.get("/m/qr")
def mobile_qr(request: Request, ward: str = "") -> StreamingResponse:
    base = str(request.base_url).rstrip("/")
    url = f"{base}/m"
    if ward:
        from urllib.parse import urlencode as _enc
        url = f"{url}?{_enc({'ward': ward})}"
    qr = qrcode.QRCode(box_size=8, border=4); qr.add_data(url); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
    return StreamingResponse(buf, media_type="image/png",
        headers={"Content-Disposition": f"inline; filename=runner_mobile_{ward or 'all'}.png"})

# ------------------ Live & utilities ------------------
async def _broadcast(message: Dict[str, Any]) -> None:
    if not live_clients: return
    payload = json.dumps(message, ensure_ascii=False)
    stale: List[WebSocket] = []
    for ws in list(live_clients):
        try:
            await ws.send_text(payload)
        except Exception:
            stale.append(ws)
    for ws in stale:
        if ws in live_clients:
            live_clients.remove(ws)

# ------------------ Desktop helper client ------------------
def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime): return value
    if isinstance(value, dtime): return datetime.combine(date.today(), value)
    if isinstance(value, (int, float)): return datetime.fromtimestamp(value)
    if isinstance(value, str):
        value = value.strip()
        if not value: return None
        try:
            if "T" in value: return datetime.fromisoformat(value)
            return datetime.combine(date.today(), datetime.strptime(value, "%H:%M").time())
        except ValueError:
            return None
    return None

class RunnerPickupClient:
    """Lightweight HTTP client for the embedded runner service."""
    def __init__(self, base_url: Optional[str] = None, *, timeout: float = 3.0, session: Optional[requests.Session] = None) -> None:
        resolved = base_url or _default_runner_base_url()
        self.base = resolved.rstrip("/")
        self.timeout = timeout
        self.s = session or requests.Session()

    def _health_ok(self) -> bool:
        try:
            r = self.s.get(f"{self.base}/health", timeout=min(self.timeout, 0.8))
            return r.ok
        except requests.RequestException:
            return False

    def ensure_runner_alive(self) -> bool:
        if self._health_ok(): return True
        try: parsed = urlparse(self.base)
        except Exception: parsed = None

        should_bootstrap = False; host_hint: Optional[str] = None; port_hint: Optional[int] = None
        if parsed and parsed.scheme in {"http","https"}:
            host_hint = parsed.hostname; port_hint = parsed.port or _default_runner_port()
            default_host = _default_runner_host()
            if host_hint in {None, "127.0.0.1", "localhost", default_host}:
                should_bootstrap = True
        else:
            should_bootstrap = True

        if should_bootstrap:
            try: start_embedded_server(host_hint, port_hint)
            except Exception: pass

        for _ in range(10):
            if self._health_ok(): return True
            time.sleep(0.5)
        return False

    def push_entries(self, rows: Iterable[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
        endpoint = f"{self.base}/runner/update"
        ok: List[str] = []; bad: List[str] = []
        for row in rows:
            if not isinstance(row, dict):
                bad.append(""); continue
            pid = str(row.get("pickup_id") or "")
            try:
                resp = self.s.post(endpoint, json=row, timeout=self.timeout)
                resp.raise_for_status()
                ok.append(pid)
            except requests.RequestException:
                bad.append(pid)
        return ok, bad

def push_today_pickups(rows: Iterable[Dict[str, Any]], *, base_url: Optional[str] = None, timeout: float = 3.0) -> List[str]:
    """Transform & upsert rows into the runner service."""
    today = date.today().isoformat()
    payloads: List[Dict[str, Any]] = []
    for raw in rows:
        if raw is None: continue
        pickup_id = str(raw.get("pickup_id") or raw.get("id") or "") or str(uuid.uuid4())
        start_candidate = (raw.get("start_time") or raw.get("start") or raw.get("เริ่ม") or raw.get("Start") or raw.get("เวลาเริ่ม") or "")
        start_dt = _coerce_datetime(start_candidate)
        due_time = (start_dt - timedelta(minutes=15)).strftime("%H:%M") if start_dt else ""
        payloads.append({
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
        })
    if not payloads: return []
    client = RunnerPickupClient(base_url=base_url, timeout=timeout)
    if not client.ensure_runner_alive(): return []
    ok, _ = client.push_entries(payloads)
    return ok

__all__ = [
    "app", "init_db", "list_pickups",
    "RunnerPickupClient", "push_today_pickups",
    "set_status", "start_embedded_server", "upsert_pickups",
]

# ------------------ Starter ------------------
def start_embedded_server(host: Optional[str] = None, port: Optional[int] = None) -> threading.Thread:
    """Start the FastAPI server in a daemon thread and return immediately."""
    init_db()
    resolved_host = (host or _default_runner_host()).strip() or _default_runner_host()
    if isinstance(port, str):
        try: resolved_port = int(port)
        except ValueError: resolved_port = _default_runner_port()
    elif isinstance(port, int):
        resolved_port = port or _default_runner_port()
    else:
        resolved_port = _default_runner_port()
    global _server_thread
    with _SERVER_LOCK:
        if _server_thread and _server_thread.is_alive():
            return _server_thread
        def _run() -> None:
            uvicorn.run(app, host=resolved_host, port=resolved_port, log_level="warning")
        thread = threading.Thread(target=_run, name="RunnerFastAPI", daemon=True)
        thread.start()
        _server_thread = thread
        return thread

if __name__ == "__main__":
    print(f"Starting Runner API on http://{_default_runner_host()}:{_default_runner_port()}")
    start_embedded_server().join()
