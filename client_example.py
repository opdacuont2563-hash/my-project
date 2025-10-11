import os
import sys
import json
import argparse
from pathlib import Path
import requests
from dotenv import load_dotenv

# ===== โหลด .env (ถ้ามี) =====
env_path = Path.cwd() / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

DEFAULT_HOST = os.getenv("SURGIBOT_CLIENT_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("SURGIBOT_CLIENT_PORT", "8088"))
DEFAULT_TOKEN = os.getenv("SURGIBOT_SECRET", "")

API_HEALTH = "/api/health"
API_UPDATE = "/api/update"

STATUS_CHOICES = ["รอผ่าตัด", "กำลังผ่าตัด", "กำลังพักฟื้น", "กำลังส่งกลับตึก", "เลื่อนการผ่าตัด"]
OR_CHOICES = ["OR1", "OR2", "OR3", "OR4", "OR5"]
QUEUE_CHOICES = ["0-1", "0-2", "0-3", "0-4", "0-5"]

class SurgiBotClient:
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, token=DEFAULT_TOKEN, timeout=6):
        self.base = f"http://{host}:{port}"
        self.token = token
        self.timeout = timeout

    def health(self):
        url = self.base + API_HEALTH
        r = requests.get(url, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def send_update(self, action, or_room=None, queue=None, status=None, patient_id=None):
        """
        action: add|edit|delete
        - ถ้าส่ง patient_id แล้ว ไม่จำเป็นต้องส่ง or_room+queue
        - ถ้าไม่ส่ง patient_id จะประกอบจาก or_room-queue (เช่น OR1-0-2)
        """
        url = self.base + API_UPDATE
        payload = {
            "token": self.token,
            "action": action,
        }
        if patient_id:
            payload["patient_id"] = str(patient_id)
        else:
            if or_room: payload["or"] = str(or_room)
            if queue: payload["queue"] = str(queue)

        if status:
            payload["status"] = str(status)

        r = requests.post(url, json=payload, timeout=self.timeout)
        # คืนค่า JSON หรือ error text ชัดๆ
        try:
            data = r.json()
        except Exception:
            data = {"ok": False, "error": f"HTTP {r.status_code}", "text": r.text}
        if r.status_code >= 400:
            raise requests.HTTPError(json.dumps(data, ensure_ascii=False))
        return data

# ===== CLI =====
def build_parser():
    p = argparse.ArgumentParser(
        description="SurgiBot Client — ส่งคำสั่ง add/edit/delete ไปยัง Server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    p.add_argument("--host", default=DEFAULT_HOST, help="Server host")
    p.add_argument("--port", default=DEFAULT_PORT, type=int, help="Server port (int)")
    p.add_argument("--token", default=DEFAULT_TOKEN, help="SURGIBOT_SECRET token")

    sub = p.add_subparsers(dest="cmd", required=False)

    # health
    sp = sub.add_parser("health", help="ตรวจสุขภาพ API server")

    # add
    sp = sub.add_parser("add", help="เพิ่มแถวใหม่")
    sp.add_argument("--or", dest="or_room", choices=OR_CHOICES, required=True, help="OR room")
    sp.add_argument("--queue", choices=QUEUE_CHOICES, required=True, help="คิว เช่น 0-2")
    sp.add_argument("--status", choices=STATUS_CHOICES, required=True, help="สถานะเริ่มต้น")

    # edit
    sp = sub.add_parser("edit", help="แก้สถานะ")
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--patient-id", dest="patient_id", help="เช่น OR1-0-2")
    g.add_argument("--or", dest="or_room", choices=OR_CHOICES, help="OR room (ใช้คู่กับ --queue)")
    sp.add_argument("--queue", choices=QUEUE_CHOICES, help="คิว (ต้องใช้เมื่อระบุ --or)")
    sp.add_argument("--status", choices=STATUS_CHOICES, required=True, help="สถานะใหม่")

    # delete
    sp = sub.add_parser("delete", help="ลบผู้ป่วย")
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--patient-id", dest="patient_id", help="เช่น OR1-0-2")
    g.add_argument("--or", dest="or_room", choices=OR_CHOICES, help="OR room (ใช้คู่กับ --queue)")
    sp.add_argument("--queue", choices=QUEUE_CHOICES, help="คิว (ต้องใช้เมื่อระบุ --or)")

    # GUI
    p.add_argument("--gui", action="store_true", help="เปิด GUI Client (Tkinter)")

    return p

# ===== GUI (ไม่ยุ่งกับ UI/UX ฝั่ง Server) =====
def run_gui(host, port, token):
    import tkinter as tk
    from tkinter import ttk, messagebox

    client = SurgiBotClient(host, port, token)

    root = tk.Tk()
    root.title("SurgiBot Client")
    root.geometry("560x420")
    root.resizable(False, False)

    main = tk.Frame(root, padx=12, pady=12)
    main.pack(fill="both", expand=True)

    # Server row
    frm_srv = tk.LabelFrame(main, text="Server", padx=8, pady=8)
    frm_srv.pack(fill="x")
    tk.Label(frm_srv, text="Host:").grid(row=0, column=0, sticky="e", padx=4, pady=4)
    ent_host = tk.Entry(frm_srv)
    ent_host.insert(0, host)
    ent_host.grid(row=0, column=1, sticky="we", padx=4, pady=4)

    tk.Label(frm_srv, text="Port:").grid(row=0, column=2, sticky="e", padx=4, pady=4)
    ent_port = tk.Entry(frm_srv, width=6)
    ent_port.insert(0, str(port))
    ent_port.grid(row=0, column=3, sticky="w", padx=4, pady=4)

    tk.Label(frm_srv, text="Token:").grid(row=1, column=0, sticky="e", padx=4, pady=4)
    ent_token = tk.Entry(frm_srv, show="*")
    ent_token.insert(0, token or "")
    ent_token.grid(row=1, column=1, columnspan=3, sticky="we", padx=4, pady=4)

    for i in (1,):
        frm_srv.grid_columnconfigure(i, weight=1)

    # Action row
    frm_act = tk.LabelFrame(main, text="Action", padx=8, pady=8)
    frm_act.pack(fill="x", pady=(8, 0))

    action_var = tk.StringVar(value="add")
    rb_add = tk.Radiobutton(frm_act, text="add", variable=action_var, value="add")
    rb_edit = tk.Radiobutton(frm_act, text="edit", variable=action_var, value="edit")
    rb_del = tk.Radiobutton(frm_act, text="delete", variable=action_var, value="delete")
    rb_add.grid(row=0, column=0, padx=6, pady=4)
    rb_edit.grid(row=0, column=1, padx=6, pady=4)
    rb_del.grid(row=0, column=2, padx=6, pady=4)

    # Fields
    frm_fields = tk.LabelFrame(main, text="Fields", padx=8, pady=8)
    frm_fields.pack(fill="x", pady=(8, 0))

    tk.Label(frm_fields, text="OR:").grid(row=0, column=0, sticky="e", padx=4, pady=4)
    cb_or = ttk.Combobox(frm_fields, values=OR_CHOICES, state="readonly")
    cb_or.grid(row=0, column=1, sticky="we", padx=4, pady=4)
    cb_or.set(OR_CHOICES[0])

    tk.Label(frm_fields, text="Queue:").grid(row=0, column=2, sticky="e", padx=4, pady=4)
    cb_q = ttk.Combobox(frm_fields, values=QUEUE_CHOICES, state="readonly", width=8)
    cb_q.grid(row=0, column=3, sticky="w", padx=4, pady=4)
    cb_q.set(QUEUE_CHOICES[0])

    tk.Label(frm_fields, text="Status:").grid(row=1, column=0, sticky="e", padx=4, pady=4)
    cb_status = ttk.Combobox(frm_fields, values=STATUS_CHOICES, state="readonly")
    cb_status.grid(row=1, column=1, sticky="we", padx=4, pady=4)
    cb_status.set(STATUS_CHOICES[0])

    tk.Label(frm_fields, text="Patient ID (ถ้าระบุ จะใช้แทน OR/Queue):").grid(row=2, column=0, columnspan=2, sticky="w", padx=4, pady=4)
    ent_pid = tk.Entry(frm_fields)
    ent_pid.grid(row=2, column=2, columnspan=2, sticky="we", padx=4, pady=4)

    frm_fields.grid_columnconfigure(1, weight=1)
    frm_fields.grid_columnconfigure(2, weight=1)

    # Log
    frm_log = tk.LabelFrame(main, text="Result", padx=8, pady=8)
    frm_log.pack(fill="both", expand=True, pady=(8, 0))
    txt = tk.Text(frm_log, height=8)
    txt.pack(fill="both", expand=True)

    # Buttons
    frm_btn = tk.Frame(main)
    frm_btn.pack(fill="x", pady=(8,0))
    def do_health():
        try:
            c = SurgiBotClient(ent_host.get(), int(ent_port.get()), ent_token.get())
            res = c.health()
            txt.insert("end", json.dumps(res, ensure_ascii=False) + "\n")
            txt.see("end")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def do_send():
        try:
            c = SurgiBotClient(ent_host.get(), int(ent_port.get()), ent_token.get())
            action = action_var.get()
            pid = ent_pid.get().strip() or None
            or_room = cb_or.get() if not pid else None
            q = cb_q.get() if not pid else None
            status = cb_status.get() if action in ("add", "edit") else None

            res = c.send_update(action=action, or_room=or_room, queue=q, status=status, patient_id=pid)
            txt.insert("end", json.dumps(res, ensure_ascii=False) + "\n")
            txt.see("end")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    tk.Button(frm_btn, text="Health Check", command=do_health).pack(side="left", padx=4)
    tk.Button(frm_btn, text="Send", command=do_send).pack(side="right", padx=4)

    root.mainloop()

def main():
    parser = build_parser()
    args = parser.parse_args()

    # GUI first?
    if args.gui:
        run_gui(args.host, args.port, args.token)
        return

    # no subcommand -> show help
    if not args.cmd:
        parser.print_help()
        sys.exit(0)

    client = SurgiBotClient(args.host, args.port, args.token)

    try:
        if args.cmd == "health":
            res = client.health()
            print(json.dumps(res, ensure_ascii=False, indent=2))
        elif args.cmd == "add":
            res = client.send_update(
                action="add",
                or_room=args.or_room,
                queue=args.queue,
                status=args.status
            )
            print(json.dumps(res, ensure_ascii=False, indent=2))
        elif args.cmd == "edit":
            if args.patient_id:
                pid = args.patient_id
                res = client.send_update(action="edit", patient_id=pid, status=args.status)
            else:
                if not args.or_room or not args.queue:
                    raise SystemExit("--or และ --queue จำเป็นเมื่อไม่ได้ส่ง --patient-id")
                res = client.send_update(action="edit", or_room=args.or_room, queue=args.queue, status=args.status)
            print(json.dumps(res, ensure_ascii=False, indent=2))
        elif args.cmd == "delete":
            if args.patient_id:
                res = client.send_update(action="delete", patient_id=args.patient_id)
            else:
                if not args.or_room or not args.queue:
                    raise SystemExit("--or และ --queue จำเป็นเมื่อไม่ได้ส่ง --patient-id")
                res = client.send_update(action="delete", or_room=args.or_room, queue=args.queue)
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            parser.print_help()
    except requests.HTTPError as he:
        print(f"[HTTP ERROR] {he}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
