"""Shared helpers for SurgiBot client and patient-facing tools.

This module centralises light-weight logic for describing the daily
operating-room (OR) plan and keeping historical registry snapshots in
sync with display quirks such as the Wednesday owner reassignment rule.

The original project keeps these helpers in the patient console.  The
client now imports them as well, but some deployments bundle the client
without that module.  Shipping this pared-down implementation restores
compatibility while following the same contract so both sides share the
behaviour.
"""
from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
import json
import re
from pathlib import Path
from typing import Iterable, Sequence, Any

try:  # Qt is available on the rich client; fall back gracefully for tests
    from PySide6.QtCore import QSettings  # type: ignore
except Exception:  # pragma: no cover - optional dependency during tests
    QSettings = None  # type: ignore

ORG_NAME = "ORNBH"
APP_SHARED = "SurgiBotShared"
ENTRIES_KEY = "schedule/entries"
PLAN_FILE = Path(__file__).with_name("or_plan.json")

# Known OR rooms used throughout the suite
KNOWN_OR_ROOMS = ("OR1", "OR2", "OR3", "OR4", "OR5", "OR6", "OR8")

# Basic speciality mapping used as a fallback for plan/owner hints.
_DEFAULT_SPECIALTY_LABELS = {
    "OR1": "ศัลยกรรมทั่วไป",
    "OR2": "ศัลยกรรมกระดูกและข้อ",
    "OR3": "ENT / ตา / ศัลยกรรมศีรษะ",
    "OR4": "สูติ-นรีเวช",
    "OR5": "ระบบทางเดินปัสสาวะ",
    "OR6": "ศัลยกรรมเฉพาะทาง",
    "OR8": "ศัลยกรรมร่วม / สำรอง",
}

# Keywords to infer OR ownership from free-form text.
_OWNER_KEYWORDS = (
    ("ศัลยกรรมทั่วไป", "OR1"),
    ("general", "OR1"),
    ("กระดูก", "OR2"),
    ("orth", "OR2"),
    ("กระดูกและข้อ", "OR2"),
    ("ent", "OR3"),
    ("หู", "OR3"),
    ("คอ", "OR3"),
    ("จมูก", "OR3"),
    ("ตา", "OR3"),
    ("สูติ", "OR4"),
    ("gyn", "OR4"),
    ("ob", "OR4"),
    ("นรีเวช", "OR4"),
    ("ปัสสาวะ", "OR5"),
    ("uro", "OR5"),
    ("กุมาร", "OR6"),
    ("pediatric", "OR6"),
)

_OR_PATTERN = re.compile(r"\bOR\s*-?\s*(\d)\b", re.IGNORECASE)


