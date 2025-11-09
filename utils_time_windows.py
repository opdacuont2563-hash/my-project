"""Time window helpers for OR registry scheduling."""
from __future__ import annotations

from datetime import datetime, time, timedelta

IN_START = time(8, 30)
IN_END = time(16, 30)


def overlaps_in_hours(start: datetime, end: datetime) -> bool:
    """Return True if the interval overlaps any weekday in-hours window."""
    if end <= start:
        return False
    current_day = start.date()
    last_day = end.date()
    while current_day <= last_day:
        if datetime.combine(current_day, time()).weekday() < 5:
            win_start = datetime.combine(current_day, IN_START)
            win_end = datetime.combine(current_day, IN_END)
            if max(start, win_start) < min(end, win_end):
                return True
        current_day += timedelta(days=1)
    return False


def decide_service_window(urgency: str, start: datetime, end: datetime) -> str:
    """Return the service window classification from urgency + interval."""
    if end <= start:
        return "OutOfHours"
    normalized = (urgency or "").strip().title()
    if normalized == "Elective":
        same_day = start.date() == end.date()
        weekday = start.weekday() < 5
        fully_in = (
            weekday
            and same_day
            and IN_START <= start.time() <= IN_END
            and IN_START <= end.time() <= IN_END
        )
        return "InHours" if fully_in else "OutOfHours"
    return "InHours" if overlaps_in_hours(start, end) else "OutOfHours"


def categorize_timebucket(dt: datetime) -> str:
    """Return the Thai time bucket label (ในเวลา/นอกเวลา) for a timestamp."""
    weekday = dt.weekday()
    in_hours = 0 <= weekday <= 4 and IN_START <= dt.time() < IN_END
    return "ในเวลา" if in_hours else "นอกเวลา"


__all__ = [
    "IN_START",
    "IN_END",
    "overlaps_in_hours",
    "decide_service_window",
    "categorize_timebucket",
]
