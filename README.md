# 🏥 SurgiBot - Real-time Surgery Status Management System

**ระบบจัดการและติดตามสถานะการผ่าตัดแบบ Real-time สำหรับโรงพยาบาลหนองบัวลำภู**

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

---

## 📋 Overview

SurgiBot เป็นระบบบริหารจัดการห้องผ่าตัดแบบครบวงจร ออกแบบมาเพื่อให้โรงพยาบาลสามารถติดตามสถานะการผ่าตัดแบบ Real-time ประกอบด้วย 3 ส่วนหลัก:

### 🖥️ **SurgiBot Server**
- แสดงผลสถานะการผ่าตัดบนหน้าจอใหญ่ (Tkinter GUI)
- API Server (FastAPI) พร้อม WebSocket support
- ประกาศเสียงอัตโนมัติ (TTS) ภาษาไทย/อังกฤษ
- Sync ข้อมูลไป Google Sheets
- Auto-transition ตามเวลาที่กำหนด

### 💻 **SurgiBot Client**
- โปรแกรม Desktop สำหรับเจ้าหน้าที่ห้องผ่าตัด (PySide6)
- อัพเดตสถานะผู้ป่วยแบบ Real-time
- เชื่อมต่อ WebSocket กับ Server
- UI ที่ใช้งานง่าย รองรับหลายภาษา

### 📊 **Registry Patient Connect**
- จัดการข้อมูลผู้ป่วยและตารางผ่าตัด (PySide6)
- ฐานข้อมูล SQLite/PostgreSQL
- ICD-10 catalog integration
- รายงานและสถิติ

---

## ✨ Key Features

### 🔄 Real-time Updates
- WebSocket สำหรับ push notifications
- Auto-refresh ทุก 10 วินาที
- สถานะอัพเดตทันทีทุก station

### 🎯 Smart Auto-Transitions
- **กำลังพักฟื้น** → **พักฟื้นครบแล้ว** (1 ชั่วโมง)
- **พักฟื้นครบแล้ว** → **กำลังส่งกลับตึก** (3 นาที)
- **กำลังส่งกลับตึก** → **ลบอัตโนมัติ** (3 นาที)

### 🔊 Bilingual TTS Announcements
- ประกาศภาษาไทย + อังกฤษ
- ประกาศตามรอบเวลา (ปรับได้)
- ประกาศพิเศษเมื่อเลื่อนผ่าตัด

### 🎨 Modern UI/UX
- Color-coded status (Yellow, Orange, Blue, Green, Purple, Gray)
- Pulse animation สำหรับสถานะที่กำลังดำเนินการ
- Responsive design
- Dark mode support (Coming soon)

### 🔐 Security
- Token-based authentication
- HN masking (แสดง 6 ตัว + XXX)
- Audit logging
- Role-based access control

### 📈 Google Sheets Integration
- Auto-sync ข้อมูลไป Google Sheets
- Backup แบบ Real-time
- Graceful fallback ถ้าไม่พร้อมใช้งาน

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11 or higher
- pip
- Virtual environment (recommended)
- (Optional) Docker & Docker Compose

### Installation

#### 1. Clone Repository
```bash
git clone https://github.com/yourusername/surgibot.git
cd surgibot
```

#### 2. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

#### 3. Install Dependencies
```bash
pip install -r requirements-new.txt
```

#### 4. Setup Environment Variables
```bash
cp .env.example .env
# Edit .env with your configuration
```

#### 5. Initialize Database
```bash
python -c "from surgibot.core.database import get_db; get_db().create_tables()"
```

#### 6. Run Server
```bash
# Development mode
python -m surgibot.server.api.app

# Production mode
uvicorn surgibot.server.api.app:app --host 0.0.0.0 --port 8088 --workers 4
```

#### 7. Run Client (in another terminal)
```bash
python -m surgibot.client.ui.main_window
```

#### 8. Run Registry (in another terminal)
```bash
python -m surgibot.registry.ui.main_window
```

---

## 🐳 Docker Deployment

### Build and Run with Docker Compose
```bash
cd docker
docker-compose up -d
```

### Individual Services
```bash
# Server only
docker build -f docker/Dockerfile.server -t surgibot-server .
docker run -p 8088:8088 surgibot-server

# Client only
docker build -f docker/Dockerfile.client -t surgibot-client .
docker run surgibot-client
```

---

## ⚙️ Configuration

### Environment Variables

Create `.env` file in project root:

```bash
# API Server
SURGIBOT_API_HOST=0.0.0.0
SURGIBOT_API_PORT=8088
SURGIBOT_SECRET=your-secret-token-here

# Client
SURGIBOT_CLIENT_HOST=127.0.0.1
SURGIBOT_CLIENT_PORT=8088

# Features
SURGIBOT_ENABLE_SHEETS=true
SURGIBOT_ENABLE_TTS=true
SURGIBOT_ENABLE_AUTO_TRANSITIONS=true

# Auto-transitions
SURGIBOT_AUTO_DISCHARGE_DELAY_MIN=3
SURGIBOT_AUTO_DELETE_MIN=3
SURGIBOT_RECOVERY_DURATION_HOURS=1

# TTS
SURGIBOT_ANNOUNCE_MINUTES=20

# Google Sheets
SURGIBOT_SPREADSHEET_ID=your-spreadsheet-id
SURGIBOT_GCP_CREDENTIALS_JSON='{"type":"service_account",...}'

# Database
DATABASE_URL=sqlite:///./surgibot.db
# For PostgreSQL: postgresql://user:pass@localhost/surgibot

# Logging
LOG_LEVEL=INFO
LOG_FILE=surgibot.log
```

---

## 📖 API Documentation

### API Endpoints

