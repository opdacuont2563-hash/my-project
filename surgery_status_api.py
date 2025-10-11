from flask import Flask, request, jsonify
import sqlite3

app = Flask(__name__)

def init_db():
    with sqlite3.connect("surgery.db") as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS patients (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            patient_id TEXT UNIQUE,
                            status TEXT,
                            timestamp TEXT)''')
        conn.commit()

@app.route("/patients", methods=["GET"])
def get_patients():
    with sqlite3.connect("surgery.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM patients")
        patients = cursor.fetchall()
    return jsonify(patients)

@app.route("/patients", methods=["POST"])
def add_patient():
    data = request.json
    with sqlite3.connect("surgery.db") as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO patients (patient_id, status, timestamp) VALUES (?, ?, ?)",
                           (data["patient_id"], data["status"], data.get("timestamp")))
            conn.commit()
        except sqlite3.IntegrityError:
            return jsonify({"error": "รหัสผู้ป่วยนี้มีอยู่แล้ว"}), 400
    return jsonify({"message": "เพิ่มข้อมูลสำเร็จ"})

@app.route("/patients/<patient_id>", methods=["PUT"])
def update_patient(patient_id):
    data = request.json
    with sqlite3.connect("surgery.db") as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE patients SET status=?, timestamp=? WHERE patient_id=?",
                       (data["status"], data.get("timestamp"), patient_id))
        conn.commit()
    return jsonify({"message": "อัปเดตข้อมูลสำเร็จ"})

@app.route("/patients/<patient_id>", methods=["DELETE"])
def delete_patient(patient_id):
    with sqlite3.connect("surgery.db") as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM patients WHERE patient_id=?", (patient_id,))
        conn.commit()
    return jsonify({"message": "ลบข้อมูลสำเร็จ"})

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
