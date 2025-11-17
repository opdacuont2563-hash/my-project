"""Time window helpers for OR registry scheduling."""
from __future__ import annotations

from datetime import datetime, time, timedelta as _td

IN_START = time(8, 30)
IN_END = time(16, 30)


def overlaps_in_hours(start: datetime, end: datetime) -> bool:
    day = start.date()
    while day <= end.date():
        if datetime.combine(day, time()).weekday() < 5:  # Mon-Fri
            win_start = datetime.combine(day, IN_START)
            win_end = datetime.combine(day, IN_END)
            if max(start, win_start) < min(end, win_end):
                return True
        day += _td(days=1)
    return False


def decide_service_window(urgency: str, start: datetime, end: datetime) -> str:
    if urgency == "Elective":
        same_day = start.date() == end.date()
        weekday = start.weekday() < 5
        fully_in = (
            weekday
            and same_day
            and (IN_START <= start.time() <= IN_END)
            and (IN_START <= end.time() <= IN_END)
        )
        return "InHours" if fully_in else "OutOfHours"
    return "InHours" if overlaps_in_hours(start, end) else "OutOfHours"


__all__ = ["IN_START", "IN_END", "overlaps_in_hours", "decide_service_window"]