Once server is running, visit:
- **Swagger UI**: http://localhost:8088/docs
- **ReDoc**: http://localhost:8088/redoc

### Main Endpoints

#### Health Check
```bash
GET /api/health
```

#### List Cases
```bash
# Public (masked HN)
GET /api/list

# Authenticated (full HN)
GET /api/list?token=YOUR_TOKEN
GET /api/list_full?token=YOUR_TOKEN
```

#### Update Status
```bash
POST /api/update
Content-Type: application/json

{
  "token": "YOUR_TOKEN",
  "action": "add|edit|delete",
  "patient_id": "OR1-0-2",
  "status": "กำลังผ่าตัด",
  "eta_minutes": 90,
  "hn": "590166994"
}
```

#### WebSocket
```javascript
const ws = new WebSocket('ws://localhost:8088/api/ws');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Status update:', data);
};
```

---

## 🧪 Development

### Run Tests
```bash
pytest
pytest --cov=surgibot tests/
```

### Code Quality
```bash
# Format code
black surgibot/
isort surgibot/

# Lint
flake8 surgibot/
mypy surgibot/
```

### Pre-commit Hooks
```bash
pre-commit install
pre-commit run --all-files
```

---

## 📁 Project Structure

```
surgibot/
├── surgibot/                   # Main package
│   ├── config/                 # Configuration & constants
│   ├── core/                   # Data models & database
│   ├── server/                 # Server components
│   │   ├── api/                # FastAPI app & routes
│   │   ├── display/            # Tkinter display (TODO)
│   │   ├── tts/                # Text-to-speech
│   │   └── services/           # Business logic
│   ├── client/                 # Client app (TODO)
│   ├── registry/               # Registry app (TODO)
│   └── shared/                 # Shared utilities
├── tests/                      # Unit tests
├── docker/                     # Docker configs
├── ARCHITECTURE.md             # Architecture documentation
├── README.md                   # This file
├── requirements-new.txt        # Production dependencies
├── requirements-dev.txt        # Development dependencies
└── setup.py                    # Package setup
```

---

## 🛠️ Tech Stack

### Backend
- **FastAPI** - Modern async web framework
- **SQLAlchemy** - ORM and database toolkit
- **Pydantic** - Data validation
- **WebSockets** - Real-time communication
- **gspread** - Google Sheets API

### Frontend
- **PySide6** - Qt for Python (Desktop GUI)
- **Tkinter** - Display monitor GUI

### Speech
- **gTTS** - Google Text-to-Speech
- **pygame** - Audio playback

### DevOps
- **Docker** - Containerization
- **uvicorn** - ASGI server
- **pytest** - Testing framework

---

## 🎯 Roadmap

### Version 2.0 (Current - In Progress)
- [x] FastAPI migration
- [x] WebSocket support
- [x] Modular architecture
- [x] Pydantic models
- [x] SQLAlchemy ORM
- [x] TTS engine
- [x] Google Sheets service
- [x] Auto-transition service
- [ ] Refactor Display module
- [ ] Refactor Client module
- [ ] Refactor Registry module

### Version 2.1 (Planned)
- [ ] PostgreSQL support
- [ ] Redis caching
- [ ] Advanced reporting
- [ ] Mobile app (React Native)
- [ ] Multi-hospital support
- [ ] Advanced analytics dashboard

### Version 3.0 (Future)
- [ ] Microservices architecture
- [ ] Kubernetes deployment
- [ ] AI-powered predictions
- [ ] Video conferencing integration
- [ ] IoT device integration

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

Please ensure:
- Code follows PEP 8 style guide
- All tests pass
- Documentation is updated
- Commit messages are descriptive

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 👥 Authors

**SurgiBot Team**
- Nongbua Lamphu Hospital IT Department
- Contributors: [See all contributors](https://github.com/yourusername/surgibot/contributors)

---

## 🙏 Acknowledgments

- โรงพยาบาลหนองบัวลำภู
- ทีมพัฒนาระบบสารสนเทศ
- เจ้าหน้าที่ห้องผ่าตัด
- All contributors and testers

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/surgibot/issues)
- **Email**: surgibot@hospital.go.th
- **Documentation**: [Full Docs](https://surgibot.readthedocs.io/)

---

## 🔗 Links

- [Architecture Documentation](ARCHITECTURE.md)
- [API Documentation](http://localhost:8088/docs)
- [Contributing Guidelines](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

---

**Made with ❤️ for better healthcare**

---

## 🎉 Phase 2 Completed: Display Window

### New in Phase 2

**✅ Server Display Module (Tkinter)**
- Full-screen display for large monitors
- Real-time WebSocket updates
- Color-coded status display
- Auto-refresh timers
- Connection status indicator

**✅ Launcher Scripts**
- `run_server.py` - Start API Server
- `run_display.py` - Start Display Window

**✅ Quick Start Guide**
- See [QUICKSTART.md](QUICKSTART.md) for step-by-step instructions

### How to Run Phase 2

#### Terminal 1: API Server
```bash
python run_server.py
```

#### Terminal 2: Display Window
```bash
python run_display.py
```

**That's it!** The display will auto-connect and show real-time updates.

---

## 📸 Phase 2 Features

### Display Window
- ✅ Fullscreen mode (ESC to exit)
- ✅ Real-time WebSocket connection
- ✅ Color-coded status (Yellow, Orange, Blue, Green, Purple, Gray)
- ✅ Countdown timers for recovery
- ✅ ETA calculations
- ✅ Connection status indicator
- ✅ Auto-reconnect on disconnect

### What's Next (Phase 3)
- Client UI for staff (PySide6)
- Registry UI for patient management (PySide6)
- Advanced reporting
- Mobile app support

---
