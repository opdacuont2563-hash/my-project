import tkinter as tk
from tkinter import messagebox, ttk
import requests  # ใช้ requests สำหรับติดต่อกับ Flask API
from datetime import datetime, timedelta
import json


class SurgeryStatusApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ระบบติดตามสถานะการผ่าตัด")
        self.patient_data = {}  # ใช้เก็บข้อมูลผู้ป่วย
        self.id_counter = 1  # ใช้เก็บไอดีของผู้ป่วย
        self.create_widgets()

    def create_widgets(self):
        # กรอบของฟอร์มการกรอกข้อมูล
        input_frame = tk.Frame(self.root, bg="#f0f4f8", bd=2, relief="groove")
        input_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(input_frame, text="รหัสผู้ป่วย:", font=("Prompt", 14), bg="#f0f4f8").grid(row=0, column=0, padx=5)
        self.patient_id_entry = tk.Entry(input_frame, font=("Prompt", 12), bg="#e8f0fe", relief="solid")
        self.patient_id_entry.grid(row=0, column=1, padx=5)

        tk.Label(input_frame, text="สถานะการผ่าตัด:", font=("Prompt", 12), bg="#f0f4f8").grid(row=0, column=2, padx=5)
        self.status_var = tk.StringVar()
        self.status_combobox = ttk.Combobox(input_frame, textvariable=self.status_var,
                                             values=["รอผ่าตัด", "กำลังผ่าตัด", "กำลังพักฟื้น", "กำลังส่งกลับตึก", "เลื่อนการผ่าตัด"],
                                             font=("Prompt", 14))
        self.status_combobox.grid(row=0, column=3, padx=5)

        add_button = tk.Button(input_frame, text="เพิ่มข้อมูล", command=self.add_patient, bg="#4caf50", fg="white", font=("Prompt", 12), relief="raised")
        add_button.grid(row=0, column=4, padx=5)

        edit_button = tk.Button(input_frame, text="แก้ไขข้อมูล", command=self.edit_patient, bg="#2196f3", fg="white", font=("Prompt", 12), relief="raised")
        edit_button.grid(row=0, column=5, padx=5)

        delete_button = tk.Button(input_frame, text="ลบข้อมูล", command=self.delete_patient, bg="#f44336", fg="white", font=("Prompt", 12), relief="raised")
        delete_button.grid(row=0, column=6, padx=5)

        # Table Frame
        table_frame = tk.Frame(self.root, bg="#f0f4f8", bd=2, relief="groove")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        style = ttk.Style()
        style.configure("Treeview", font=("Prompt", 14), rowheight=40, background="#ffffff", fieldbackground="#ffffff", borderwidth=2)
        style.configure("Treeview.Heading", font=("Prompt", 14, "bold"), background="#1f4e79", foreground="blue")

        self.tree = ttk.Treeview(table_frame, columns=("ID", "Patient ID", "Status", "Timer"), show='headings')
        self.tree.heading("ID", text="ID")
        self.tree.heading("Patient ID", text="รหัสผู้ป่วย")
        self.tree.heading("Status", text="สถานะ")
        self.tree.heading("Timer", text="เวลา")

        # Adjust column widths
        self.tree.column("ID", width=100, anchor='center')
        self.tree.column("Patient ID", width=250, anchor='center')
        self.tree.column("Status", width=300, anchor='center')
        self.tree.column("Timer", width=200, anchor='center')

        # Scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side='right', fill='y')

        self.tree.pack(fill=tk.BOTH, expand=True)

        # กำหนดสี
        self.tree.tag_configure("waiting", background="#FFEB3B")
        self.tree.tag_configure("surgery", background="#F44336")
        self.tree.tag_configure("recovery", background="#4CAF50")
        self.tree.tag_configure("discharge", background="#9C27B0")
        self.tree.tag_configure("recovery_complete", background="#FF9800", foreground="white")
        self.tree.tag_configure("postponed", background="#607D8B", foreground="white")

        self.update_timers()  # เริ่มต้นการอัปเดตเวลา

    def add_patient(self):
        # ข้อมูลที่จะส่ง
        payload = {
            'patient_id': self.patient_id_entry.get(),
            'status': self.status_var.get()
        }

        # URL ของเซิร์ฟเวอร์
        url = "http://10.0.212.221/add_patient"  # เปลี่ยน URL ให้ตรงกับ API ของคุณ
        headers = {'Content-Type': 'application/json'}

        # ส่งคำขอ POST
        response = requests.post(url, data=json.dumps(payload), headers=headers)

        if response.status_code == 200:
            try:
                response_data = response.json()  # พยายามแปลงเป็น JSON
                messagebox.showinfo("สำเร็จ", "เพิ่มข้อมูลผู้ป่วยสำเร็จ")
            except ValueError:
                messagebox.showerror("ข้อผิดพลาด", "ได้รับข้อมูลที่ไม่สามารถแปลงเป็น JSON ได้จากเซิร์ฟเวอร์")
        else:
            messagebox.showerror("ข้อผิดพลาด", f"เกิดข้อผิดพลาดจากเซิร์ฟเวอร์: {response.status_code}")

    def edit_patient(self):
        print("เริ่มต้นฟังก์ชัน edit_patient")  # Debugging
        selected_item = self.tree.selection()
        print(f"Selected Item: {selected_item}")  # Debugging

        if not selected_item:
            messagebox.showerror("ข้อผิดพลาด", "กรุณาเลือกข้อมูลที่ต้องการแก้ไข")
            return

        item = self.tree.item(selected_item)
        print(f"Item Data: {item}")  # Debugging

        patient_id = str(item['values'][1])  # ตรวจสอบว่าดัชนีถูกต้อง
        print(f"Patient ID: {patient_id}")  # Debugging

        new_status = self.status_var.get()
        print(f"New Status: {new_status}")  # Debugging

        if not new_status:
            messagebox.showerror("ข้อผิดพลาด", "กรุณาเลือกสถานะใหม่")
            return

        if patient_id not in self.patient_data:
            messagebox.showerror("ข้อผิดพลาด", f"ไม่พบข้อมูลของผู้ป่วย {patient_id}")
            return

        print(f"Updating status for {patient_id}")  # Debugging
        self.patient_data[patient_id]["status"] = new_status

        if new_status == "กำลังผ่าตัด":
            self.patient_data[patient_id]["timestamp"] = datetime.now()

        # อัปเดตข้อมูลใน treeview
        try:
            self.tree.item(selected_item, values=(
                self.patient_data[patient_id]["id"],
                patient_id,
                new_status,
                self.patient_data[patient_id].get("timestamp", "")
            ))
            self.tree.selection_remove(selected_item)  # เอาแถบสีน้ำเงินออก
            print("อัปเดตข้อมูลสำเร็จ")  # Debugging
        except Exception as e:
            print(f"Error updating tree: {e}")  # Debugging

        self.clear_input_fields()
        print("จบฟังก์ชัน edit_patient")  # Debugging

    def delete_patient(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showerror("ข้อผิดพลาด", "กรุณาเลือกข้อมูลที่ต้องการลบ")
            return

        item = self.tree.item(selected_item)
        patient_id = item['values'][1]

        # ตรวจสอบว่าข้อมูล patient_id เป็น string หรือ int แล้วแปลงให้ตรงกัน
        patient_id = str(patient_id)  # ถ้าเก็บเป็น string

        # ตรวจสอบว่า patient_id มีอยู่ใน self.patient_data หรือไม่
        if patient_id not in self.patient_data:
            messagebox.showerror("ข้อผิดพลาด", f"ไม่พบข้อมูลของผู้ป่วย {patient_id}")
            return

        del self.patient_data[patient_id]
        self.tree.delete(selected_item)

    def update_timers(self):
        for item in self.tree.get_children():
            values = self.tree.item(item, 'values')
            patient_id = values[1]

            if patient_id in self.patient_data:
                data = self.patient_data[patient_id]
                timer_text = ""

                if data["status"] == "กำลังผ่าตัด":
                    elapsed = datetime.now() - data["timestamp"]
                    timer_text = str(elapsed).split('.')[0]

                elif data["status"] in ["กำลังพักฟื้น", "พักฟื้นครบแล้ว"]:
                    elapsed = datetime.now() - data["timestamp"]

                    if data["status"] == "กำลังพักฟื้น":
                        if elapsed >= timedelta(hours=1):
                            if "recovery_complete_time" not in data:
                                data["recovery_complete_time"] = datetime.now()
                                data["status"] = "พักฟื้นครบแล้ว"
                            timer_text = "พักฟื้นครบแล้ว"
                        else:
                            timer_text = str(elapsed).split('.')[0]

                    if data["status"] == "พักฟื้นครบแล้ว":
                        recovery_elapsed = datetime.now() - data["recovery_complete_time"]
                        if recovery_elapsed >= timedelta(seconds=180):
                            data["status"] = "ส่งกลับตึก"
                            data["timestamp"] = datetime.now()
                        timer_text = "พักฟื้นครบแล้ว"

                self.tree.item(item, values=(values[0], values[1], data["status"], timer_text))

        self.root.after(1000, self.update_timers)  # อัปเดตทุก 1 วินาที

    def clear_input_fields(self):
        self.patient_id_entry.delete(0, tk.END)
        self.status_var.set("")



if __name__ == "__main__":
    root = tk.Tk()
    app = SurgeryStatusApp(root)
    root.mainloop()
