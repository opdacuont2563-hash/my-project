# 📋 SurgiBot System - Complete Architecture Plan
## Based on Existing Code Analysis

---

## 🏗️ System Overview

SurgiBot เป็นระบบจัดการและติดตามสถานะการผ่าตัดแบบ Real-time สำหรับโรงพยาบาลหนองบัวลำภู
ประกอบด้วย 3 ส่วนหลัก:

1. **SurgiBot Server** - ระบบแสดงผลหน้าจอใหญ่และ API Server
2. **SurgiBot Client** - โปรแกรม Desktop สำหรับเจ้าหน้าที่
3. **Registry Patient Connect** - ระบบจัดการข้อมูลผู้ป่วยและตารางผ่าตัด

---

## 📊 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Hospital Network                          │
├───────────────────────┬───────────────────────────────────────┤
│                       │                                       │
│   ┌──────────────┐   │        ┌──────────────┐              │
│   │  SurgiBot    │   │        │   Client     │              │
│   │   Server     │◄──┼────────┤  Stations    │              │
│   └──────┬───────┘   │        └──────┬───────┘              │
│          │           │               │                       │
│          ▼           │               ▼                       │
│   ┌──────────────┐   │        ┌──────────────┐              │
│   │ Display      │   │        │   Registry   │              │
│   │  Monitor     │   │        │   Database   │              │
│   └──────────────┘   │        └──────────────┘              │
│                      │                                       │
│   ┌──────────────┐   │        ┌──────────────┐              │
│   │Google Sheets │◄──┼────────┤   WebSocket  │              │
│   │   (Backup)   │   │        │    Server    │              │
│   └──────────────┘   │        └──────────────┘              │
└───────────────────────────────────────────────────────────────┘
```

---

## 🔧 Component Details

### 1. SurgiBot Server (FastAPI + Tkinter)
**หน้าที่หลัก**: API Server และแสดงผลสถานะผ่าตัดบนหน้าจอใหญ่

#### Features:
- **FastAPI Application**
  - RESTful API endpoints
  - WebSocket support for real-time updates
  - Async/await architecture
  - Auto-generated API docs (Swagger/ReDoc)

- **Display System** (Tkinter GUI)
  - Fullscreen GUI
  - Real-time table with color coding
  - Auto-refresh
  - Pulse animation for active status

- **API Endpoints**
  ```
  GET  /api/health         # Health check
  GET  /api/list          # List cases (with/without token)
  GET  /api/list_full     # Full list (requires token)
  POST /api/update        # Update status
  WS   /api/ws            # WebSocket connection
  ```

- **Status Management**
  ```python
  STATUS_FLOW = [
    "รอผ่าตัด",
    "กำลังผ่าตัด",
    "กำลังพักฟื้น",
    "พักฟื้นครบแล้ว",
    "กำลังส่งกลับตึก",
    "เลื่อนการผ่าตัด"
  ]
  ```

- **Auto Features**
  - Auto transition: พักฟื้น → พักฟื้นครบ (1 ชม.)
  - Auto transition: พักฟื้นครบ → ส่งกลับตึก (3 นาที)
  - Auto delete: ลบอัตโนมัติหลังส่งกลับตึก
  - Auto announce: ประกาศเสียงตามรอบเวลา

- **TTS (Text-to-Speech)**
  - gTTS for Thai/English announcements
  - pygame for audio playback
  - Bilingual announcements
  - Scheduled public announcements

- **Google Sheets Integration**
  - Async sync to Google Sheets
  - Service Account authentication
  - Graceful fallback if unavailable

- **Security**
  - Token authentication
  - HN masking (XXX format)
  - Secure WebSocket connections

### 2. SurgiBot Client (PySide6 Desktop App)
**หน้าที่หลัก**: โปรแกรมสำหรับเจ้าหน้าที่จัดการข้อมูลผู้ป่วย

#### Features:
- **Modern UI (PySide6)**
  - Material Design inspired
  - Tab-based interface
  - Real-time status cards
  - Responsive layout

- **Tabs**
  1. Result Schedule Patient
  2. Status Operation Real Time

- **WebSocket Client**
  - Real-time updates from server
  - Auto-reconnection
  - Connection status indicator

- **HTTP Client**
  - Retry logic
  - Connection pooling
  - Timeout handling

### 3. Registry Patient Connect (PySide6 App)
**หน้าที่หลัก**: ระบบจัดการข้อมูลผู้ป่วยและตารางผ่าตัด

#### Features:
- **Database (SQLAlchemy + SQLite)**
  - Comprehensive surgery case schema
  - Indexed queries
  - Migration support

- **UI Components**
  - Patient registration form
  - Schedule viewer
  - Dashboard with statistics
  - Report generation

- **Smart Features**
  - ICD-10 catalog integration
  - Operation suggestions
  - Diagnosis auto-complete
  - Fuzzy search (rapidfuzz)

---

## 💾 Data Flow

### 1. Patient Registration Flow
```
Registry → Input Form → Validate → Database → API → Server Display
```

### 2. Status Update Flow
```
Client → Status Change → API POST → Database → WebSocket Broadcast
                                           ↓
                                    All Connected Clients
