"""
Constants and configuration values used throughout the application.
Status definitions, color schemes, and other fixed values.
"""

from typing import Dict, List

# ===================== Surgery Status Flow =====================
STATUS_FLOW: List[str] = [
    "รอผ่าตัด",           # Waiting for surgery
    "กำลังผ่าตัด",        # In surgery
    "กำลังพักฟื้น",       # In recovery
    "พักฟื้นครบแล้ว",     # Recovery complete
    "กำลังส่งกลับตึก",    # Being transferred back to ward
    "เลื่อนการผ่าตัด",    # Surgery postponed
]

STATUS_CHOICES: List[str] = STATUS_FLOW

# English translations for status
STATUS_EN: Dict[str, str] = {
    "รอผ่าตัด": "waiting for surgery",
    "กำลังผ่าตัด": "in surgery",
    "กำลังพักฟื้น": "in recovery",
    "พักฟื้นครบแล้ว": "recovery complete",
    "กำลังส่งกลับตึก": "being transferred back to the ward",
    "เลื่อนการผ่าตัด": "surgery postponed",
}

# ===================== Color Schemes =====================
# Status colors (for UI display)
STATUS_COLORS: Dict[str, str] = {
    "รอผ่าตัด": "#facc15",        # Yellow
    "กำลังผ่าตัด": "#f97316",      # Orange
    "กำลังพักฟื้น": "#38bdf8",     # Blue
    "พักฟื้นครบแล้ว": "#22c55e",   # Green
    "กำลังส่งกลับตึก": "#a855f7",  # Purple
    "เลื่อนการผ่าตัด": "#64748b",  # Gray
}

# Light theme tag styles for Tkinter TreeView
TAG_STYLES_LIGHT: Dict[str, Dict[str, str]] = {
    "waiting": {"background": "#FFF4CC", "foreground": "#5D4037"},
    "surgery": {"background": "#D0EBFF", "foreground": "#0B3C5D"},
    "recovery": {"background": "#D3F9D8", "foreground": "#1B5E20"},
    "recovery_complete": {"background": "#B2F2E8", "foreground": "#0F5132"},
    "discharge": {"background": "#E5DEFF", "foreground": "#3D2C8D"},
    "postponed": {"background": "#ECEFF1", "foreground": "#37474F"},
}

# Pulse animation colors (for active status)
PULSE_LIGHT_A = "#D0EBFF"
PULSE_LIGHT_B = "#E3F3FF"

# ===================== Operating Room Configuration =====================
OR_ROOMS: List[str] = ["OR1", "OR2", "OR3", "OR4", "OR5", "OR6", "OR7", "OR8"]

OR_HEADER_COLORS: Dict[str, str] = {
    "OR1": "#3b82f6",  # Blue
    "OR2": "#10b981",  # Green
    "OR3": "#f59e0b",  # Amber
    "OR4": "#ef4444",  # Red
    "OR5": "#a855f7",  # Purple
    "OR6": "#06b6d4",  # Cyan
    "OR7": "#f97316",  # Orange
    "OR8": "#64748b",  # Gray
}

QUEUE_CHOICES: List[str] = ["0-1", "0-2", "0-3", "0-4", "0-5", "0-6", "0-7"]

# ===================== TTS Announcements =====================
PUBLIC_ANNOUNCEMENT_TH = (
    "ท่านใดที่ต้องการเดินทางไปยังจุดอื่นหรือไม่ได้อยู่ที่จุดรอผ่าตัดนี้ "
    "ท่านสามารถสแกนคิวอาร์โค้ดที่แสดงที่หน้าจอเพื่อติดตามสถานะการผ่าตัดแบบเรียลไทม์ออนไลน์ได้ตลอดเวลา "
    "โดยติดตามจากรหัสผู้ป่วยที่ท่านได้รับไปค่ะ ขอบคุณค่ะ"
)

PUBLIC_ANNOUNCEMENT_EN = (
    "If you need to go to another area or cannot remain in this surgical waiting area, "
    "please scan the QR code on the screen to follow the surgery status in real time. "
    "Use the patient code you were given. Thank you."
)

# ===================== Ward List =====================
WARD_LIST: List[str] = [
    "— กรุณาเลือก —",
    "หอผู้ป่วยอภิบาลสงฆ์",
    "หอผู้ป่วยพิเศษศัลยกรรม ชั้น 4",
    "หอผู้ป่วยศัลยกรรมกระดูกและข้อ",
    "หอผู้ป่วยศัลยกรรมหญิง",
    "หอผู้ป่วยศัลยกรรมชาย",
    "หอผู้ป่วยพิเศษอายุรกรรม ชั้น 5",
    "หอผู้ป่วยพิเศษอายุรกรรม ชั้น 4",
    "หอผู้ป่วยICU-MED",
    "หอผู้ป่วย ICU รวม",
    "หอผู้ป่วยอายุรกรรมหญิง",
    "หอผู้ป่วยอายุรกรรมชาย",
    "หอผู้ป่วยพิเศษรวมน้ำใจ",
    "หอผู้ป่วยหนักกุมารเวช",
    "หอผู้ป่วยหู ตา คอ จมูก",
    "หอผู้ป่วยกุมารเวช",
    "หอผู้ป่วยพิเศษสูติ-นรีเวช ชั้น 5",
    "หอผู้ป่วยพิเศษสูติ-นรีเวช ชั้น 4",
    "หอผู้ป่วยศัลยกรรมประสาทและสมอง",
    "หอผู้ป่วยสูติ-นรีเวช",
    "ห้องคลอด",
    "ห้องผ่าตัด",
    "แผนกอุบัติเหตุและฉุกเฉิน",
]

