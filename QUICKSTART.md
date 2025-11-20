# 🚀 SurgiBot - Quick Start Guide

**ระบบติดตามสถานะการผ่าตัดแบบ Real-time**

---

## 📦 ติดตั้งครั้งแรก

### 1. Clone & Setup

```bash
git clone <repository-url>
cd my-project
```

### 2. สร้าง Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. ติดตั้ง Dependencies

```bash
# สำหรับ API Server + Display (ไม่ต้องใช้ PySide6)
pip install --timeout=1000 fastapi uvicorn[standard] pydantic pydantic-settings sqlalchemy websockets requests python-dotenv python-multipart httpx python-dateutil

# ถ้าต้องการ Google Sheets
pip install gspread google-auth
```

### 4. สร้าง Database

```bash
python -c "from surgibot.core.database import get_db; get_db().create_tables(); print('✅ Database created!')"
```

### 5. ตั้งค่า Environment

```bash
# สร้าง .env
copy .env.example .env

# แก้ไขตามต้องการ (หรือใช้ค่าเริ่มต้น)
```

---

## 🎮 วิธีใช้งาน

### 🔹 แบบที่ 1: รันทั้งระบบ (2 Terminal)

#### Terminal 1: API Server

```bash
python run_server.py
```

**ผลลัพธ์:**
```
🚀 SurgiBot API Server
Server URL: http://0.0.0.0:8088
API Docs:   http://0.0.0.0:8088/docs
```

#### Terminal 2: Display Window

```bash
python run_display.py
```

**ผลลัพธ์:**
- หน้าต่างแสดงผล fullscreen
- เชื่อมต่อ WebSocket กับ API Server
- แสดงสถานะแบบ real-time

---

### 🔹 แบบที่ 2: รัน API Server อย่างเดียว (ใช้ Swagger UI)

```bash
python run_server.py
```

เปิดเบราว์เซอร์: http://localhost:8088/docs

---

## 📊 ทดสอบระบบ

### 1. Health Check

เปิดเบราว์เซอร์:
```
http://localhost:8088/api/health
```

**ผลลัพธ์:**
```json
{
  "ok": true,
  "timestamp": "2024-11-20T...",
  "version": "2.0.0"
}
```

### 2. เพิ่มข้อมูลผู้ป่วย

#### ใช้ Swagger UI:

1. เข้า http://localhost:8088/docs
2. กด **POST /api/update**
3. กด "Try it out"
4. ใส่ข้อมูล:

```json
{
  "token": "uTCoBelMyNfSSNmUulT_Kz6zrrCVkvD578MxEuLKZoaaXX0pVlpAD8toYHBxsFxI",
  "action": "add",
  "patient_id": "OR1-0-1",
  "status": "รอผ่าตัด",
  "eta_minutes": 90,
  "hn": "590166001"
}
```

5. กด "Execute"

#### ใช้ curl:

```bash
curl -X POST http://localhost:8088/api/update \
  -H "Content-Type: application/json" \
  -d '{
    "token": "uTCoBelMyNfSSNmUulT_Kz6zrrCVkvD578MxEuLKZoaaXX0pVlpAD8toYHBxsFxI",
    "action": "add",
    "patient_id": "OR1-0-1",
    "status": "รอผ่าตัด",
    "eta_minutes": 90,
    "hn": "590166001"
  }'
```

### 3. ดูรายการผู้ป่วย

```
http://localhost:8088/api/list
```

### 4. อัพเดตสถานะ

```json
{
  "token": "...",
  "action": "edit",
  "patient_id": "OR1-0-1",
  "status": "กำลังผ่าตัด",
  "eta_minutes": 120
}
```

### 5. ลบผู้ป่วย

```json
{
  "token": "...",
  "action": "delete",
  "patient_id": "OR1-0-1"
}
```

---

## 🎨 สถานะที่รองรับ