def _ensure_date(value: Any) -> date | None:
    """Normalise user supplied date inputs to a ``date`` instance."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        txt = value.strip()
        if not txt:
            return None
        for fmt in (
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y %H:%M:%S",
        ):
            try:
                return datetime.strptime(txt, fmt).date()
            except ValueError:
                continue
    return None


def _parse_date(value: Any) -> date | None:
    """Parse registry schedule dates."""
    if isinstance(value, (date, datetime)):
        return _ensure_date(value)
    if isinstance(value, str):
        txt = value.strip()
        if not txt:
            return None
        # Strip potential timezone suffixes
        txt = txt.replace("Z", "")
        parsed = _ensure_date(txt)
        if parsed:
            return parsed
        # Fallback: ISO with time first
        try:
            return datetime.fromisoformat(txt).date()
        except ValueError:
            return None
    return None


def _load_plan_overrides() -> dict[str, dict[str, str]]:
    if not PLAN_FILE.exists():
        return {}
    try:
        data = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for key, value in data.items():
        if not isinstance(key, str) or key.strip() == "":
            continue
        if not isinstance(value, dict):
            continue
        room = key.strip().upper()
        out[room] = {str(k): str(v) for k, v in value.items() if isinstance(k, str)}
    return out


def _room_from_owner(text: str) -> str | None:
    if not text:
        return None
    match = _OR_PATTERN.search(text)
    if match:
        room_code = f"OR{match.group(1)}"
        if room_code in KNOWN_OR_ROOMS:
            return room_code
    low = text.lower()
    for keyword, room in _OWNER_KEYWORDS:
        if keyword in low:
            return room
    return None


def _get(entry: Any, key: str, default: Any = "") -> Any:
    if entry is None:
        return default
    if isinstance(entry, dict):
        return entry.get(key, default)
    return getattr(entry, key, default)


def _set_or(entry: Any, value: str) -> None:
    if entry is None:
        return
    if isinstance(entry, dict):
        entry["or"] = value
        entry["or_room"] = value
    else:
        setattr(entry, "or_room", value)
        # Some payloads keep the raw dictionary in ``_extra``; mirror it.
        extra = getattr(entry, "_extra", None)
        if isinstance(extra, dict):
            extra["or"] = value
            extra["or_room"] = value


def normalize_owner_for_wednesday(entries: Sequence[Any], today: Any | None = None) -> list[Any]:
    """Reapply OR ownership rules for Wednesday schedules.

    Historically the registry stores mid-week ownership as free-form text
    ("ENT - OR3" etc.).  This helper mimics the patient console by
    forcing such rows back to the canonical OR code when the current day
    is Wednesday.  Other days are returned untouched.
    """
    if not entries:
        return list(entries) if isinstance(entries, Iterable) else []

    day = _ensure_date(today) or date.today()
    if day.weekday() != 2:  # Monday=0 … Sunday=6
        return list(entries)

    normalised: list[Any] = []
    for entry in entries:
        try:
            owner = str(_get(entry, "owner", "") or _get(entry, "or_owner", ""))
        except Exception:
            owner = ""
        room_hint = _room_from_owner(owner)
        if room_hint:
            _set_or(entry, room_hint)
        normalised.append(entry)
    return normalised


@lru_cache(maxsize=32)
def _snapshot_entries() -> list[dict[str, Any]]:
    if QSettings is None:  # pragma: no cover - headless unit tests
        return []
    try:
        settings = QSettings(ORG_NAME, APP_SHARED)
        raw = settings.value(ENTRIES_KEY, [])
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item.copy())
    return out


def _plan_label_from_entries(day: date, room: str) -> str:
    labels: list[str] = []
    for item in _snapshot_entries():
        item_room = str(item.get("or") or item.get("or_room") or "").strip()
        if not item_room:
            owner_hint = _room_from_owner(str(item.get("owner") or item.get("or_owner") or ""))
            if owner_hint:
                item_room = owner_hint
        if item_room != room:
            continue
        item_date = _parse_date(item.get("date"))
        if item_date and item_date != day:
            continue
        doctor = str(item.get("doctor") or "").strip()
        dept = str(item.get("dept") or "").strip()
        owner = str(item.get("owner") or item.get("or_owner") or "").strip()
        label = ""
        if doctor and dept and dept not in doctor:
            label = f"{doctor} ({dept})"
        elif doctor:
            label = doctor
        elif owner:
            label = owner
        if label and label not in labels:
            labels.append(label)
    return " \u2022 ".join(labels)


def describe_or_plan_label(day: Any | None, room: str) -> str:
    """Return the OR sub-label (doctor/plan) for the given day and room."""
    room = (room or "").strip().upper()
    if not room:
        return ""
    base_date = _ensure_date(day) or date.today()

    label = _plan_label_from_entries(base_date, room)
    if label:
        return label

    overrides = _load_plan_overrides()
    room_plan = overrides.get(room, {})
    weekday_key = str(base_date.weekday())
    if weekday_key in room_plan:
        return room_plan[weekday_key]
    if "default" in room_plan:
        return room_plan["default"]
    return _DEFAULT_SPECIALTY_LABELS.get(room, "")


__all__ = [
    "describe_or_plan_label",
    "normalize_owner_for_wednesday",
]
