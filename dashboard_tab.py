# -*- coding: utf-8 -*-
"""
Dashboard Tab สำหรับ OR — ใช้กับ PySide6 + SQLite (elective/emergency)
กราฟ: Matplotlib (ฝังใน QWidget)
แหล่งข้อมูล: schedule_elective.db, schedule_emergency.db
ตารางที่ใช้: postop_records, schedule, surgery_events
"""

from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Union

import numpy as np
import pandas as pd

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.ticker as mticker

# ----------------------------- Config -----------------------------
APP_DIR = Path(__file__).resolve().parent
DB_ELECTIVE = APP_DIR / "schedule_elective.db"
DB_EMERGENCY = APP_DIR / "schedule_emergency.db"

DEFAULT_BLOCK_START = "08:30"  # ใช้กับ Emergency ตามที่คุย
DEFAULT_BLOCK_END = "16:30"

# ----------------------------- Utils ------------------------------
def hhmm_to_minutes(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def minutes_to_hhmm(minutes: Union[float, int]) -> str:
    m = int(round(float(minutes)))
    h = m // 60
    mm = m % 60
    return f"{h}h {mm}m"


def sec_to_hhmm(sec: float) -> str:
    s = int(round(sec))
    h, m = s // 3600, (s % 3600) // 60
    return f"{h:02d}:{m:02d}"


def safe_read_sqlite(db_path: Path, sql: str, parse_dates: Tuple[str, ...] = ()) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    con = sqlite3.connect(str(db_path))
    try:
        df = pd.read_sql_query(sql, con)
        for col in parse_dates:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        return df
    finally:
        con.close()


# ----------------------------- ETL -------------------------------
@dataclass
class DataBundle:
    postop: pd.DataFrame
    schedule: pd.DataFrame
    events: pd.DataFrame
    source_label: str


def load_bundle(kind: str) -> DataBundle:
    if kind not in {"elective", "emergency", "all"}:
        raise ValueError("kind must be elective/emergency/all")

    bundles = []
    targets = []
    if kind in {"elective", "all"}:
        targets.append(("elective", DB_ELECTIVE))
    if kind in {"emergency", "all"}:
        targets.append(("emergency", DB_EMERGENCY))

    for label, db in targets:
        postop = safe_read_sqlite(
            db,
            """
            SELECT case_uid, hn, name, dept, doctor, or_room,
                   case_size, urgency, status,
                   time_start_dt, time_end_dt,
                   ops_json, diags_json
            FROM postop_records
            """,
            parse_dates=("time_start_dt", "time_end_dt"),
        )
        schedule = safe_read_sqlite(
            db,
            """
            SELECT
              timestamp, urgency, period, or_room, date, time,
              hn, name, dept, doctor, diagnosis, operation, ward, queue,
              time_start, time_end, case_size
            FROM schedule
            """,
            parse_dates=("date",),
        )
        events = safe_read_sqlite(
            db,
            "SELECT case_uid, event, at, details FROM surgery_events",
            parse_dates=("at",),
        )
        postop["source"] = label
        schedule["source"] = label
        events["source"] = label
        bundles.append(DataBundle(postop=postop, schedule=schedule, events=events, source_label=label))

    if len(bundles) == 1:
        return bundles[0]

    postop = pd.concat([b.postop for b in bundles], ignore_index=True)
    schedule = pd.concat([b.schedule for b in bundles], ignore_index=True)
    events = pd.concat([b.events for b in bundles], ignore_index=True)
    return DataBundle(postop=postop, schedule=schedule, events=events, source_label="all")


# ------------------------ Analytics Core -------------------------
def clip_overlap_minutes(starts: pd.Series, ends: pd.Series, block_start_hhmm: str, block_end_hhmm: str) -> pd.Series:
    bs = pd.to_datetime(starts.dt.date.astype(str) + " " + block_start_hhmm + ":00")
    be = pd.to_datetime(starts.dt.date.astype(str) + " " + block_end_hhmm + ":00")
    os = pd.Series(np.maximum(starts.values.astype("datetime64[ns]"), bs.values.astype("datetime64[ns]")))
    oe = pd.Series(np.minimum(ends.values.astype("datetime64[ns]"), be.values.astype("datetime64[ns]")))
    mins = (oe - os).dt.total_seconds() / 60.0
    return mins.clip(lower=0)


def enrich_cases(df_postop: pd.DataFrame, df_sched: pd.DataFrame) -> pd.DataFrame:
    df = df_postop.copy()
    df = df.dropna(subset=["time_start_dt", "time_end_dt"])
    if df.empty:
        return df
    df["date"] = df["time_start_dt"].dt.date
    df["dow"] = df["time_start_dt"].dt.dayofweek
    df["hour"] = df["time_start_dt"].dt.hour

    if not df_sched.empty and {"date", "or_room", "doctor", "hn"}.issubset(df_sched.columns):
        m = df.merge(
            df_sched[["date", "or_room", "doctor", "hn", "operation", "diagnosis"]],
            on=["date", "or_room", "doctor", "hn"],
            how="left",
            suffixes=("", "_sch"),
        )
        df["operation"] = m["operation"]
        df["diagnosis"] = m["diagnosis"]
    else:
        def parse_ops(x):
            try:
                obj = (json.loads(x) if isinstance(x, str) and (x.startswith("[") or x.startswith("{")) else x)
                if isinstance(obj, list) and obj:
                    first = obj[0]
                    if isinstance(first, str):
                        return first
                    return json.dumps(first, ensure_ascii=False)
                if isinstance(obj, dict):
                    return obj.get("operation") or obj.get("op") or json.dumps(obj, ensure_ascii=False)
                return str(obj) if obj else None
            except Exception:
                return None
        df["operation"] = df_postop.get("ops_json", pd.Series([None] * len(df_postop))).map(parse_ops)
        df["diagnosis"] = df_postop.get("diags_json", pd.Series([None] * len(df_postop)))
    return df


def compute_kpi(df: pd.DataFrame, block_start: str, block_end: str) -> dict:
    if df.empty:
        return dict(cases=0, case_min=0, avail_min=0, utilization_pct=0.0, avg_case_min=0.0)
    df = df.copy()
    df["inblock_min"] = clip_overlap_minutes(df["time_start_dt"], df["time_end_dt"], block_start, block_end)

    case_min = df["inblock_min"].sum()
    block_minutes = hhmm_to_minutes(block_end) - hhmm_to_minutes(block_start)

    room_days = (
        df.dropna(subset=["or_room"])
        .groupby(["date", "or_room"])
        .size()
        .reset_index() [["date", "or_room"]]
    )
    avail_min = len(room_days) * block_minutes
    cases = len(df)
    util = (case_min / avail_min * 100.0) if avail_min > 0 else 0.0
    avg_case = (case_min / cases) if cases > 0 else 0.0

    return dict(
        cases=int(cases),
        case_min=round(case_min, 1),
        avail_min=int(avail_min),
        utilization_pct=round(util, 1),
        avg_case_min=round(avg_case, 1),
    )


def trend(df: pd.DataFrame, block_start: str, block_end: str, granularity: str = "day") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["bucket", "cases", "case_min", "util_pct"])
    df = df.copy()
    df["inblock_min"] = clip_overlap_minutes(df["time_start_dt"], df["time_end_dt"], block_start, block_end)
    block_minutes = hhmm_to_minutes(block_end) - hhmm_to_minutes(block_start)

    if granularity == "month":
        df["bucket"] = pd.to_datetime(df["time_start_dt"].dt.to_period("M").dt.start_time)
    elif granularity == "year":
        df["bucket"] = pd.to_datetime(df["time_start_dt"].dt.to_period("Y").dt.start_time)
    else:
        df["bucket"] = pd.to_datetime(df["time_start_dt"].dt.date)

    g = df.groupby("bucket").agg(
        cases=("case_uid", "count"),
        case_min=("inblock_min", "sum"),
    ).reset_index()

    room_day = df.groupby(["bucket", "date"])["or_room"].nunique().rename("rooms").reset_index()
    room_day2 = room_day.groupby("bucket")["rooms"].sum().rename("room_days").reset_index()
    out = g.merge(room_day2, on="bucket", how="left")
    out["avail_min"] = out["room_days"].fillna(0) * block_minutes
    out["util_pct"] = (
        (out["case_min"] / out["avail_min"] * 100.0)
        .replace([np.inf, -np.inf], 0)
        .fillna(0)
        .round(1)
    )
    return out[["bucket", "cases", "case_min", "util_pct"]]


