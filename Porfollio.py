import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import sqlite3
import os
from PIL import Image, ImageTk
import shutil

# สร้างโฟลเดอร์สำหรับเก็บรูปและเอกสารถ้ายังไม่มี
if not os.path.exists('photos'):
    os.makedirs('photos')
if not os.path.exists('documents'):
    os.makedirs('documents')

# ตั้งค่าฐานข้อมูล
conn = sqlite3.connect('employee_data.db')
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id TEXT,
        title TEXT,
        first_name TEXT,
        last_name TEXT,
        gender TEXT,
        dob TEXT,
        age INTEGER,
        height REAL,
        weight REAL,
        blood_group TEXT,
        nationality TEXT,
        ethnicity TEXT,
        religion TEXT,
        military_status TEXT,
        photo TEXT,
        document TEXT,
        note TEXT
    )
''')
conn.commit()


# ฟังก์ชัน
def save_data():
    if not employee_id_var.get():
        messagebox.showerror("Error", "กรุณากรอกรหัสพนักงาน")
        return

    # รูปถ่าย
    if photo_path_var.get():
        photo_filename = os.path.basename(photo_path_var.get())
        new_photo_path = os.path.join('photos', photo_filename)
        shutil.copy(photo_path_var.get(), new_photo_path)
    else:
        new_photo_path = ""

    # เอกสาร PDF
    if document_path_var.get():
        doc_filename = os.path.basename(document_path_var.get())
        new_doc_path = os.path.join('documents', doc_filename)
        shutil.copy(document_path_var.get(), new_doc_path)
    else:
        new_doc_path = ""

    # บันทึกลงฐานข้อมูล
    c.execute('''
        INSERT INTO employees (
            employee_id, title, first_name, last_name, gender, dob, age,
            height, weight, blood_group, nationality, ethnicity, religion,
            military_status, photo, document, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        employee_id_var.get(), title_var.get(), first_name_var.get(), last_name_var.get(),
        gender_var.get(), dob_var.get(), age_var.get(),
        height_var.get(), weight_var.get(), blood_group_var.get(),
        nationality_var.get(), ethnicity_var.get(), religion_var.get(),
        military_status_var.get(), new_photo_path, new_doc_path, note_text.get("1.0", tk.END)
    ))
    conn.commit()
    messagebox.showinfo("Success", "บันทึกข้อมูลสำเร็จ")
    clear_form()


def clear_form():
    employee_id_var.set("")
    title_var.set("")
    first_name_var.set("")
    last_name_var.set("")
    gender_var.set("")
    dob_var.set("")
    age_var.set("")
    height_var.set("")
    weight_var.set("")
    blood_group_var.set("")
    nationality_var.set("")
    ethnicity_var.set("")
    religion_var.set("")
    military_status_var.set("")
    photo_label.config(image="")
    photo_path_var.set("")
    document_label.config(text="")
    document_path_var.set("")
    note_text.delete("1.0", tk.END)


def select_photo():
    filepath = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.jpeg *.png")])
    if filepath:
        photo_path_var.set(filepath)
        img = Image.open(filepath)
        img = img.resize((100, 130))
        photo = ImageTk.PhotoImage(img)
        photo_label.config(image=photo)
        photo_label.image = photo


def select_document():
    filepath = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
    if filepath:
        document_path_var.set(filepath)
        document_label.config(text=os.path.basename(filepath))


# หน้าต่างหลัก
root = tk.Tk()
root.title("ระบบบันทึกข้อมูลพนักงาน (มี Tab)")

# ตัวแปร
employee_id_var = tk.StringVar()
title_var = tk.StringVar()
first_name_var = tk.StringVar()
last_name_var = tk.StringVar()
gender_var = tk.StringVar()
dob_var = tk.StringVar()
age_var = tk.StringVar()
height_var = tk.StringVar()
weight_var = tk.StringVar()
blood_group_var = tk.StringVar()
nationality_var = tk.StringVar()
ethnicity_var = tk.StringVar()
religion_var = tk.StringVar()
military_status_var = tk.StringVar()
photo_path_var = tk.StringVar()
document_path_var = tk.StringVar()

# สร้าง Notebook (Tab Control)
notebook = ttk.Notebook(root)
notebook.pack(padx=10, pady=10, expand=True, fill='both')

