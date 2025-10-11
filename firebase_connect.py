import tkinter as tk
from tkinter import ttk, messagebox
import requests
import socketio
from datetime import datetime, timedelta

SERVER_URL = "http://10.0.212.176:5000"
sio = socketio.Client()

# กำหนด handler สำหรับ event 'disconnect'
@sio.event
def disconnect():
    print("Disconnected from server")  # จะพิมพ์ข้อความนี้เมื่อถูกตัดการเชื่อมต่อ

# กำหนด handler สำหรับ event 'update' ที่ได้รับข้อมูลจาก Server
# ฟังก์ชันที่รับข้อมูลจาก Server ผ่าน socketio
@sio.event
def update(data):
    print(f"Data received from server: {data}")
    # อัปเดตข้อมูลใน Treeview
    self.update_data(data)  # อัปเดต Treeview จากข้อมูลที่ได้รับ


class SurgeryStatusClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Surgery Status Client")
        self.root.geometry("1280x720")
        self.root.configure(bg="#f0f4f8")
        self.patient_data = {}
        self.selected_patient_id = None  # เก็บ patient_id ที่เลือกไว้

        # ... (ส่วนที่เหลือของโค้ดไม่เปลี่ยนแปลง)

        title_frame = tk.Frame(root, bg="#1f4e79", pady=10)
        title_frame.pack(fill="x")
        title_label = tk.Label(title_frame, text="Surgery Status Tracking", font=("Prompt", 24, "bold"), fg="white",
                               bg="#1f4e79")
        title_label.pack()

        input_frame = tk.Frame(root, bg="#f0f4f8")
        input_frame.pack(pady=10)

        tk.Label(input_frame, text="รหัสผู้ป่วย:", font=("Prompt", 14), bg="#f0f4f8").grid(row=0, column=0, padx=5)
        self.patient_id_entry = tk.Entry(input_frame, font=("Prompt", 14))
        self.patient_id_entry.grid(row=0, column=1, padx=5)

        tk.Label(input_frame, text="สถานะ:", font=("Prompt", 14), bg="#f0f4f8").grid(row=0, column=2, padx=5)
        self.status_combobox = ttk.Combobox(input_frame,
                                            values=["รอผ่าตัด", "กำลังผ่าตัด", "กำลังพักฟื้น", "พักฟื้นครบแล้ว",
                                                    "กำลังส่งกลับตึก"],
                                            font=("Prompt", 14), state="readonly")
        self.status_combobox.grid(row=0, column=3, padx=5)

        add_button = tk.Button(input_frame, text="เพิ่มข้อมูล", command=self.add_patient, bg="#4caf50", fg="white",
                               font=("Prompt", 12), relief="raised")
        add_button.grid(row=0, column=4, padx=5)

        edit_button = tk.Button(input_frame, text="แก้ไขข้อมูล", command=self.edit_patient, bg="#2196f3", fg="white",
                                font=("Prompt", 12), relief="raised")
        edit_button.grid(row=0, column=5, padx=5)

        delete_button = tk.Button(input_frame, text="ลบข้อมูล", command=self.delete_patient, bg="#f44336", fg="white",
                                  font=("Prompt", 12), relief="raised")
        delete_button.grid(row=0, column=6, padx=5)

        table_frame = tk.Frame(root, bg="#f0f4f8")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tree = ttk.Treeview(table_frame, columns=("ID", "Patient ID", "Status", "Time"), show='headings')
        self.tree.heading("ID", text="ID")
        self.tree.heading("Patient ID", text="รหัสผู้ป่วย")
        self.tree.heading("Status", text="สถานะ")
        self.tree.heading("Time", text="เวลาที่ผ่านไป")
        self.tree.column("ID", width=50, anchor='center')
        self.tree.column("Patient ID", width=200, anchor='center')
        self.tree.column("Status", width=200, anchor='center')
        self.tree.column("Time", width=200, anchor='center')

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.tree.pack(fill=tk.BOTH, expand=True)

        self.connect_to_server()
        self.load_data()
        self.update_timers()

    def connect_to_server(self):
        # ตรวจสอบว่าเชื่อมต่อแล้วหรือยัง
        if not sio.connected:
            try:
                sio.connect(SERVER_URL)
                print("Connected to server successfully!")
            except Exception as e:
                print(f"Error connecting to server: {e}")
        else:
            print("Already connected to server!")

    def load_data(self):
        try:
            response = requests.get(f"{SERVER_URL}/patients")
            response.raise_for_status()
            data = response.json()

            # แก้ไขให้ self.patient_data เก็บข้อมูลในรูปแบบที่เหมาะสม
            self.patient_data = {
                p["patient_id"]: p for p in data
            }

            self.update_data(data)

        except Exception as e:
            print(f"โหลดข้อมูลไม่สำเร็จ: {e}")

    def update_data(self, data):
        # เก็บการเลือกที่เกิดขึ้นก่อนจะรีเฟรชข้อมูล
        selected_item = self.tree.selection()
        if selected_item:
            values = self.tree.item(selected_item[0], 'values')
            self.selected_patient_id = values[1]  # เก็บ patient_id ที่เลือก

        self.patient_data = {
            p["patient_id"]: {
                "id": p["id"],
                "status": p["status"],
                "timestamp": datetime.strptime(p["timestamp"], "%Y-%m-%d %H:%M:%S")
            } for p in data
        }

        # ลบข้อมูลใน Treeview เก่าทั้งหมด
        self.tree.delete(*self.tree.get_children())

        # กำหนดสีสำหรับแต่ละสถานะ
        status_colors = {
            "รอผ่าตัด": "yellow",
            "กำลังผ่าตัด": "red",
            "กำลังพักฟื้น": "green",
            "พักฟื้นครบแล้ว": "orange",
            "กำลังส่งกลับตึก": "purple"
        }

        for patient in data:
            elapsed_time = ""
            timestamp = datetime.strptime(patient["timestamp"], "%Y-%m-%d %H:%M:%S")
            elapsed = datetime.now() - timestamp

            if patient["status"] == "กำลังพักฟื้น" and elapsed >= timedelta(hours=1):
                if elapsed < timedelta(hours=1, minutes=30):
                    patient["status"] = "พักฟื้นครบแล้ว"
                else:
                    remaining = 300 - (elapsed - timedelta(hours=1, minutes=30)).seconds
                    patient["status"] = f"กำลังจะส่งภายใน {remaining // 60} นาที"

                # ส่งข้อมูลอัปเดตไปที่เซิร์ฟเวอร์
                requests.put(f"{SERVER_URL}/patients/{patient['patient_id']}", json={"status": patient["status"]})

            elapsed_time = str(elapsed).split('.')[0]

            # เพิ่มข้อมูลลงใน Treeview และกำหนดสีให้กับแต่ละสถานะ
            status_color = status_colors.get(patient["status"], "white")  # หากสถานะไม่พบให้เป็นสีขาว
            self.tree.insert("", "end", values=(patient["id"], patient["patient_id"], patient["status"], elapsed_time),
                             tags=(status_color,))

        # เลือกไอเทมเดิมที่เก็บไว้หลังจากที่ข้อมูลถูกรีเฟรช
        if self.selected_patient_id:
            for item in self.tree.get_children():
                values = self.tree.item(item, 'values')
                if values[1] == self.selected_patient_id:  # เปรียบเทียบ patient_id
                    self.tree.selection_add(item)
                    break

        # กำหนดสีพื้นหลังให้กับแต่ละแท็กที่กำหนดไว้
        self.tree.tag_configure("yellow", background="yellow")
        self.tree.tag_configure("red", background="red")
        self.tree.tag_configure("green", background="green")
        self.tree.tag_configure("orange", background="orange")
        self.tree.tag_configure("purple", background="purple")
        self.tree.tag_configure("white", background="white")  # กรณีไม่มีสี

    def update_timers(self):
        self.load_data()
        self.root.after(1000, self.update_timers)

    def add_patient(self):
        patient_id = self.patient_id_entry.get()
        status = self.status_combobox.get()

        if patient_id and status:
            try:
                # ส่งคำขอไปยัง server เพื่อเพิ่มข้อมูลผู้ป่วยใหม่
                response = requests.post(f"{SERVER_URL}/patients", json={"patient_id": patient_id, "status": status})

                if response.status_code == 201:
                    print(f"Added new patient: {response.json()}")  # ตรวจสอบว่าเพิ่มข้อมูลได้หรือไม่
                    # ส่งข้อมูลไปที่ Server โดยใช้ socketio.emit
                    sio.emit("update", response.json())  # ส่งข้อมูลอัปเดต
                    self.load_data()  # รีเฟรชข้อมูลหลังจากเพิ่ม
                else:
                    messagebox.showerror("Error", "ไม่สามารถเพิ่มข้อมูลผู้ป่วยได้")
            except Exception as e:
                print(f"Error: {e}")
                messagebox.showerror("Error", "เกิดข้อผิดพลาดในการติดต่อกับ server")

    def edit_patient(self):
        selected_item = self.tree.selection()
        if selected_item:
            patient_id = self.tree.item(selected_item[0], "values")[1]
            new_status = self.status_combobox.get()

            if new_status:
                try:
                    # ส่งคำขอไปยัง server เพื่อแก้ไขสถานะผู้ป่วย
                    response = requests.put(f"{SERVER_URL}/patients/{patient_id}", json={"status": new_status})

                    if response.status_code == 200:
                        print(f"Updated patient status: {response.json()}")
                        # ส่งข้อมูลไปที่ Server
                        sio.emit("update", response.json())
                        self.load_data()  # รีเฟรชข้อมูลหลังจากแก้ไข
                    else:
                        messagebox.showerror("Error", "ไม่สามารถแก้ไขข้อมูลผู้ป่วยได้")
                except Exception as e:
                    print(f"Error: {e}")
                    messagebox.showerror("Error", "เกิดข้อผิดพลาดในการติดต่อกับ server")

    def delete_patient(self):
        selected_item = self.tree.selection()
        if selected_item:
            patient_id = self.tree.item(selected_item[0], "values")[1]
            try:
                # ส่งคำขอไปยัง server เพื่อลบข้อมูลผู้ป่วย
                response = requests.delete(f"{SERVER_URL}/patients/{patient_id}")

                if response.status_code == 200:
                    print(f"Deleted patient: {response.json()}")
                    # ส่งข้อมูลไปที่ Server
                    sio.emit("update", response.json())
                    self.load_data()  # รีเฟรชข้อมูลหลังจากลบ
                else:
                    messagebox.showerror("Error", "ไม่สามารถลบข้อมูลผู้ป่วยได้")
            except Exception as e:
                print(f"Error: {e}")
                messagebox.showerror("Error", "เกิดข้อผิดพลาดในการติดต่อกับ server")

if __name__ == "__main__":
    root = tk.Tk()
    app = SurgeryStatusClient(root)
    root.mainloop()