# ===================== Departments and Doctors =====================
DEPT_DOCTORS: Dict[str, List[str]] = {
    "Surgery | ศัลยกรรมทั่วไป": [
        "นพ.สุริยา คุณาชน",
        "นพ.ธนวัฒน์ พันธุ์พรหม",
        "พญ.สุภาภรณ์ พิณพาทย์",
        "พญ.รัฐพร ตั้งเพียร",
        "พญ.พิชัย สุวัฒนพูนลาภ",
    ],
    "Orthopedics | ศัลยกรรมกระดูกและข้อ": [
        "นพ.ชัชพล องค์โฆษิต",
        "นพ.ณัฐพงศ์ ศรีโพนทอง",
        "นพ.อำนาจ อนันต์วัฒนกุล",
        "นพ.อภิชาติ ลักษณะ",
        "นพ.กฤษฎา อิ้งอำพร",
        "นพ.วิษณุ ผูกพันธ์",
    ],
    "Urology | ศัลยกรรมระบบทางเดินปัสสาวะ": ["พญ.สายฝน บรรณจิตร์"],
    "ENT | ศัลยกรรม โสต ศอ นาสิก": [
        "พญ.พิรุณยา แสนวันดี",
        "พญ.สุทธิพร หมวดไธสง",
        "นพ.วรวิช พลเวียงธรรม",
    ],
    "Obstetrics-Gynecology | สูติ-นรีเวช": [
        "นพ.สุรจิตต์ นิมิตรวงษ์สกุล",
        "พญ.ขวัญตา ทุนประเทือง",
        "พญ.วัชราภรณ์ อนวัชชกุล",
        "พญ.รุ่งฤดี โขมพัตร",
        "พญ.ฐิติมน ชัยชนะทรัพย์",
    ],
    "Ophthalmology | จักษุ": [
        "นพ.สราวุธ สารีย์",
        "พญ.ดวิษา อังศรีประเสริฐ",
        "พญ.สาวิตรี ถนอมวงศ์ไทย",
        "พญ.สีกชมพู ตั้งสัตยาธิษฐาน",
        "พญ.นันท์นภัส ชีวะเกรียงไกร",
    ],
    "Maxillofacial | ศัลยกรรมขากรรไกร": [
        "นพ.ฉลองรัฐ เดชา",
        "พญ.อรุณนภา คิสารัง",
    ],
}

# ===================== Staff Lists =====================
SCRUB_NURSES: List[str] = [
    "อรุณี",
    "ศิวดาติ์",
    "กัญญณัช",
    "ชัญญาภัค",
    "สุนทรี",
    "พิศมัย",
    "เทวัญ",
    "กันต์พงษ์",
    "ปนัฏฐา",
    "สุจิตรา",
    "ชัยยงค์",
    "สุภาวัลย์",
    "จันทจร",
    "วรรณิภา",
    "ณัฐพงษ์",
    "ตะวัน",
    "ปวีณา",
    "นิฤมล",
    "ปริญญา",
    "สยุมพร",
    "สุรสิทธ์",
    "บุศรินทร์",
    "ศิริกัญญา",
    "นราวัตน์",
    "บัณฑิตา",
    "วรรณวิสา",
    "ชลดา",
    "วรีสา",
]

# ===================== API Endpoints =====================
API_ENDPOINTS = {
    "health": "/api/health",
    "list": "/api/list",
    "list_full": "/api/list_full",
    "update": "/api/update",
    "websocket": "/api/ws",
}

# ===================== Status Transitions =====================
# Define which status can transition to which status
STATUS_TRANSITIONS: Dict[str, List[str]] = {
    "รอผ่าตัด": ["กำลังผ่าตัด", "เลื่อนการผ่าตัด"],
    "กำลังผ่าตัด": ["กำลังพักฟื้น", "เลื่อนการผ่าตัด"],
    "กำลังพักฟื้น": ["พักฟื้นครบแล้ว"],
    "พักฟื้นครบแล้ว": ["กำลังส่งกลับตึก"],
    "กำลังส่งกลับตึก": [],
    "เลื่อนการผ่าตัด": ["รอผ่าตัด"],
}

# Statuses that require ETA
STATUSES_WITH_ETA = {"กำลังผ่าตัด", "กำลังพักฟื้น"}

# Statuses that trigger announcements
STATUSES_WITH_ANNOUNCEMENT = {
    "กำลังผ่าตัด",
    "กำลังพักฟื้น",
    "พักฟื้นครบแล้ว",
    "เลื่อนการผ่าตัด",
}
