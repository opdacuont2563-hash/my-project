# -*- coding: utf-8 -*-
"""result_schedule_runner_addon_compat
--------------------------------------
Compat helper that wires runner roster UI features into the existing
Result Schedule page while staying functional even when the newer
``registry_patient_connect`` helpers are unavailable.

If the latest ``registry_patient_connect`` module is present the helper
reuses its classes directly.  Otherwise a trimmed down fallback
implementation bundled in this file is used instead so the UI can still
offer runner assignment controls without import errors.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional, Set, Tuple

import os

# ---------------------------------------------------------------------------
# Attempt to import the latest helpers.  If they are missing we fall back to
# minimal in-file implementations so the UI keeps working.
# ---------------------------------------------------------------------------
USING_FALLBACK = False
try:  # pragma: no cover - runtime import probe
    from registry_patient_connect import (  # type: ignore
        DispatchEngine as _RealDispatchEngine,
        RosterStore as _RealRosterStore,
        ScheduleEntry as _RealScheduleEntry,
        SurgeryStatus as _RealSurgeryStatus,
        compute_eta as _real_compute_eta,
        pickup_id_for_entry as _real_pickup_id_for_entry,
        shift_key_now as _real_shift_key_now,
        tick_returning_cron as _real_tick_returning_cron,
    )
except Exception:  # pragma: no cover - fallback path
    USING_FALLBACK = True


# ---------------------------------------------------------------------------
# Fallback core (lightweight versions of the scheduling helpers).
# ---------------------------------------------------------------------------
if USING_FALLBACK:  # pragma: no cover - exercised only when imports fail
    from typing import Any

    RETURNING_GRACE_SEC = int(os.getenv("RETURNING_GRACE_SEC", "180"))
    TURNOVER_BUFFER_MIN = int(os.getenv("TURNOVER_BUFFER_MIN", "12"))
    DEFAULT_RUNNERS = [
        "นาที",
        "อนุพันธ์",
        "กฤษณพงษ์",
        "จีระวัฒน์",
        "นัฐพงษ์",
        "ศราวุธ",
        "รัตนพล",
        "อนุพงษ์",
    ]
    RUNNER_PUSHED_STATES = {"waiting", "picking", "arrived"}

    class SurgeryStatus(str):
        WAITING = "WAITING"
        IN_SURGERY = "IN_SURGERY"
        RECOVERY = "RECOVERY"
        RETURNING = "RETURNING"
        POSTPONED = "POSTPONED"
        CANCELLED = "CANCELLED"
        DONE = "DONE"

    @dataclass
    class ScheduleEntry:  # noqa: D401 - simple data container
        case_id: str
        hn: str
        name: str
        diagnosis: str = ""
        operation: str = ""
        surgeon: str = ""
        ward: str = ""
        or_room: str = ""
        schedule_time: Optional[datetime] = None
        expected_duration_min: int = 60
        status: str = SurgeryStatus.WAITING
        start_time: Optional[datetime] = None
        finish_time: Optional[datetime] = None
        recovery_start: Optional[datetime] = None
        returning_started_at: Optional[datetime] = None
        returned_to_ward_at: Optional[datetime] = None
        done_time: Optional[datetime] = None
        pushed_to_runner: bool = False
        extra: Dict[str, Any] = field(default_factory=dict)

    def _format_countdown(delta: timedelta) -> str:
        seconds = max(0, int(delta.total_seconds()))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"

    def compute_eta(entry: ScheduleEntry) -> Tuple[Optional[datetime], Optional[str]]:
        now = datetime.now()
        if entry.status == SurgeryStatus.WAITING:
            if entry.schedule_time:
                return entry.schedule_time, _format_countdown(entry.schedule_time - now)
            return None, None
        if entry.status == SurgeryStatus.IN_SURGERY and entry.start_time:
            eta = entry.start_time + timedelta(minutes=entry.expected_duration_min)
            if (now - entry.start_time).total_seconds() > entry.expected_duration_min * 60:
                eta = now + timedelta(seconds=int(entry.expected_duration_min * 9))
            return eta, _format_countdown(eta - now)
        if entry.status == SurgeryStatus.RECOVERY and entry.finish_time:
            eta = entry.finish_time + timedelta(minutes=TURNOVER_BUFFER_MIN)
            return eta, _format_countdown(eta - now)
        if entry.status == SurgeryStatus.RETURNING and entry.returning_started_at:
            eta = entry.returning_started_at + timedelta(seconds=RETURNING_GRACE_SEC)
            return eta, _format_countdown(eta - now)
        return None, None

    def shift_key_now(moment: Optional[datetime] = None) -> str:
        moment = moment or datetime.now()
        hhmm = int(moment.strftime("%H%M"))
        if 830 <= hhmm < 1630:
            base = "morning"
        elif 1630 <= hhmm < 2430:
            base = "evening"
        else:
            base = "night"
        key = base
        if moment.weekday() >= 5:
            key = f"holiday_{base}"
        return key

    def pickup_id_for_entry(entry: ScheduleEntry, override_or: Optional[str] = None) -> str:
        or_room = (override_or or entry.or_room or "-").strip()
        day = entry.schedule_time.strftime("%Y%m%d") if entry.schedule_time else date.today().strftime("%Y%m%d")
        return f"{or_room}-{day}-{entry.case_id}"

    class RosterStore:
        def __init__(self, path: str = "runner_roster.json") -> None:
            self.path = path
            self.data: Dict[str, Any] = {"master": list(DEFAULT_RUNNERS), "roster": {}, "shift_pointers": {}}
            self._load()

        def _load(self) -> None:
            if not os.path.exists(self.path):
                return
            import json

            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    payload = json.load(fh)
            except Exception:
                return
            if isinstance(payload, dict):
                master = payload.get("master")
                if isinstance(master, list):
                    self.data["master"] = [str(item).strip() for item in master if str(item).strip()]
                roster = payload.get("roster")
                if isinstance(roster, dict):
                    self.data["roster"] = roster
                pointers = payload.get("shift_pointers")
                if isinstance(pointers, dict):
                    self.data["shift_pointers"] = pointers

        def _save(self) -> None:
            import json

            try:
                with open(self.path, "w", encoding="utf-8") as fh:
                    json.dump(self.data, fh, ensure_ascii=False, indent=2)
            except Exception:
                pass

        def set_master(self, names: List[str]) -> None:
            cleaned = [str(item).strip() for item in names if str(item).strip()]
            self.data["master"] = cleaned or list(DEFAULT_RUNNERS)
            self._save()

        def get_master(self) -> List[str]:
            return list(self.data.get("master", [])) or list(DEFAULT_RUNNERS)

        def set_shift(self, key: str, **roles: str) -> None:
            roster = {role.upper(): str(name).strip() for role, name in roles.items() if str(name).strip()}
            self.data.setdefault("roster", {})[key] = roster
            self._save()

        def get_shift(self, key: str) -> Dict[str, str]:
            roster = self.data.get("roster", {}).get(key, {})
            return {role: str(name) for role, name in roster.items()}

        def get_ptr(self, key: str) -> int:
            return int(self.data.get("shift_pointers", {}).get(key, 0) or 0)

        def set_ptr(self, key: str, value: int) -> None:
            self.data.setdefault("shift_pointers", {})[key] = int(value)
            self._save()

        def roster_for_now(self) -> List[str]:
            key = shift_key_now()
            roster = self.get_shift(key)
            ordered = [roster.get(role, "") for role in ("P3", "P1", "P2", "OUTER")]
            cleaned = [name for name in ordered if name]
            return cleaned or self.get_master()

    class RunnerBoard:
        def __init__(self) -> None:
            self._store: Dict[str, Dict[str, Any]] = {}

        def fetch_status_map(self) -> Dict[str, Dict[str, Any]]:
            return dict(self._store)

        def push_entries(self, entries: List[ScheduleEntry]) -> Tuple[bool, List[str]]:
            errors: List[str] = []
            for entry in entries:
                pickup_id = pickup_id_for_entry(entry)
                if pickup_id in self._store and self._store[pickup_id]["status"] in RUNNER_PUSHED_STATES:
                    continue
                self._store[pickup_id] = {
                    "status": "waiting",
                    "assignee": None,
                    "payload": asdict(entry),
                }
            return True, errors

        def ack(self, pickup_id: str, runner: str) -> None:
            slot = self._store.setdefault(pickup_id, {"status": "waiting", "payload": {}, "assignee": None})
            slot["assignee"] = runner
            slot["status"] = "picking"

    def _base_order(key: str) -> List[str]:
        return {
            "morning": ["P3", "P1", "P2"],
            "evening": ["P1", "P2"],
            "night": ["P1"],
            "holiday_morning": ["P1"],
            "holiday_evening": ["P1", "P2"],
            "holiday_night": ["P1"],
        }.get(key, ["P1", "P2", "P3", "OUTER"])

    class DispatchEngine:
        def __init__(self, roster: Optional[RosterStore] = None, board: Optional[RunnerBoard] = None) -> None:
            self.roster = roster or RosterStore()
            self.board = board or RunnerBoard()

        def busy_names(self) -> Set[str]:
            busy: Set[str] = set()
            for row in self.board.fetch_status_map().values():
                assignee = str(row.get("assignee") or "").strip()
                status = str(row.get("status") or "").strip().lower()
                if assignee and status in RUNNER_PUSHED_STATES:
                    busy.add(assignee)
            return busy

        def next_runner(self) -> Optional[str]:
            shift = shift_key_now()
            roles = self.roster.get_shift(shift)
            base_order = [roles.get(role, "") for role in _base_order(shift)]
            queue = [name for name in base_order if name] or self.roster.get_master()
            if not queue:
                return None
            pointer = self.roster.get_ptr(shift)
            busy = self.busy_names()
            for offset in range(len(queue)):
                idx = (pointer + offset) % len(queue)
                candidate = queue[idx]
                if candidate not in busy:
                    self.roster.set_ptr(shift, idx + 1)
                    return candidate
            self.roster.set_ptr(shift, (pointer + 1) % len(queue))
            return None

    def _pick_next(entries: List[ScheduleEntry], board: RunnerBoard) -> Optional[ScheduleEntry]:
        status_map = board.fetch_status_map()

        def _is_pushed(entry: ScheduleEntry) -> bool:
            slot = status_map.get(pickup_id_for_entry(entry))
            if not slot:
                return False
            return str(slot.get("status") or "").strip().lower() in RUNNER_PUSHED_STATES

        candidates = [
            entry
            for entry in entries
            if entry.status in {SurgeryStatus.WAITING, SurgeryStatus.IN_SURGERY, SurgeryStatus.RECOVERY}
            and not _is_pushed(entry)
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda entry: entry.schedule_time.strftime("%H%M") if entry.schedule_time else "9999")
        return candidates[0]

    def tick_returning_cron(
        entries: List[ScheduleEntry],
        engine: DispatchEngine,
        on_db_insert: Optional[Callable[[ScheduleEntry], None]] = None,
        on_banner: Optional[Callable[[str, ScheduleEntry], None]] = None,
    ) -> None:
        now = datetime.now()
        for entry in entries:
            if entry.status != SurgeryStatus.RETURNING or not entry.returning_started_at:
                continue
            if (now - entry.returning_started_at).total_seconds() < RETURNING_GRACE_SEC:
                continue
            entry.returned_to_ward_at = entry.returned_to_ward_at or now
            if entry.finish_time:
                entry.status = SurgeryStatus.DONE
                entry.done_time = now
                if on_db_insert:
                    on_db_insert(entry)
                next_case = _pick_next(entries, engine.board)
                if not next_case:
                    continue
                ok, _ = engine.board.push_entries([next_case])
                if not ok:
                    continue
                runner = engine.next_runner()
                if runner:
                    engine.board.ack(pickup_id_for_entry(next_case), runner)
                next_case.pushed_to_runner = True
                if on_banner:
                    on_banner("ok", entry)
            else:
                if on_banner:
                    on_banner("postop_pending", entry)

else:  # USING_FALLBACK is False
    DispatchEngine = _RealDispatchEngine
    RosterStore = _RealRosterStore
    ScheduleEntry = _RealScheduleEntry
    SurgeryStatus = _RealSurgeryStatus
    compute_eta = _real_compute_eta
    pickup_id_for_entry = _real_pickup_id_for_entry
    shift_key_now = _real_shift_key_now
    tick_returning_cron = _real_tick_returning_cron


# ---------------------------------------------------------------------------
# UI helper (shared between real and fallback implementations).
# ---------------------------------------------------------------------------
from PySide6 import QtCore, QtWidgets  # type: ignore

try:  # pragma: no cover - optional UI extras
    from ui_runner_components import (  # type: ignore
        ResultScheduleTopBar,
        RunnerConsoleDialog,
        RunnerRosterPanel,
    )
except Exception:  # pragma: no cover - UI widgets optional
    ResultScheduleTopBar = None
    RunnerConsoleDialog = None
    RunnerRosterPanel = None


class ResultScheduleRunnerAddon(QtCore.QObject):
    """Embed runner roster widgets and assignment helpers into a schedule table."""

    def __init__(
        self,
        parent_container: QtWidgets.QWidget,
        table: QtWidgets.QTableWidget,
        entries_provider: Callable[[], List[ScheduleEntry]],
        cron_sec: int = 30,
    ) -> None:
        super().__init__(parent_container)
        self.parent_container = parent_container
        self.table = table
        self.entries_provider = entries_provider
        self.roster = RosterStore()
        self.engine = DispatchEngine(self.roster)  # type: ignore[arg-type]
        self.cron_sec = cron_sec
        self._assign_col: Optional[int] = None
        self._eta_col: Optional[int] = None
        self._cd_col: Optional[int] = None
        self._topbar: Optional[QtWidgets.QWidget] = None
        self._roster_panel: Optional[QtWidgets.QWidget] = None

        self._cron_timer = QtCore.QTimer(self)
        self._cron_timer.timeout.connect(self._tick_cron)
        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh)

    def install(self) -> None:
        self._ensure_layout()
        self._ensure_topbar_and_roster()
        self._ensure_columns()
        self._cron_timer.start(int(self.cron_sec * 1000))
        self._refresh_timer.start(1500)
        self.refresh()

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        entries = self.entries_provider() or []
        rows = self.table.rowCount()
        for row in range(min(rows, len(entries))):
            entry = entries[row]
            eta, countdown = compute_eta(entry)
            if self._eta_col is not None:
                self._set_item(row, self._eta_col, "" if not eta else eta.strftime("%H:%M"))
            if self._cd_col is not None:
                self._set_item(row, self._cd_col, countdown or "-")
            if self._assign_col is not None:
                widget = self.table.cellWidget(row, self._assign_col)
                if not isinstance(widget, QtWidgets.QToolButton):
                    button = QtWidgets.QToolButton(self.table)
                    button.setText("Assign")
                    button.setToolTip("ส่งเคสนี้ให้เวรเปลตามคิวกะ/ความแฟร์")
                    button.clicked.connect(lambda _=False, idx=row: self._assign_row(idx))
                    self.table.setCellWidget(row, self._assign_col, button)

    def _set_item(self, row: int, column: int, text: str) -> None:
        item = self.table.item(row, column)
        if item is None:
            item = QtWidgets.QTableWidgetItem()
            self.table.setItem(row, column, item)
        item.setText(text)

    def _ensure_layout(self) -> None:
        layout = self.parent_container.layout()
        if layout is None:
            layout = QtWidgets.QVBoxLayout(self.parent_container)
            self.parent_container.setLayout(layout)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        widgets = [layout.itemAt(i).widget() for i in range(layout.count()) if layout.itemAt(i).widget()]
        if self.table.parent() is self.parent_container and self.table not in widgets:
            layout.addWidget(self.table)

    def _ensure_topbar_and_roster(self) -> None:
        layout = self.parent_container.layout()
        if ResultScheduleTopBar is not None and self._topbar is None:
            self._topbar = ResultScheduleTopBar(self.engine)  # type: ignore[arg-type]
            layout.insertWidget(0, self._topbar, alignment=QtCore.Qt.AlignRight)
        if RunnerRosterPanel is not None and self._roster_panel is None:
            self._roster_panel = RunnerRosterPanel(self.engine, self.entries_provider())  # type: ignore[arg-type]
            group = QtWidgets.QGroupBox("เวรเปล/กะวันนี้", self.parent_container)
            wrapper = QtWidgets.QVBoxLayout(group)
            wrapper.addWidget(self._roster_panel)
            layout.addWidget(group)
            if hasattr(self._roster_panel, "openConsoleRequested") and RunnerConsoleDialog is not None:
                self._roster_panel.openConsoleRequested.connect(self._open_console)  # type: ignore[attr-defined]

    def _ensure_columns(self) -> None:
        headers = [
            self.table.horizontalHeaderItem(i).text() if self.table.horizontalHeaderItem(i) else ""
            for i in range(self.table.columnCount())
        ]
        if "ETA" not in headers:
            self._eta_col = self.table.columnCount()
            self.table.insertColumn(self._eta_col)
            self.table.setHorizontalHeaderItem(self._eta_col, QtWidgets.QTableWidgetItem("ETA"))
        else:
            self._eta_col = headers.index("ETA")

        headers = [
            self.table.horizontalHeaderItem(i).text() if self.table.horizontalHeaderItem(i) else ""
            for i in range(self.table.columnCount())
        ]
        if "Countdown" not in headers:
            self._cd_col = self.table.columnCount()
            self.table.insertColumn(self._cd_col)
            self.table.setHorizontalHeaderItem(self._cd_col, QtWidgets.QTableWidgetItem("Countdown"))
        else:
            self._cd_col = headers.index("Countdown")

        headers = [
            self.table.horizontalHeaderItem(i).text() if self.table.horizontalHeaderItem(i) else ""
            for i in range(self.table.columnCount())
        ]
        if "Assign" not in headers:
            self._assign_col = self.table.columnCount()
            self.table.insertColumn(self._assign_col)
            self.table.setHorizontalHeaderItem(self._assign_col, QtWidgets.QTableWidgetItem("Assign"))
        else:
            self._assign_col = headers.index("Assign")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _assign_row(self, row: int) -> None:
        entries = self.entries_provider() or []
        if row < 0 or row >= len(entries):
            QtWidgets.QMessageBox.warning(self.parent_container, "ไม่พบรายการ", "ไม่พบเคสในแถวนี้")
            return
        entry = entries[row]
        board = getattr(self.engine, "board", None)
        if board is None:
            QtWidgets.QMessageBox.warning(
                self.parent_container,
                "ไม่รองรับ",
                "ไม่พบ RunnerBoard ในระบบ กรุณาอัปเดต registry_patient_connect.py",
            )
            return
        ok, _ = board.push_entries([entry])
        if not ok:
            QtWidgets.QMessageBox.warning(
                self.parent_container,
                "ส่งงานไม่สำเร็จ",
                "ไม่สามารถส่งงานขึ้น Runner board ได้",
            )
            return
        runner = self.engine.next_runner()
        if runner:
            pickup_id = pickup_id_for_entry(entry)
            board.ack(pickup_id, runner)
            QtWidgets.QMessageBox.information(
                self.parent_container,
                "ส่งงานแล้ว",
                f"ส่งเคส {entry.case_id} ให้เวรเปล: {runner}",
            )
        else:
            QtWidgets.QMessageBox.information(
                self.parent_container,
                "ส่งงานแล้ว",
                "ส่งขึ้นบอร์ดแล้ว (ยังไม่ระบุผู้รับ)",
            )
        entry.pushed_to_runner = True
        self.refresh()

    def _open_console(self) -> None:
        if RunnerConsoleDialog is None:
            QtWidgets.QMessageBox.information(
                self.parent_container,
                "ไม่มีคอนโซล",
                "ไม่พบ RunnerConsoleDialog",
            )
            return
        dialog = RunnerConsoleDialog(self.engine, self.parent_container)  # type: ignore[arg-type]
        dialog.exec()

    def _tick_cron(self) -> None:
        def _noop_db(entry: ScheduleEntry) -> None:  # pragma: no cover - UI callback
            _ = entry

        def _noop_banner(_kind: str, _entry: ScheduleEntry) -> None:  # pragma: no cover - UI callback
            return

        try:
            entries = self.entries_provider() or []
            tick_returning_cron(entries, self.engine, _noop_db, _noop_banner)  # type: ignore[arg-type]
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Refresh timer callback proxies to :meth:`refresh`.
    # ------------------------------------------------------------------
    # Using a direct connection keeps PySide signal wiring straightforward.


__all__ = [
    "ResultScheduleRunnerAddon",
    "DispatchEngine",
    "RosterStore",
    "ScheduleEntry",
    "SurgeryStatus",
    "USING_FALLBACK",
]