def room_util(df: pd.DataFrame, block_start: str, block_end: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["or_room", "cases", "avg_case_min", "util_pct", "idle_min"])
    df = df.copy()
    df["inblock_min"] = clip_overlap_minutes(df["time_start_dt"], df["time_end_dt"], block_start, block_end)
    block_minutes = hhmm_to_minutes(block_end) - hhmm_to_minutes(block_start)
    g = df.groupby("or_room").agg(
        cases=("case_uid", "count"),
        case_min=("inblock_min", "sum"),
        open_days=("date", "nunique"),
    ).reset_index()
    g["avail_min"] = g["open_days"] * block_minutes
    g["avg_case_min"] = (g["case_min"] / g["cases"]).replace([np.inf, -np.inf], 0).fillna(0).round(1)
    g["util_pct"] = (
        (g["case_min"] / g["avail_min"] * 100.0)
        .replace([np.inf, -np.inf], 0)
        .fillna(0)
        .round(1)
    )
    g["idle_min"] = (g["avail_min"] - g["case_min"]).clip(lower=0)
    return g.sort_values("util_pct", ascending=False)


def surgeon_first_cut(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["doctor", "avg_first_cut", "workdays"])
    t = df[["doctor", "date", "time_start_dt"]].dropna()
    first = t.groupby(["doctor", "date"])["time_start_dt"].min().reset_index()
    first["sec"] = first["time_start_dt"].dt.hour * 3600 + first["time_start_dt"].dt.minute * 60 + first["time_start_dt"].dt.second
    agg = first.groupby("doctor").agg(avg_first_sec=("sec", "mean"), workdays=("date", "nunique")).reset_index()
    agg = agg[agg["workdays"] >= 3]
    agg["avg_first_cut"] = agg["avg_first_sec"].map(sec_to_hhmm)
    return agg.sort_values("avg_first_sec")[ ["doctor", "avg_first_cut", "workdays"] ]


