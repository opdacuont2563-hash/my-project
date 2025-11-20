"""
Main display window using Tkinter for showing surgery status on large screen.
Refactored from original surgibot_server.py with modern architecture.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import asyncio
import threading
import json

from ...config import get_settings, TAG_STYLES_LIGHT, STATUS_COLORS
from ...core.models import SurgeryStatus
from ...shared.logging_config import get_display_logger
from ...shared.utils import format_timedelta, mask_hn
from .websocket_client import DisplayWebSocketClient

logger = get_display_logger()


class DisplayWindow(tk.Frame):
    """
    Main display window for showing surgery status.
    Connects to API server via WebSocket for real-time updates.
    """

    def __init__(self, root: tk.Tk):
        super().__init__(root)
        self.root = root
        self.settings = get_settings()

        # Configure window
        self.root.title("SurgiBot - ติดตามสถานะการผ่าตัด")
        self._setup_fullscreen()

        # Data
        self.patient_data: Dict[str, Dict[str, Any]] = {}
        self.id_counter = 1

        # WebSocket client
        self.ws_client: Optional[DisplayWebSocketClient] = None
        self._ws_thread: Optional[threading.Thread] = None

        # UI Components
        self._setup_ui()
        self._apply_styles()

        # Start update loop
        self.root.after(1000, self._update_timers)

        logger.info("Display window initialized")

    def _setup_fullscreen(self):
        """Setup fullscreen mode based on OS."""
        try:
            import os
            if os.name == "nt":  # Windows
                self.root.state("zoomed")
            else:  # Linux/Mac
                self.root.attributes("-fullscreen", True)
        except Exception as e:
            logger.warning(f"Could not set fullscreen: {e}")
            self.root.geometry("1600x900")

        self.root.resizable(True, True)

        # ESC to exit fullscreen
        self.root.bind("<Escape>", self._exit_fullscreen)

    def _setup_ui(self):
        """Setup UI components."""
        # Configure background
        self.root.configure(bg="#f0f4f8")
        self.configure(bg="#f0f4f8")

        # Header
        self._create_header()

        # Control panel
        self._create_control_panel()

        # Table
        self._create_table()

        # Status bar
        self._create_status_bar()

    def _create_header(self):
        """Create header with title."""
        header_frame = tk.Frame(self.root, bg="#1f4e79", pady=14, padx=20)
        header_frame.pack(pady=5, fill="x")

        title_label = tk.Label(
            header_frame,
            text="ติดตามสถานะการผ่าตัดโรงพยาบาลหนองบัวลำภู",
            font=("Prompt", 34, "bold"),
            fg="white",
            bg="#1f4e79"
        )
        title_label.pack()

        # Subtitle with connection status
        self.connection_label = tk.Label(
            header_frame,
            text="● เชื่อมต่อกับเซิร์ฟเวอร์...",
            font=("Prompt", 12),
            fg="#fbbf24",
            bg="#1f4e79"
        )
        self.connection_label.pack()

    def _create_control_panel(self):
        """Create control panel (simplified - no add/edit buttons)."""
        control_frame = tk.Frame(self.root, bg="#f0f4f8", pady=5)
        control_frame.pack(pady=5, padx=5, fill="x")

        # Info label
        info_label = tk.Label(
            control_frame,
            text="📊 หน้าจอแสดงผลแบบ Real-time • เชื่อมต่อผ่าน WebSocket",
            font=("Prompt", 12),
            bg="#f0f4f8",
            fg="#64748b"
        )
        info_label.pack(side="left", padx=10)

        # Refresh time
        self.refresh_label = tk.Label(
            control_frame,
            text="อัปเดตล่าสุด: --:--:--",
            font=("Prompt", 12),
            bg="#f0f4f8",
            fg="#64748b"
        )
        self.refresh_label.pack(side="right", padx=10)

    def _create_table(self):
        """Create table for displaying cases."""
        table_frame = tk.Frame(self.root, bg="#f0f4f8", bd=2, relief="groove")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Style
        style = ttk.Style()
        style.configure(
            "Display.Treeview",
            font=("Prompt", 28),
            rowheight=56,
            background="#ffffff",
            fieldbackground="#ffffff"
        )
        style.configure(
            "Display.Treeview.Heading",
            font=("Prompt", 26),
            padding=6
        )

        # Treeview
        self.tree = ttk.Treeview(
            table_frame,
            columns=("ID", "PatientID", "Status", "Elapsed", "ETA"),
            show="headings",
            style="Display.Treeview"
        )

        # Headers
        self.tree.heading("ID", text="ID")
        self.tree.heading("PatientID", text="รหัสผู้ป่วย (Patient ID)")
        self.tree.heading("Status", text="สถานะ (Status)")
        self.tree.heading("Elapsed", text="เวลาเดินไป (Elapsed)")
        self.tree.heading("ETA", text="เวลาคาดเสร็จ (ETA)")

        # Columns
        self.tree.column("ID", width=160, anchor="center", minwidth=140)
        self.tree.column("PatientID", width=420, anchor="center", minwidth=360)
        self.tree.column("Status", width=420, anchor="center", minwidth=360)
        self.tree.column("Elapsed", width=260, anchor="center", minwidth=220)
        self.tree.column("ETA", width=340, anchor="center", minwidth=300)

        # Scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(fill=tk.BOTH, expand=True)

    def _create_status_bar(self):
        """Create status bar at bottom."""
        status_frame = tk.Frame(self.root, bg="#1f4e79", pady=8)
        status_frame.pack(side="bottom", fill="x")

        self.status_label = tk.Label(
            status_frame,
            text="พร้อมแสดงผล",
            font=("Prompt", 12),
            fg="white",
            bg="#1f4e79"
        )
        self.status_label.pack(side="left", padx=20)

        # Clock
        self.clock_label = tk.Label(
            status_frame,
            text="",
            font=("Prompt", 12, "bold"),
            fg="white",
            bg="#1f4e79"
        )
        self.clock_label.pack(side="right", padx=20)
        self._update_clock()

    def _apply_styles(self):
        """Apply tag styles for different statuses."""
        for tag, style in TAG_STYLES_LIGHT.items():
            self.tree.tag_configure(
                tag,
                background=style["background"],
                foreground=style["foreground"]
            )

    def _update_clock(self):
        """Update clock display."""
        now = datetime.now()
        self.clock_label.config(text=now.strftime("%d/%m/%Y %H:%M:%S"))
        self.root.after(1000, self._update_clock)

    def _update_timers(self):
        """Update elapsed time and ETA for all cases."""
        now = datetime.now()

        for item_id in self.tree.get_children():
            try:
                values = self.tree.item(item_id, "values")
                if len(values) < 2:
                    continue

                patient_id = values[1]
                if patient_id not in self.patient_data:
                    continue

                data = self.patient_data[patient_id]
                status = data.get("status", "")
                timestamp = data.get("timestamp")
                eta_minutes = data.get("eta_minutes")

                # Calculate elapsed and ETA
                elapsed_text = ""
                eta_text = ""

                if timestamp:
                    if status == "กำลังผ่าตัด":
                        elapsed = now - timestamp
                        elapsed_text = format_timedelta(elapsed)

                        if isinstance(eta_minutes, int):
                            eta_dt = timestamp + timedelta(minutes=eta_minutes)
                            remain = eta_dt - now
                            hhmm = eta_dt.strftime("%H:%M") + " น."

                            if remain.total_seconds() >= 0:
                                eta_text = f"{hhmm} • เหลือ {format_timedelta(remain)}"
                            else:
                                eta_text = f"{hhmm} • เกินเวลา {format_timedelta(remain).replace('-', '')}"

                    elif status == "กำลังพักฟื้น":
                        # Countdown to recovery complete (1 hour)
                        end_dt = timestamp + timedelta(hours=1)
                        remain = end_dt - now

                        if remain.total_seconds() < 0:
                            remain = timedelta(seconds=0)

                        elapsed_text = format_timedelta(remain)
                        eta_text = now.strftime("%H:%M") + " น."

                    else:
                        elapsed = now - timestamp
                        elapsed_text = format_timedelta(elapsed)

                # Update display
                masked_id = mask_hn(data.get("hn")) or data.get("id", "")
                self.tree.item(
                    item_id,
                    values=(masked_id, patient_id, status, elapsed_text, eta_text)
                )

                # Apply tag
                self._apply_status_tag(item_id, status)

            except Exception as e:
                logger.error(f"Error updating timer for {item_id}: {e}")

        self.root.after(1000, self._update_timers)

    def _apply_status_tag(self, item_id: str, status: str):
        """Apply color tag based on status."""
        tag_map = {
            "รอผ่าตัด": "waiting",
            "กำลังผ่าตัด": "surgery",
            "กำลังพักฟื้น": "recovery",
            "พักฟื้นครบแล้ว": "recovery_complete",
            "กำลังส่งกลับตึก": "discharge",
            "เลื่อนการผ่าตัด": "postponed",
        }

        tag = tag_map.get(status)
        if tag:
            self.tree.item(item_id, tags=(tag,))

    def update_from_snapshot(self, snapshot: Dict[str, Any]):
        """
        Update display from API snapshot.

        Args:
            snapshot: Snapshot data from API
        """
        try:
            items = snapshot.get("items", [])

            # Clear current display
            for item in self.tree.get_children():
                self.tree.delete(item)

            # Update patient data
            self.patient_data.clear()

            # Add items
            for item in items:
                patient_id = item.get("patient_id")
                if not patient_id:
                    continue

                # Parse timestamp
                timestamp_str = item.get("timestamp")
                timestamp = None
                if timestamp_str:
                    try:
                        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", ""))
                    except Exception:
                        pass

                # Store data
                self.patient_data[patient_id] = {
                    "id": item.get("id"),
                    "hn": item.get("hn_full"),
                    "status": item.get("status", ""),
                    "timestamp": timestamp,
                    "eta_minutes": item.get("eta_minutes"),
                }

                # Add to tree
                masked_id = item.get("id", "")
                status = item.get("status", "")

                tree_id = self.tree.insert(
                    "",
                    "end",
                    values=(masked_id, patient_id, status, "", "")
                )
                self._apply_status_tag(tree_id, status)

            # Update refresh time
            self.refresh_label.config(
                text=f"อัปเดตล่าสุด: {datetime.now().strftime('%H:%M:%S')}"
            )

            logger.debug(f"Updated display with {len(items)} items")

        except Exception as e:
            logger.error(f"Error updating from snapshot: {e}", exc_info=True)

    def handle_status_update(self, update: Dict[str, Any]):
        """
        Handle real-time status update from WebSocket.

        Args:
            update: Update data from WebSocket
        """
        try:
            action = update.get("action")
            patient_id = update.get("patient_id")

            if action == "add" or action == "edit" or action == "status_change":
                # Refresh from API
                self._request_snapshot()

            elif action == "delete":
                # Remove from display
                if patient_id in self.patient_data:
                    del self.patient_data[patient_id]
                    self._remove_row(patient_id)

            logger.debug(f"Handled update: {action} for {patient_id}")

        except Exception as e:
            logger.error(f"Error handling status update: {e}", exc_info=True)

    def _remove_row(self, patient_id: str):
        """Remove row from table by patient_id."""
        for item_id in self.tree.get_children():
            values = self.tree.item(item_id, "values")
            if len(values) >= 2 and str(values[1]) == str(patient_id):
                self.tree.delete(item_id)
                return

    def _request_snapshot(self):
        """Request full snapshot from API."""
        if self.ws_client:
            self.ws_client.request_snapshot()

    def set_connection_status(self, connected: bool):
        """Update connection status indicator."""
        if connected:
            self.connection_label.config(
                text="● เชื่อมต่อสำเร็จ",
                fg="#22c55e"
            )
            self.status_label.config(text="เชื่อมต่อกับเซิร์ฟเวอร์สำเร็จ")
        else:
            self.connection_label.config(
                text="● การเชื่อมต่อขาดหาย",
                fg="#ef4444"
            )
            self.status_label.config(text="กำลังพยายามเชื่อมต่อใหม่...")

    def connect_to_server(self):
        """Connect to API server via WebSocket."""
        try:
            self.ws_client = DisplayWebSocketClient(
                host=self.settings.client_host,
                port=self.settings.client_port,
                on_snapshot=self.update_from_snapshot,
                on_update=self.handle_status_update,
                on_connected=lambda: self.set_connection_status(True),
                on_disconnected=lambda: self.set_connection_status(False),
            )

            # Start WebSocket in separate thread
            self._ws_thread = threading.Thread(
                target=self.ws_client.run,
                daemon=True
            )
            self._ws_thread.start()

            logger.info("WebSocket client started")

        except Exception as e:
            logger.error(f"Failed to connect to server: {e}", exc_info=True)
            messagebox.showerror(
                "Connection Error",
                f"ไม่สามารถเชื่อมต่อกับเซิร์ฟเวอร์: {e}"
            )

    def _exit_fullscreen(self, event=None):
        """Exit fullscreen mode."""
        try:
            import os
            if os.name != "nt":
                self.root.attributes("-fullscreen", False)
        except Exception:
            pass

    def cleanup(self):
        """Cleanup resources."""
        if self.ws_client:
            self.ws_client.stop()
        logger.info("Display window cleaned up")


def run_display():
    """Run the display window application."""
    root = tk.Tk()
    app = DisplayWindow(root)
    app.pack(fill=tk.BOTH, expand=True)

    # Connect to server
    app.connect_to_server()

    # Handle window close
    def on_closing():
        app.cleanup()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)

    # Run
    root.mainloop()


if __name__ == "__main__":
    run_display()
