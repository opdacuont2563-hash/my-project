import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime, timedelta

class SurgeryStatusApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Surgery Status Tracker")
        self.root.geometry("1920x1080")
        self.patient_data = {}
        self.id_counter = 1

        self.root.configure(bg="#f0f4f8")
        self.root.option_add("*TCombobox*Listbox.Font", ("Prompt", 14))

        title_frame = tk.Frame(root, bg="#1f4e79", pady=20, padx=20, bd=5, relief="ridge")
        title_frame.pack(pady=10, fill="x")

        title_label = tk.Label(title_frame, text="ติดตามสถานะการผ่าตัดโรงพยาบาลหนองบัวลำภู", font=("Prompt", 40, "bold"), fg="white", bg="#1f4e79")
        title_label.pack()

        credit_label = tk.Label(root, text="Parinya Kaewsupho Copyright 2025", font=("Prompt", 10), bg="#f0f4f8")
        credit_label.pack(pady=5)

        input_frame = tk.Frame(root, pady=10, bg="#f0f4f8")
        input_frame.pack()

        tk.Label(input_frame, text="รหัสผู้ป่วย:", font=("Prompt", 14), bg="#f0f4f8").grid(row=0, column=0, padx=5)
        self.patient_id_entry = tk.Entry(input_frame, font=("Prompt",12), bg="#e8f0fe", relief="solid")
        self.patient_id_entry.grid(row=0, column=1, padx=5)

        tk.Label(input_frame, text="สถานะการผ่าตัด:", font=("Prompt", 12), bg="#f0f4f8").grid(row=0, column=2, padx=5)
        self.status_var = tk.StringVar()
        self.status_combobox = ttk.Combobox(input_frame, textvariable=self.status_var, values=["รอผ่าตัด", "กำลังผ่าตัด", "กำลังพักฟื้น", "กำลังส่งกลับตึก"], font=("Prompt", 18))
        self.status_combobox.grid(row=0, column=3, padx=5)

        style = ttk.Style()
        style.configure('TCombobox', font=('Prompt', 14))
        style.map('TCombobox', fieldbackground=[('readonly', '#e8f0fe')], background=[('readonly', '#e8f0fe')])

        add_button = tk.Button(input_frame, text="เพิ่มข้อมูล", command=self.add_patient, bg="#4caf50", fg="white", font=("Prompt", 12), relief="raised")
        add_button.grid(row=0, column=4, padx=5)

        edit_button = tk.Button(input_frame, text="แก้ไขข้อมูล", command=self.edit_patient, bg="#2196f3", fg="white", font=("Prompt", 12), relief="raised")
        edit_button.grid(row=0, column=5, padx=5)

        delete_button = tk.Button(input_frame, text="ลบข้อมูล", command=self.delete_patient, bg="#f44336", fg="white", font=("Prompt", 12), relief="raised")
        delete_button.grid(row=0, column=6, padx=5)

        table_frame = tk.Frame(root, bg="#f0f4f8", bd=2, relief="groove")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        style.configure("Treeview", font=("Prompt", 30), rowheight=60, background="#ffffff", fieldbackground="#ffffff", borderwidth=2, relief="solid")
        style.configure("Treeview.Heading", font=("Prompt", 30, "bold"), background="#1f4e79", foreground="blue", relief="solid")

        self.tree = ttk.Treeview(table_frame, columns=("ID", "Patient ID", "Status", "Timer"), show='headings')
        self.tree.heading("ID", text="ID")
        self.tree.heading("Patient ID", text="รหัสผู้ป่วย (Patient ID)")
        self.tree.heading("Status", text="สถานะ (Status)")
        self.tree.heading("Timer", text="เวลา (Elapsed Time)")

        self.tree.column("ID", width=100, anchor='center', minwidth=100)
        self.tree.column("Patient ID", width=400, anchor='center', minwidth=400)
        self.tree.column("Status", width=600, anchor='center', minwidth=600)
        self.tree.column("Timer", width=400, anchor='center', minwidth=400)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side='right', fill='y')

        self.tree.pack(fill=tk.BOTH, expand=True)
        self.update_timers()

    def add_patient(self):
        patient_id = self.patient_id_entry.get()
        status = self.status_var.get()
        if not patient_id or not status:
            messagebox.showerror("ข้อผิดพลาด", "กรุณากรอกข้อมูลให้ครบถ้วน")
            return
        self.patient_data[self.id_counter] = {"patient_id": patient_id, "status": status, "start_time": datetime.now()}
        self.tree.insert("", "end", values=(self.id_counter, patient_id, status, "0:00"))
        self.id_counter += 1

    def edit_patient(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showerror("ข้อผิดพลาด", "กรุณาเลือกผู้ป่วยที่ต้องการแก้ไข")
            return
        item = selected_item[0]
        item_values = self.tree.item(item, "values")
        new_status = self.status_var.get()
        if not new_status:
            messagebox.showerror("ข้อผิดพลาด", "กรุณาเลือกสถานะใหม่")
            return
        self.tree.item(item, values=(item_values[0], item_values[1], new_status, item_values[3]))
        self.patient_data[int(item_values[0])]["status"] = new_status

    def delete_patient(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showerror("ข้อผิดพลาด", "กรุณาเลือกผู้ป่วยที่ต้องการลบ")
            return
        for item in selected_item:
            item_values = self.tree.item(item, "values")
            del self.patient_data[int(item_values[0])]
            self.tree.delete(item)

    def update_timers(self):
        for item in self.tree.get_children():
            item_values = self.tree.item(item, "values")
            patient_id = int(item_values[0])
            elapsed_time = datetime.now() - self.patient_data[patient_id]["start_time"]
            minutes, seconds = divmod(elapsed_time.seconds, 60)
            self.tree.item(item, values=(item_values[0], item_values[1], item_values[2], f"{minutes}:{seconds:02d}"))
        self.root.after(1000, self.update_timers)

if __name__ == "__main__":
    root = tk.Tk()
    app = SurgeryStatusApp(root)
    root.mainloop()