# --- Tab Administrator ---
tab_admin = tk.Frame(notebook)
notebook.add(tab_admin, text="Administrator")

frame_admin = tk.Frame(tab_admin)
frame_admin.pack(padx=10, pady=10)

tk.Label(frame_admin, text="รหัสพนักงาน").grid(row=0, column=0)
tk.Entry(frame_admin, textvariable=employee_id_var).grid(row=0, column=1)

tk.Label(frame_admin, text="คำนำหน้า").grid(row=1, column=0)
tk.Entry(frame_admin, textvariable=title_var).grid(row=1, column=1)

tk.Label(frame_admin, text="ชื่อ").grid(row=2, column=0)
tk.Entry(frame_admin, textvariable=first_name_var).grid(row=2, column=1)

tk.Label(frame_admin, text="นามสกุล").grid(row=3, column=0)
tk.Entry(frame_admin, textvariable=last_name_var).grid(row=3, column=1)

tk.Label(frame_admin, text="เพศ").grid(row=4, column=0)
ttk.Combobox(frame_admin, textvariable=gender_var, values=["ชาย", "หญิง"]).grid(row=4, column=1)

tk.Label(frame_admin, text="วันเกิด (dd/mm/yyyy)").grid(row=5, column=0)
tk.Entry(frame_admin, textvariable=dob_var).grid(row=5, column=1)

tk.Label(frame_admin, text="อายุ").grid(row=6, column=0)
tk.Entry(frame_admin, textvariable=age_var).grid(row=6, column=1)

tk.Label(frame_admin, text="ส่วนสูง (cm)").grid(row=7, column=0)
tk.Entry(frame_admin, textvariable=height_var).grid(row=7, column=1)

tk.Label(frame_admin, text="น้ำหนัก (kg)").grid(row=8, column=0)
tk.Entry(frame_admin, textvariable=weight_var).grid(row=8, column=1)

tk.Label(frame_admin, text="หมู่เลือด").grid(row=9, column=0)
tk.Entry(frame_admin, textvariable=blood_group_var).grid(row=9, column=1)

tk.Label(frame_admin, text="สัญชาติ").grid(row=10, column=0)
tk.Entry(frame_admin, textvariable=nationality_var).grid(row=10, column=1)

tk.Label(frame_admin, text="เชื้อชาติ").grid(row=11, column=0)
tk.Entry(frame_admin, textvariable=ethnicity_var).grid(row=11, column=1)

tk.Label(frame_admin, text="ศาสนา").grid(row=12, column=0)
tk.Entry(frame_admin, textvariable=religion_var).grid(row=12, column=1)

tk.Label(frame_admin, text="สถานะทางทหาร").grid(row=13, column=0)
tk.Entry(frame_admin, textvariable=military_status_var).grid(row=13, column=1)

photo_label = tk.Label(frame_admin)
photo_label.grid(row=0, column=2, rowspan=8, padx=10)

tk.Button(frame_admin, text="เลือกรูปถ่าย", command=select_photo).grid(row=8, column=2)

document_label = tk.Label(frame_admin, text="")
document_label.grid(row=9, column=2)

tk.Button(frame_admin, text="แนบเอกสาร PDF", command=select_document).grid(row=10, column=2)

# --- Tab Note ---
tab_note = tk.Frame(notebook)
notebook.add(tab_note, text="Note")

note_text = tk.Text(tab_note, height=20)
note_text.pack(fill="both", expand=True, padx=10, pady=10)

# --- Tab Attachment ---
tab_attach = tk.Frame(notebook)
notebook.add(tab_attach, text="Attachment")

tk.Label(tab_attach, text="(ในอนาคต: แนบไฟล์อื่น ๆ ได้ที่นี่)").pack(padx=10, pady=10)

# ปุ่มควบคุม
frame_button = tk.Frame(root)
frame_button.pack(pady=10)

tk.Button(frame_button, text="Save", command=save_data, width=10).pack(side=tk.LEFT, padx=10)
tk.Button(frame_button, text="New", command=clear_form, width=10).pack(side=tk.LEFT, padx=10)
tk.Button(frame_button, text="Close", command=root.quit, width=10).pack(side=tk.RIGHT, padx=10)

root.mainloop()
