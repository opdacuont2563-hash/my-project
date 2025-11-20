"""
Utility functions for common operations.
Date/time formatting, parsing, and other helpers.
"""

from datetime import datetime, timedelta, date, time
from typing import Optional, Union


def format_timedelta(td: timedelta) -> str:
    """
    Format timedelta as HH:MM:SS.

    Args:
        td: Timedelta to format

    Returns:
        Formatted string (e.g., "02:30:45")
    """
    total_seconds = int(abs(td.total_seconds()))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """
    Parse ISO format datetime string.

    Args:
        dt_str: ISO datetime string

    Returns:
        datetime object or None if invalid
    """
    if not dt_str or not isinstance(dt_str, str):
        return None

    try:
        # Remove 'Z' suffix and parse
        cleaned = dt_str.replace("Z", "").strip()
        return datetime.fromisoformat(cleaned)
    except (ValueError, AttributeError):
        return None


def parse_date(date_str: Optional[str]) -> Optional[date]:
    """
    Parse date string in various formats.

    Args:
        date_str: Date string

    Returns:
        date object or None if invalid
    """
    if not date_str or not isinstance(date_str, str):
        return None

    date_str = date_str.strip()
    if not date_str:
        return None

    # Try ISO format first
    try:
        cleaned = date_str.replace("Z", "")
        return datetime.fromisoformat(cleaned).date()
    except ValueError:
        pass

    # Try common formats
    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    return None


def calculate_eta(
    start_time: datetime, duration_minutes: int
) -> tuple[datetime, int]:
    """
    Calculate ETA and remaining time.

    Args:
        start_time: Start timestamp
        duration_minutes: Duration in minutes

    Returns:
        Tuple of (eta_datetime, remaining_seconds)
    """
    eta_dt = start_time + timedelta(minutes=duration_minutes)
    now = datetime.now()
    remaining_seconds = int((eta_dt - now).total_seconds())
    return eta_dt, remaining_seconds


def get_current_time_window() -> str:
    """
    Get current time window (in-hours, after-hours, out-of-hours).

    Returns:
        Time window string
    """
    now = datetime.now()
    current_time = now.time()
    is_weekday = now.weekday() < 5  # Monday = 0, Sunday = 6

    # InHours: 07:00 - 16:00 (weekdays)
    if is_weekday and time(7, 0) <= current_time < time(16, 0):
        return "in-hours"

    # AfterHours: 16:00 - 20:00 (weekdays)
    if is_weekday and time(16, 0) <= current_time < time(20, 0):
        return "after-hours"

    # OutOfHours: everything else
    return "out-of-hours"


def sanitize_string(s: Optional[str], max_length: int = 255) -> Optional[str]:
    """
    Sanitize string for safe storage/display.

    Args:
        s: String to sanitize
        max_length: Maximum length

    Returns:
        Sanitized string or None
    """
    if not s or not isinstance(s, str):
        return None

    # Strip whitespace
    s = s.strip()
    if not s:
        return None

    # Truncate to max length
    if len(s) > max_length:
        s = s[:max_length]

    return s


def format_thai_datetime(dt: datetime) -> str:
    """
    Format datetime in Thai-friendly format.

    Args:
        dt: datetime to format

    Returns:
        Formatted string (e.g., "20 พ.ย. 2567 เวลา 14:30")
    """
    thai_months = [
        "ม.ค.",
        "ก.พ.",
        "มี.ค.",
        "เม.ย.",
        "พ.ค.",
        "มิ.ย.",
        "ก.ค.",
        "ส.ค.",
        "ก.ย.",
        "ต.ค.",
        "พ.ย.",
        "ธ.ค.",
    ]

    day = dt.day
    month = thai_months[dt.month - 1]
    year = dt.year + 543  # Buddhist Era
    time_str = dt.strftime("%H:%M")

    return f"{day} {month} {year} เวลา {time_str}"


def is_valid_hn(hn: Optional[str]) -> bool:
    """
    Validate Hospital Number format.

    Args:
        hn: Hospital Number to validate

    Returns:
        True if valid, False otherwise
    """
    if not hn or not isinstance(hn, str):
        return False

    hn = hn.strip()
    return hn.isdigit() and len(hn) == 9


def generate_patient_id(or_room: str, queue: Union[int, str]) -> str:
    """
    Generate patient ID from OR room and queue number.

    Args:
        or_room: Operating room identifier
        queue: Queue number

    Returns:
        Patient ID string (e.g., "OR1-0-2")
    """
    return f"{or_room}-{queue}"


def parse_patient_id(patient_id: str) -> Optional[tuple[str, str]]:
    """
    Parse patient ID into OR room and queue.

    Args:
        patient_id: Patient ID string (e.g., "OR1-0-2")

    Returns:
        Tuple of (or_room, queue) or None if invalid
    """
    if not patient_id or "-" not in patient_id:
        return None

    parts = patient_id.split("-", 1)
    if len(parts) != 2:
        return None

    return parts[0], parts[1]