```

### 3. Auto-Transition Flow
```
Background Service → Check Status → Apply Rules → Update DB → Broadcast
```

---

## 🔐 Security & Authentication

### Token System
```python
DEFAULT_SECRET = "uTCoBelMyNfSSNmUulT_Kz6zrrCVkvD578MxEuLKZoaaXX0pVlpAD8toYHBxsFxI"
SURGIBOT_SECRET = os.environ.get("SURGIBOT_SECRET", DEFAULT_SECRET)
```

### Data Protection
- HN Masking: `590166XXX` format
- Token-based authentication
- Encrypted connections
- Audit logging

---

## 🌐 Network Architecture

### Ports & Endpoints
```yaml
API Server:
  - Host: 0.0.0.0
  - Port: 8088
  - Protocol: HTTP (WebSocket upgrade)

WebSocket:
  - Endpoint: ws://host:8088/api/ws
  - Protocol: WebSocket

Google Sheets:
  - API: sheets.googleapis.com
  - Auth: Service Account (OAuth2)
```

### Communication Protocols
1. **REST API** - CRUD operations
2. **WebSocket** - Real-time bidirectional updates
3. **Google Sheets API** - Backup sync
4. **SQLite/PostgreSQL** - Local persistence

---

## 🎨 UI/UX Design

### Color Scheme
```python
STATUS_COLORS = {
    "รอผ่าตัด":        "#facc15",  # Yellow
    "กำลังผ่าตัด":      "#f97316",  # Orange
    "กำลังพักฟื้น":     "#38bdf8",  # Blue
    "พักฟื้นครบแล้ว":   "#22c55e",  # Green
    "กำลังส่งกลับตึก":  "#a855f7",  # Purple
    "เลื่อนการผ่าตัด":  "#64748b"   # Gray
}
```

### OR Room Colors
```python
OR_HEADER_COLORS = {
    "OR1": "#3b82f6",  "OR2": "#10b981",  "OR3": "#f59e0b",
    "OR4": "#ef4444",  "OR5": "#a855f7",  "OR6": "#06b6d4",
    "OR7": "#f97316",  "OR8": "#64748b"
}
```

---

## 📦 New Modular Structure

```
surgibot/
├── surgibot/
│   ├── __init__.py
│   ├── config/
│   │   ├── settings.py         # Pydantic settings
│   │   └── constants.py        # Status, colors, etc.
│   ├── core/
│   │   ├── models.py           # Pydantic models
│   │   └── database.py         # SQLAlchemy ORM
│   ├── server/
│   │   ├── api/
│   │   │   ├── app.py          # FastAPI app
│   │   │   ├── routes.py       # API endpoints
│   │   │   └── websocket.py    # WebSocket handlers
│   │   ├── display/
│   │   │   └── window.py       # Tkinter display
│   │   ├── tts/
│   │   │   └── engine.py       # TTS engine
│   │   └── services/
│   │       ├── status.py       # Status management
│   │       └── sheets.py       # Google Sheets sync
│   ├── client/
│   │   ├── ui/
│   │   └── network/
│   ├── registry/
│   │   ├── ui/
│   │   └── database/
│   └── shared/
│       ├── security.py         # Auth, masking
│       ├── utils.py            # Helpers
│       └── logging_config.py   # Logging
├── tests/
├── docker/
│   ├── Dockerfile.server
│   ├── Dockerfile.client
│   └── docker-compose.yml
├── ARCHITECTURE.md
├── README.md
├── requirements-new.txt
├── setup.py
└── .env.example
```

---

## 🚀 Deployment

### Development
```bash
pip install -r requirements-new.txt
python -m surgibot.server.api.app
```

### Production (Docker)
```bash
docker-compose up -d
```

### Production (Manual)
```bash
uvicorn surgibot.server.api.app:app --host 0.0.0.0 --port 8088 --workers 4
```

---

## 🔄 State Management

### Transition Rules
```python
TRANSITIONS = {
    "waiting" → "operating": Manual,
    "operating" → "recovery": Manual,
    "recovery" → "complete": Auto(60min),
    "complete" → "returning": Auto(3min),
    "returning" → Delete: Auto(3min),
    "any" → "postponed": Manual
}
```

---

## 📝 Improvements in v2.0

### Architecture
✅ Migrated from Flask to FastAPI
✅ Added proper WebSocket support
✅ Implemented clean layered architecture
✅ Added Pydantic models for validation
✅ SQLAlchemy ORM instead of raw SQL

### Code Quality
✅ Type hints throughout
✅ Modular structure
✅ Separation of concerns
✅ Async/await patterns
✅ Comprehensive logging

### Features
✅ Better error handling
✅ Graceful degradation
✅ Configuration management
✅ Auto-transition service
✅ Background task scheduling

### DevOps
✅ Docker support
✅ Environment-based config
✅ Development/production modes
✅ API documentation (Swagger)
✅ Setup.py for installation

---

*Document Version: 2.0*
*Updated: November 2024*
*Architecture: Modernized & Refactored*