```
- รอผ่าตัด          (สีเหลือง)
- กำลังผ่าตัด        (สีส้ม)
- กำลังพักฟื้น       (สีฟ้า)
- พักฟื้นครบแล้ว     (สีเขียว)
- กำลังส่งกลับตึก    (สีม่วง)
- เลื่อนการผ่าตัด    (สีเทา)
```

---

## 🔧 การตั้งค่า

### Environment Variables (.env)

```bash
# API Server
SURGIBOT_API_HOST=0.0.0.0
SURGIBOT_API_PORT=8088
SURGIBOT_SECRET=your-secret-token

# Features
SURGIBOT_ENABLE_TTS=false           # Text-to-Speech
SURGIBOT_ENABLE_SHEETS=false        # Google Sheets sync
SURGIBOT_ENABLE_AUTO_TRANSITIONS=true

# Auto-transitions
SURGIBOT_RECOVERY_DURATION_HOURS=1
SURGIBOT_AUTO_DISCHARGE_DELAY_MIN=3
SURGIBOT_AUTO_DELETE_MIN=3

# Database
DATABASE_URL=sqlite:///./surgibot.db

# Logging
LOG_LEVEL=INFO
LOG_FILE=surgibot.log
```

---

## 🔍 Troubleshooting

### Port ชนกัน

```bash
# เปลี่ยน port ใน .env
SURGIBOT_API_PORT=8089
```

### Database Error

```bash
# ลบ database เดิม
rm surgibot.db

# สร้างใหม่
python -c "from surgibot.core.database import get_db; get_db().create_tables()"
```

### WebSocket ไม่เชื่อมต่อ

1. ตรวจสอบ API Server รันอยู่
2. ตรวจสอบ port 8088 ไม่ถูกบล็อก
3. ดู log ที่ `surgibot.log`

---

## 📁 โครงสร้างไฟล์

```
my-project/
├── run_server.py           # 🚀 รัน API Server
├── run_display.py          # 🖥️  รัน Display
├── surgibot/               # 📦 Main package
│   ├── config/             # ⚙️  Configuration
│   ├── core/               # 🗄️  Models & Database
│   ├── server/             # 🌐 Server components
│   │   ├── api/            # FastAPI app
│   │   ├── display/        # Tkinter display (✅ Phase 2)
│   │   ├── tts/            # Text-to-speech
│   │   └── services/       # Business logic
│   └── shared/             # 🔧 Utilities
├── ARCHITECTURE.md         # 📖 Architecture docs
├── README.md               # 📘 Full documentation
└── QUICKSTART.md           # 🚀 This file
```

---

## 🎯 What's Implemented

### ✅ Phase 1 (Completed)
- ✅ FastAPI Backend
- ✅ WebSocket support
- ✅ Database (SQLAlchemy + SQLite)
- ✅ Status management service
- ✅ Google Sheets integration
- ✅ TTS engine
- ✅ Configuration management
- ✅ Logging system

### ✅ Phase 2 (Completed)
- ✅ Display Window (Tkinter)
- ✅ WebSocket client for Display
- ✅ Real-time updates
- ✅ Launcher scripts

### 🚧 Future (Phase 3)
- ⏳ Client UI (PySide6) - for staff
- ⏳ Registry UI (PySide6) - for patient management
- ⏳ Mobile app

---

## 💡 Tips

1. **ใช้ Swagger UI** (http://localhost:8088/docs) สำหรับทดสอบ API
2. **เปิด 2 terminal** - 1 สำหรับ Server, 1 สำหรับ Display
3. **ดู logs** ที่ `surgibot.log` เมื่อเจอปัญหา
4. **ESC key** เพื่อออกจาก fullscreen (Display)

---

## 🆘 Need Help?

- 📖 ดู [ARCHITECTURE.md](ARCHITECTURE.md) สำหรับ technical details
- 📘 ดู [README.md](README.md) สำหรับ complete guide
- 🐛 Issues: [GitHub Issues](https://github.com/...)

---

**Made with ❤️ for Nongbua Lamphu Hospital**