def top_operations(df: pd.DataFrame, limit: int = 15) -> pd.DataFrame:
    if "operation" not in df.columns or df["operation"].isna().all():
        return pd.DataFrame(columns=["operation", "cases", "avg_min", "total_min"])
    df = df.copy()
    df["duration_min"] = (df["time_end_dt"] - df["time_start_dt"]).dt.total_seconds() / 60.0
    g = df.groupby("operation").agg(
        cases=("case_uid", "count"),
        avg_min=("duration_min", "mean"),
        total_min=("duration_min", "sum"),
    ).reset_index()
    g["avg_min"] = g["avg_min"].round(1)
    return g.sort_values(["cases", "total_min"], ascending=[False, False]).head(limit)


def postponement_reasons(df_events: pd.DataFrame) -> pd.DataFrame:
    if df_events.empty:
        return pd.DataFrame(columns=["reason", "cases"])
    ev = df_events.copy()
    ev["event_norm"] = ev["event"].str.lower().fillna("")
    ev = ev[ev["event_norm"].isin(["postponed", "postpone", "cancelled", "canceled"])]
    if ev.empty:
        return pd.DataFrame(columns=["reason", "cases"])
    ev["reason"] = ev["details"].fillna("Unknown")
    g = ev.groupby("reason").size().rename("cases").reset_index()
    return g.sort_values("cases", ascending=False)


