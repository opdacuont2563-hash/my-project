# -*- coding: utf-8 -*-
"""Simplified SurgiBot client focused on schedule display.

This lightweight PySide6 interface trusts ``surgibot_patient_connect`` as the
single source of truth for operating-room ownership rules.  The client simply
pulls the prepared patient list and renders it in a sortable table.  When the
module exposes richer helpers (``get_patients_for_display`` /
``fetch_today_schedule`` + ``apply_owner_rules`` / ``OR_LABELS``), the client
uses them directly; otherwise it falls back gracefully to empty data.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Shared helpers imported from surgibot_patient_connect
# ---------------------------------------------------------------------------
try:
    from surgibot_patient_connect import get_patients_for_display  # type: ignore
except Exception:  # pragma: no cover - optional helper missing at runtime
    get_patients_for_display = None  # type: ignore

_fetch_fn = None
_apply_owner_rules = None
_or_labels: Dict[str, str] | None = None

if get_patients_for_display is None:
    try:
        from surgibot_patient_connect import fetch_today_schedule  # type: ignore

        _fetch_fn = fetch_today_schedule
    except Exception:  # pragma: no cover - optional helper missing at runtime
        _fetch_fn = None

    try:
        from surgibot_patient_connect import apply_owner_rules  # type: ignore

        _apply_owner_rules = apply_owner_rules
    except Exception:  # pragma: no cover - optional helper missing at runtime
        _apply_owner_rules = None
else:
    _fetch_fn = get_patients_for_display

try:
    from surgibot_patient_connect import OR_LABELS  # type: ignore

    _or_labels = dict(OR_LABELS)
except Exception:  # pragma: no cover - optional helper missing at runtime
    try:
        from surgibot_patient_connect import OR_MAP  # type: ignore

        _or_labels = dict(OR_MAP)
    except Exception:  # pragma: no cover - optional helper missing at runtime
        _or_labels = None


# ---------------------------------------------------------------------------
# Column definitions (key, header)
# ---------------------------------------------------------------------------
COLUMNS: List[tuple[str, str]] = [
    ("queue_no", "คิว"),
    ("hn", "HN"),
    ("patient_name", "ชื่อผู้ป่วย"),
    ("procedure", "หัตถการ"),
    ("department", "แผนก"),
    ("case_size", "ขนาดเคส"),
    ("or_room", "ห้องผ่าตัด"),
    ("surgeon", "ศัลยแพทย์"),
    ("anesth", "วิสัญญี"),
    ("schedule", "เวลา/ช่วง"),
    ("status", "สถานะ"),
]


# ---------------------------------------------------------------------------
# Table model
# ---------------------------------------------------------------------------
class PatientTableModel(QAbstractTableModel):
    def __init__(self, rows: List[Dict[str, Any]] | None = None):
        super().__init__()
        self._rows: List[Dict[str, Any]] = rows or []

    # -- metadata -----------------------------------------------------------------
    def rowCount(self, parent: QModelIndex | None = None) -> int:  # type: ignore[override]
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # type: ignore[override]
        return len(COLUMNS)

    def headerData(  # type: ignore[override]
        self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole
    ) -> Any:
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return COLUMNS[section][1]
        return section + 1

    # -- cell data ----------------------------------------------------------------
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:  # type: ignore[override]
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.ToolTipRole):
            return None

        row = self._rows[index.row()]
        key = COLUMNS[index.column()][0]
        value = row.get(key, "")

        if key == "or_room" and value and _or_labels:
            return _or_labels.get(str(value), value)

        return "" if value is None else str(value)

    # -- helpers ------------------------------------------------------------------
    def update_rows(self, rows: List[Dict[str, Any]]):
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()


# ---------------------------------------------------------------------------
# Data fetching helpers
# ---------------------------------------------------------------------------
def pull_rows(day: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Fetch schedule rows while trusting the patient-connect module rules."""

    if get_patients_for_display:
        try:
            return list(get_patients_for_display(day))  # type: ignore[misc]
        except Exception as exc:  # pragma: no cover - surface in logs only
            print("[client] get_patients_for_display() failed:", exc)

    if _fetch_fn and _apply_owner_rules:
        try:
            raw = list(_fetch_fn())  # type: ignore[misc]
            return list(_apply_owner_rules(raw, day))  # type: ignore[misc]
        except Exception as exc:  # pragma: no cover - surface in logs only
            print("[client] fetch/apply_owner_rules failed:", exc)

    return []


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class ClientWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(
            "SurgiBot Client — ตารางผู้ป่วยตามเงื่อนไขแพทย์เจ้าของห้อง"
        )
        self.resize(1200, 720)

        root = QVBoxLayout(self)

        # Information banner + refresh control
        header = QHBoxLayout()
        self.info = QLabel(
            "ข้อมูลมาจาก surgibot_patient_connect.py (กฎเจ้าของห้องเป็นแหล่งความจริง)"
        )
        self.btn_refresh = QPushButton("รีเฟรช (F5)")
        self.btn_refresh.clicked.connect(self.refresh)
        header.addWidget(self.info)
        header.addStretch(1)
        header.addWidget(self.btn_refresh)
        root.addLayout(header)

        # Table view
        self.table = QTableView()
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.model = PatientTableModel(pull_rows())
        self.table.setModel(self.model)
        root.addWidget(self.table)

        # Auto refresh every 60 seconds
        self._timer = QTimer(self)
        self._timer.setInterval(60_000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

        self._setup_shortcuts()

    # ------------------------------------------------------------------
    def _setup_shortcuts(self) -> None:
        try:
            from PySide6.QtGui import QKeySequence, QShortcut

            QShortcut(QKeySequence("F5"), self, activated=self.refresh)
        except Exception:  # pragma: no cover - optional when QtGui unavailable
            pass

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        rows = pull_rows()
        self.model.update_rows(rows)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    import sys

    app = QApplication(sys.argv)
    window = ClientWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
