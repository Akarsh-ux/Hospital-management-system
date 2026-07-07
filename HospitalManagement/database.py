

import sqlite3
from werkzeug.security import generate_password_hash

DB_NAME = "hospital.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_tables(cursor):

    # =====================================================
    # USERS TABLE (staff accounts / authentication)
    # =====================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin', 'doctor', 'receptionist')),
        email TEXT,
        phone TEXT,
        doctor_id INTEGER,
        is_active INTEGER NOT NULL DEFAULT 1,
        last_login TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE SET NULL
    )
    """)

    # =====================================================
    # DEPARTMENTS TABLE
    # =====================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT
    )
    """)

    # =====================================================
    # DOCTORS TABLE
    # =====================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS doctors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        gender TEXT,
        department_id INTEGER,
        specialization TEXT NOT NULL,
        qualification TEXT,
        experience INTEGER NOT NULL DEFAULT 0,
        phone TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        consultation_fee REAL NOT NULL DEFAULT 0,
        availability TEXT,
        photo TEXT,
        status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active', 'Inactive')),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL
    )
    """)

    # =====================================================
    # PATIENTS TABLE
    # =====================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mrn TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        dob TEXT,
        age INTEGER,
        gender TEXT NOT NULL,
        blood_group TEXT,
        phone TEXT NOT NULL,
        email TEXT,
        address TEXT NOT NULL,
        emergency_contact_name TEXT,
        emergency_contact_phone TEXT,
        disease TEXT,
        medical_history TEXT,
        allergies TEXT,
        photo TEXT,
        status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active', 'Inactive')),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)

    # =====================================================
    # APPOINTMENTS TABLE
    # =====================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        doctor_id INTEGER NOT NULL,
        appointment_date TEXT NOT NULL,
        appointment_time TEXT NOT NULL,
        reason TEXT,
        status TEXT NOT NULL DEFAULT 'Scheduled'
            CHECK(status IN ('Scheduled', 'Completed', 'Cancelled', 'No-show')),
        diagnosis TEXT,
        prescription TEXT,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
        FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE
    )
    """)

    # =====================================================
    # BILLS TABLE
    # =====================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_no TEXT NOT NULL UNIQUE,
        patient_id INTEGER NOT NULL,
        appointment_id INTEGER,
        consultation_fee REAL NOT NULL DEFAULT 0,
        medicine_charge REAL NOT NULL DEFAULT 0,
        lab_charge REAL NOT NULL DEFAULT 0,
        room_charge REAL NOT NULL DEFAULT 0,
        other_charge REAL NOT NULL DEFAULT 0,
        discount REAL NOT NULL DEFAULT 0,
        tax_percent REAL NOT NULL DEFAULT 0,
        total_amount REAL NOT NULL DEFAULT 0,
        payment_status TEXT NOT NULL DEFAULT 'Unpaid'
            CHECK(payment_status IN ('Paid', 'Unpaid', 'Partial')),
        payment_method TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
        FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL
    )
    """)

    # =====================================================
    # AUDIT LOG TABLE
    # =====================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        action TEXT NOT NULL,
        details TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)


def seed_data(cursor):

    # ---------------- Default Admin ----------------
    cursor.execute("""
        INSERT OR IGNORE INTO users
            (username, password_hash, full_name, role, email, is_active)
        VALUES (?, ?, ?, 'admin', ?, 1)
    """, (
        "admin",
        generate_password_hash("Admin@123"),
        "System Administrator",
        "admin@hospital.local",
    ))

    # ---------------- Sample Departments ----------------
    departments = [
        ("General Medicine", "Primary & preventive care"),
        ("Cardiology", "Heart & cardiovascular care"),
        ("Orthopedics", "Bone, joint & muscle care"),
        ("Pediatrics", "Child health care"),
        ("Dermatology", "Skin, hair & nail care"),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO departments (name, description) VALUES (?, ?)",
        departments
    )

    # ---------------- Sample Doctors ----------------
    cursor.execute("SELECT id, name FROM departments")
    dept_map = {name: dept_id for dept_id, name in cursor.fetchall()}

    doctors = [
        ("Dr. Sarah Johnson", "Female", dept_map.get("Cardiology"),
         "Cardiologist", "MD, DM Cardiology", 12, "9876500001",
         "sarah.johnson@hospital.local", 800, "Mon-Fri 9:00 AM - 4:00 PM"),
        ("Dr. Rajesh Kumar", "Male", dept_map.get("General Medicine"),
         "General Physician", "MBBS, MD", 8, "9876500002",
         "rajesh.kumar@hospital.local", 500, "Mon-Sat 10:00 AM - 6:00 PM"),
        ("Dr. Emily Davis", "Female", dept_map.get("Pediatrics"),
         "Pediatrician", "MBBS, DCH", 6, "9876500003",
         "emily.davis@hospital.local", 600, "Mon-Fri 11:00 AM - 5:00 PM"),
    ]
    cursor.executemany("""
        INSERT OR IGNORE INTO doctors
            (name, gender, department_id, specialization, qualification,
             experience, phone, email, consultation_fee, availability)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, doctors)


def main():
    conn = get_connection()
    cursor = conn.cursor()

    create_tables(cursor)
    seed_data(cursor)

    conn.commit()
    conn.close()

    print("=" * 55)
    print(" Hospital Management System - Database Ready")
    print("=" * 55)
    print("Tables: users, departments, doctors, patients,")
    print("        appointments, bills, audit_log")
    print("-" * 55)
    print("Default Admin Login")
    print("  Username : admin")
    print("  Password : Admin@123")
    print("-" * 55)
    print("IMPORTANT: Change the default admin password")
    print("immediately after your first login.")
    print("=" * 55)


if __name__ == "__main__":
    main()