def heatmap_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["dow", "hour", "cases"])
    g = df.groupby(["dow", "hour"]).size().rename("cases").reset_index()
    return g


# ----------------------------- UI -------------------------------
class KpiCard(QtWidgets.QFrame):
    def __init__(self, title: str, value: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setStyleSheet("QFrame { border:1px solid #e5e5e5; border-radius:8px; }")
        lay = QtWidgets.QVBoxLayout(self)
        self.title = QtWidgets.QLabel(title)
        self.title.setStyleSheet("color:#666; font-size:12px;")
        self.value = QtWidgets.QLabel(value)
        self.value.setStyleSheet("font-size:22px; font-weight:700;")
        lay.addWidget(self.title)
        lay.addWidget(self.value)

    def setValue(self, value: str):
        self.value.setText(value)


class MplChart(QtWidgets.QWidget):
    def __init__(self, title: str, height: int = 300, parent=None):
        super().__init__(parent)
        self.fig = Figure(figsize=(8, height / 100), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvas(self.fig)
        self._colorbar = None
        lay = QtWidgets.QVBoxLayout(self)
        lab = QtWidgets.QLabel(title)
        lab.setStyleSheet("font-weight:700; margin:0 0 4px 0;")
        lay.addWidget(lab)
        lay.addWidget(self.canvas)

    def clear(self):
        if self._colorbar:
            try:
                self._colorbar.remove()
            except Exception:
                pass
            self._colorbar = None
        self.ax.clear()
        self.ax.grid(True, linestyle="--", linewidth=0.4, alpha=0.6)
        for extra_ax in list(self.fig.axes[1:]):
            if extra_ax is not self.ax:
                self.fig.delaxes(extra_ax)
        self.canvas.draw_idle()


class DashboardTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        ctrl = QtWidgets.QHBoxLayout()
        self.fromDate = QtWidgets.QDateEdit(QtCore.QDate.currentDate().addDays(-30))
        self.fromDate.setCalendarPopup(True)
        self.toDate = QtWidgets.QDateEdit(QtCore.QDate.currentDate())
        self.toDate.setCalendarPopup(True)

        self.kind = QtWidgets.QComboBox()
        self.kind.addItems(["emergency", "elective", "all"])
        self.blockStart = QtWidgets.QTimeEdit(QtCore.QTime.fromString(DEFAULT_BLOCK_START, "HH:mm"))
        self.blockEnd = QtWidgets.QTimeEdit(QtCore.QTime.fromString(DEFAULT_BLOCK_END, "HH:mm"))
        self.gran = QtWidgets.QComboBox()
        self.gran.addItems(["day", "month", "year"])

        self.btnRefresh = QtWidgets.QPushButton("Refresh")
        self.btnExport = QtWidgets.QPushButton("Export De-Identified CSV")

        for w, lbl in [
            (self.fromDate, "From"),
            (self.toDate, "To"),
            (self.kind, "Source"),
            (self.gran, "Granularity"),
            (self.blockStart, "Block Start"),
            (self.blockEnd, "Block End"),
        ]:
            box = QtWidgets.QVBoxLayout()
            wrap = QtWidgets.QWidget()
            wrap.setLayout(box)
            lab = QtWidgets.QLabel(lbl)
            lab.setStyleSheet("color:#666;")
            box.addWidget(lab)
            box.addWidget(w)
            ctrl.addWidget(wrap)

        ctrl.addStretch(1)
        ctrl.addWidget(self.btnRefresh)
        ctrl.addWidget(self.btnExport)

        kpiGrid = QtWidgets.QGridLayout()
        self.k_cases = KpiCard("Cases", "0")
        self.k_caseh = KpiCard("Case Hours", "0h 0m")
        self.k_avail = KpiCard("Available Hours", "0h 0m")
        self.k_util = KpiCard("Utilization", "0%")
        self.k_avg = KpiCard("Avg Duration/Case", "0 min")
        kpiGrid.addWidget(self.k_cases, 0, 0)
        kpiGrid.addWidget(self.k_caseh, 0, 1)
        kpiGrid.addWidget(self.k_avail, 0, 2)
        kpiGrid.addWidget(self.k_util, 0, 3)
        kpiGrid.addWidget(self.k_avg, 0, 4)

        self.trendChart = MplChart("Volume & Utilization")
        self.roomsChart = MplChart("Room Utilization (Ranking)")
        self.firstCutChart = MplChart("Surgeon — Earliest First Cut (avg)")
        self.topOpsChart = MplChart("Top Operations")
        self.postponeChart = MplChart("Postponement Reasons")
        self.heatmapChart = MplChart("Heatmap (Cases) — Hour × Weekday", height=330)

        main = QtWidgets.QVBoxLayout(self)
        main.addLayout(ctrl)
        main.addSpacing(6)
        main.addLayout(kpiGrid)
        main.addSpacing(8)
        main.addWidget(self.trendChart)
        main.addWidget(self.roomsChart)
        main.addWidget(self.firstCutChart)
        main.addWidget(self.topOpsChart)
        main.addWidget(self.postponeChart)
        main.addWidget(self.heatmapChart)

        self.btnRefresh.clicked.connect(self.refresh)
        self.btnExport.clicked.connect(self.export_csv)
        QtCore.QTimer.singleShot(0, self.refresh)

    def _bundle(self) -> DataBundle:
        kind = self.kind.currentText()
        return load_bundle(kind)

    def _block(self) -> Tuple[str, str]:
        return (
            self.blockStart.time().toString("HH:mm"),
            self.blockEnd.time().toString("HH:mm"),
        )

    def refresh(self):
        bundle = self._bundle()
        df = enrich_cases(bundle.postop, bundle.schedule)
        if df.empty:
            self._clear_charts()
            self._set_kpis(dict(cases=0, case_min=0, avail_min=0, utilization_pct=0, avg_case_min=0))
            return

        d0 = self.fromDate.date().toPython()
        d1 = self.toDate.date().toPython()
        df = df[(df["date"] >= d0) & (df["date"] <= d1)]

        block_s, block_e = self._block()

        kpi = compute_kpi(df, block_s, block_e)
        self._set_kpis(kpi)

        gran = self.gran.currentText()
        tr = trend(df, block_s, block_e, granularity=gran)
        self._plot_trend(tr)

        ru = room_util(df, block_s, block_e)
        self._plot_rooms(ru)

        sf = surgeon_first_cut(df)
        self._plot_firstcut(sf)

        to = top_operations(df)
        self._plot_topops(to)

        pp = postponement_reasons(bundle.events)
        self._plot_postpone(pp)

        hm = heatmap_df(df)
        self._plot_heatmap(hm)

    def export_csv(self):
        bundle = self._bundle()
        df = enrich_cases(bundle.postop, bundle.schedule)
        if df.empty:
            QtWidgets.QMessageBox.information(self, "Export", "No data to export.")
            return
        cols = ["date", "or_room", "doctor", "dept", "operation", "case_size", "time_start_dt", "time_end_dt", "source"]
        for col in cols:
            if col not in df.columns:
                df[col] = None
        out = df[cols].sort_values(["date", "or_room", "time_start_dt"])
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save CSV", "or_dashboard_export.csv", "CSV (*.csv)")
        if path:
            out.to_csv(path, index=False, encoding="utf-8-sig")
            QtWidgets.QMessageBox.information(self, "Export", f"Saved: {path}")

    def _set_kpis(self, k: dict):
        self.k_cases.setValue(f"{k['cases']}")
        self.k_caseh.setValue(minutes_to_hhmm(k["case_min"]))
        self.k_avail.setValue(minutes_to_hhmm(k["avail_min"]))
        self.k_util.setValue(f"{k['utilization_pct']}%")
        self.k_avg.setValue(f"{k['avg_case_min']} min")

    def _plot_trend(self, tr: pd.DataFrame):
        chart = self.trendChart
        chart.clear()
        ax = chart.ax
        if tr.empty:
            chart.canvas.draw(); return
        x = tr["bucket"]
        ax.bar(x, tr["cases"], color="#9eb7ff", label="Cases")
        ax2 = ax.twinx()
        ax2.plot(x, tr["util_pct"], color="#2ca02c", marker="o", label="Util (%)")
        ax.set_ylabel("Cases"); ax2.set_ylabel("Util (%)"); ax2.set_ylim(0, 100)
        ax.set_title("Volume & Utilization")
        ax.xaxis.set_major_locator(mticker.MaxNLocator(nbins=8))
        chart.fig.legend(loc="upper right")
        chart.canvas.draw()

    def _plot_rooms(self, ru: pd.DataFrame):
        chart = self.roomsChart; chart.clear(); ax = chart.ax
        if ru.empty: chart.canvas.draw(); return
        ax.bar(ru["or_room"].astype(str), ru["util_pct"], color="#7cd992", label="Util (%)")
        ax.set_ylabel("Util (%)"); ax.set_ylim(0, 100); ax.set_title("Room Utilization (Ranking)")
        chart.canvas.draw()

    def _plot_firstcut(self, sf: pd.DataFrame):
        chart = self.firstCutChart; chart.clear(); ax = chart.ax
        if sf.empty: chart.canvas.draw(); return
        ax.bar(sf["doctor"].astype(str), sf["workdays"], color="#f6c85f")
        for i, v in enumerate(sf["avg_first_cut"]):
            ax.text(i, sf["workdays"].iloc[i] + 0.1, v, ha="center", va="bottom", fontsize=9)
        ax.set_ylabel("Workdays")
        ax.set_title("Surgeon — Earliest First Cut (avg time shown above bars)")
        ax.tick_params(axis="x", rotation=25)
        chart.canvas.draw()

    def _plot_topops(self, to: pd.DataFrame):
        chart = self.topOpsChart; chart.clear(); ax = chart.ax
        if to.empty: chart.canvas.draw(); return
        ax.bar(to["operation"].astype(str), to["cases"], color="#8884d8", label="Cases")
        ax.set_ylabel("Cases"); ax.set_title("Top Operations")
        ax.tick_params(axis="x", rotation=30)
        chart.canvas.draw()

    def _plot_postpone(self, pp: pd.DataFrame):
        chart = self.postponeChart; chart.clear(); ax = chart.ax
        if pp.empty: chart.canvas.draw(); return
        vals = pp["cases"].values; labels = pp["reason"].astype(str).values
        ax.pie(vals, labels=labels, autopct="%1.0f%%", startangle=90)
        ax.axis("equal"); ax.set_title("Postponement Reasons")
        chart.canvas.draw()

    def _plot_heatmap(self, hm: pd.DataFrame):
        chart = self.heatmapChart; chart.clear(); ax = chart.ax
        if hm.empty: chart.canvas.draw(); return
        pivot = hm.pivot_table(index="dow", columns="hour", values="cases", aggfunc="sum", fill_value=0)
        im = ax.imshow(pivot.values, aspect="auto", cmap="Blues")
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        ax.set_xticks(range(0, 24, 2))
        ax.set_xticklabels([str(h) for h in range(0, 24, 2)])
        ax.set_xlabel("Hour"); ax.set_ylabel("Day"); ax.set_title("Heatmap (Cases)")
        chart._colorbar = chart.fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        chart.canvas.draw()

    def _clear_charts(self):
        for chart in [self.trendChart, self.roomsChart, self.firstCutChart, self.topOpsChart, self.postponeChart, self.heatmapChart]:
            chart.clear()


if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    w = DashboardTab()
    w.resize(1200, 900)
    w.setWindowTitle("OR Dashboard (Preview)")
    w.show()
    app.exec()
