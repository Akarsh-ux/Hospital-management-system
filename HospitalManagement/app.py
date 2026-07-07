"""
================================================================
 Hospital Management System - Application Server
================================================================
A commercial-grade Flask application for managing patients,
doctors, appointments and billing inside a small-to-mid size
hospital or clinic.

Run:
    python database.py   (first time / to reset schema)
    python app.py
================================================================
"""

import os
import secrets
from datetime import datetime, timedelta

from flask import (
    Flask, render_template, request, redirect, session,
    url_for, flash, jsonify, abort, send_from_directory
)
from werkzeug.security import generate_password_hash, check_password_hash

from utils import (
    get_db_connection, login_required, roles_required, validate_csrf,
    generate_mrn, generate_invoice_no, is_valid_phone, is_valid_email,
    calculate_age, save_upload, log_action
)

app = Flask(__name__)

# -----------------------------------------------------------
# Configuration
# -----------------------------------------------------------
# In production set the SECRET_KEY via an environment variable,
# e.g. `export SECRET_KEY="a-long-random-value"`.
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=45)
app.config["UPLOAD_FOLDER"] = os.path.join("static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024  # 4 MB upload limit

HOSPITAL_NAME = os.environ.get("HOSPITAL_NAME", "CareWell Hospital")


# -----------------------------------------------------------
# Security headers on every response
# -----------------------------------------------------------
@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


# -----------------------------------------------------------
# Template globals / context processor
# -----------------------------------------------------------
@app.before_request
def ensure_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    session.permanent = True


@app.context_processor
def inject_globals():
    return {
        "hospital_name": HOSPITAL_NAME,
        "csrf_token": session.get("csrf_token", ""),
        "current_user": session.get("username"),
        "current_role": session.get("role"),
        "now": datetime.now(),
    }


# =====================================================================
# AUTHENTICATION
# =====================================================================
@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if "user_id" in session:
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()

    if user is None or not check_password_hash(user["password_hash"], password):
        conn.close()
        flash("Invalid username or password.", "danger")
        return render_template("login.html", username=username), 401

    if not user["is_active"]:
        conn.close()
        flash("This account has been deactivated. Contact the administrator.", "danger")
        return render_template("login.html"), 403

    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["full_name"] = user["full_name"]
    session["role"] = user["role"]
    session["doctor_id"] = user["doctor_id"]
    session["csrf_token"] = secrets.token_hex(16)

    conn.execute(
        "UPDATE users SET last_login = ? WHERE id = ?",
        (datetime.now().isoformat(timespec="seconds"), user["id"]),
    )
    conn.commit()
    log_action(conn, "LOGIN", f"{username} logged in")
    conn.close()

    flash(f"Welcome back, {user['full_name']}!", "success")
    return redirect(url_for("dashboard"))


@app.route("/logout")
@login_required
def logout():
    conn = get_db_connection()
    log_action(conn, "LOGOUT", f"{session.get('username')} logged out")
    conn.close()
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()

    if request.method == "POST":
        validate_csrf()
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not check_password_hash(user["password_hash"], current_password):
            flash("Current password is incorrect.", "danger")
        elif len(new_password) < 8:
            flash("New password must be at least 8 characters long.", "danger")
        elif new_password != confirm_password:
            flash("New password and confirmation do not match.", "danger")
        else:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(new_password), user["id"]),
            )
            conn.commit()
            log_action(conn, "PASSWORD_CHANGE", f"{session['username']} changed password")
            flash("Password updated successfully.", "success")

    conn.close()
    return render_template("profile.html", user=user)


# =====================================================================
# DASHBOARD
# =====================================================================
@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db_connection()

    patient_count = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    doctor_count = conn.execute(
        "SELECT COUNT(*) FROM doctors WHERE status = 'Active'"
    ).fetchone()[0]
    appointment_today = conn.execute(
        "SELECT COUNT(*) FROM appointments WHERE appointment_date = date('now')"
    ).fetchone()[0]
    revenue_month = conn.execute(
        """SELECT COALESCE(SUM(total_amount), 0) FROM bills
           WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')"""
    ).fetchone()[0]
    pending_bills = conn.execute(
        "SELECT COUNT(*) FROM bills WHERE payment_status != 'Paid'"
    ).fetchone()[0]

    upcoming = conn.execute("""
        SELECT a.id, p.name AS patient_name, d.name AS doctor_name,
               a.appointment_date, a.appointment_time, a.status
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.appointment_date >= date('now') AND a.status = 'Scheduled'
        ORDER BY a.appointment_date, a.appointment_time
        LIMIT 8
    """).fetchall()

    # Appointments per day for the last 7 days (for the chart)
    trend = conn.execute("""
        SELECT appointment_date, COUNT(*) AS total
        FROM appointments
        WHERE appointment_date >= date('now', '-6 days')
        GROUP BY appointment_date
        ORDER BY appointment_date
    """).fetchall()
    trend_map = {row["appointment_date"]: row["total"] for row in trend}
    trend_labels = [
        (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(6, -1, -1)
    ]
    trend_values = [trend_map.get(d, 0) for d in trend_labels]

    dept_split = conn.execute("""
        SELECT COALESCE(dep.name, 'Unassigned') AS department, COUNT(*) AS total
        FROM doctors d
        LEFT JOIN departments dep ON d.department_id = dep.id
        GROUP BY dep.name
    """).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        patients=patient_count,
        doctors=doctor_count,
        appointments_today=appointment_today,
        revenue_month=revenue_month,
        pending_bills=pending_bills,
        upcoming=upcoming,
        trend_labels=trend_labels,
        trend_values=trend_values,
        dept_labels=[row["department"] for row in dept_split],
        dept_values=[row["total"] for row in dept_split],
    )


# =====================================================================
# PATIENT MANAGEMENT
# =====================================================================
@app.route("/patients")
@login_required
def patients():
    keyword = request.args.get("keyword", "").strip()
    status_filter = request.args.get("status", "").strip()
    page = max(int(request.args.get("page", 1) or 1), 1)
    per_page = 10

    conn = get_db_connection()

    query = "SELECT * FROM patients WHERE 1=1"
    params = []

    if keyword:
        query += " AND (name LIKE ? OR mrn LIKE ? OR phone LIKE ? OR disease LIKE ?)"
        like = f"%{keyword}%"
        params += [like, like, like, like]

    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)

    total = conn.execute(
        f"SELECT COUNT(*) FROM ({query})", params
    ).fetchone()[0]

    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params += [per_page, (page - 1) * per_page]

    patient_rows = conn.execute(query, params).fetchall()
    conn.close()

    total_pages = max((total + per_page - 1) // per_page, 1)

    return render_template(
        "patients_list.html",
        patients=patient_rows,
        keyword=keyword,
        status_filter=status_filter,
        page=page,
        total_pages=total_pages,
        total=total,
    )


@app.route("/patients/view/<int:id>")
@login_required
def view_patient(id):
    conn = get_db_connection()
    patient = conn.execute("SELECT * FROM patients WHERE id = ?", (id,)).fetchone()
    if patient is None:
        conn.close()
        abort(404)

    history = conn.execute("""
        SELECT a.*, d.name AS doctor_name
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.patient_id = ?
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    """, (id,)).fetchall()

    bills = conn.execute("""
        SELECT * FROM bills WHERE patient_id = ? ORDER BY created_at DESC
    """, (id,)).fetchall()

    conn.close()
    return render_template(
        "patient_view.html", patient=patient, history=history, bills=bills
    )


@app.route("/patients/add", methods=["GET", "POST"])
@login_required
@roles_required("admin", "receptionist")
def add_patient():
    if request.method == "GET":
        return render_template("patient_form.html", patient=None)

    validate_csrf()
    form = request.form

    errors = []
    if not form.get("name", "").strip():
        errors.append("Name is required.")
    if not is_valid_phone(form.get("phone", "")):
        errors.append("Please provide a valid phone number.")
    if not is_valid_email(form.get("email", "")):
        errors.append("Please provide a valid email address.")
    if not form.get("gender"):
        errors.append("Gender is required.")
    if not form.get("address", "").strip():
        errors.append("Address is required.")

    if errors:
        for e in errors:
            flash(e, "danger")
        return render_template("patient_form.html", patient=form), 400

    conn = get_db_connection()
    mrn = generate_mrn(conn)
    age = calculate_age(form.get("dob")) or (int(form["age"]) if form.get("age") else None)

    photo_file = request.files.get("photo")
    photo_name = save_upload(photo_file, app.config["UPLOAD_FOLDER"], f"patient_{mrn}")

    conn.execute("""
        INSERT INTO patients
            (mrn, name, dob, age, gender, blood_group, phone, email, address,
             emergency_contact_name, emergency_contact_phone, disease,
             medical_history, allergies, photo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        mrn, form["name"].strip(), form.get("dob") or None, age,
        form["gender"], form.get("blood_group") or None, form["phone"].strip(),
        form.get("email", "").strip() or None, form["address"].strip(),
        form.get("emergency_contact_name", "").strip() or None,
        form.get("emergency_contact_phone", "").strip() or None,
        form.get("disease", "").strip() or None,
        form.get("medical_history", "").strip() or None,
        form.get("allergies", "").strip() or None,
        photo_name,
    ))
    conn.commit()
    log_action(conn, "PATIENT_ADD", f"Added patient {mrn} - {form['name']}")
    conn.close()

    flash(f"Patient registered successfully with MRN {mrn}.", "success")
    return redirect(url_for("patients"))


@app.route("/patients/edit/<int:id>", methods=["GET", "POST"])
@login_required
@roles_required("admin", "receptionist")
def edit_patient(id):
    conn = get_db_connection()
    patient = conn.execute("SELECT * FROM patients WHERE id = ?", (id,)).fetchone()
    if patient is None:
        conn.close()
        abort(404)

    if request.method == "GET":
        conn.close()
        return render_template("patient_form.html", patient=patient)

    validate_csrf()
    form = request.form

    errors = []
    if not form.get("name", "").strip():
        errors.append("Name is required.")
    if not is_valid_phone(form.get("phone", "")):
        errors.append("Please provide a valid phone number.")
    if not is_valid_email(form.get("email", "")):
        errors.append("Please provide a valid email address.")

    if errors:
        for e in errors:
            flash(e, "danger")
        conn.close()
        return render_template("patient_form.html", patient={**dict(patient), **form}), 400

    age = calculate_age(form.get("dob")) or (int(form["age"]) if form.get("age") else None)

    photo_name = patient["photo"]
    photo_file = request.files.get("photo")
    new_photo = save_upload(photo_file, app.config["UPLOAD_FOLDER"], f"patient_{patient['mrn']}")
    if new_photo:
        photo_name = new_photo

    conn.execute("""
        UPDATE patients SET
            name=?, dob=?, age=?, gender=?, blood_group=?, phone=?, email=?,
            address=?, emergency_contact_name=?, emergency_contact_phone=?,
            disease=?, medical_history=?, allergies=?, photo=?, status=?,
            updated_at=datetime('now')
        WHERE id=?
    """, (
        form["name"].strip(), form.get("dob") or None, age, form["gender"],
        form.get("blood_group") or None, form["phone"].strip(),
        form.get("email", "").strip() or None, form["address"].strip(),
        form.get("emergency_contact_name", "").strip() or None,
        form.get("emergency_contact_phone", "").strip() or None,
        form.get("disease", "").strip() or None,
        form.get("medical_history", "").strip() or None,
        form.get("allergies", "").strip() or None,
        photo_name, form.get("status", "Active"), id,
    ))
    conn.commit()
    log_action(conn, "PATIENT_UPDATE", f"Updated patient #{id}")
    conn.close()

    flash("Patient record updated successfully.", "success")
    return redirect(url_for("patients"))


@app.route("/patients/delete/<int:id>", methods=["POST"])
@login_required
@roles_required("admin")
def delete_patient(id):
    validate_csrf()
    conn = get_db_connection()
    conn.execute("DELETE FROM patients WHERE id=?", (id,))
    conn.commit()
    log_action(conn, "PATIENT_DELETE", f"Deleted patient #{id}")
    conn.close()
    flash("Patient record deleted.", "info")
    return redirect(url_for("patients"))


# =====================================================================
# DOCTOR MANAGEMENT
# =====================================================================
@app.route("/doctors")
@login_required
def doctors():
    keyword = request.args.get("keyword", "").strip()

    conn = get_db_connection()
    query = """
        SELECT d.*, dep.name AS department_name
        FROM doctors d
        LEFT JOIN departments dep ON d.department_id = dep.id
        WHERE 1=1
    """
    params = []
    if keyword:
        query += " AND (d.name LIKE ? OR d.specialization LIKE ? OR dep.name LIKE ?)"
        like = f"%{keyword}%"
        params += [like, like, like]
    query += " ORDER BY d.id DESC"

    doctor_rows = conn.execute(query, params).fetchall()
    conn.close()

    return render_template("doctors_list.html", doctors=doctor_rows, keyword=keyword)


@app.route("/doctors/add", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def add_doctor():
    conn = get_db_connection()
    departments = conn.execute("SELECT * FROM departments ORDER BY name").fetchall()

    if request.method == "GET":
        conn.close()
        return render_template("doctor_form.html", doctor=None, departments=departments)

    validate_csrf()
    form = request.form

    errors = []
    if not form.get("name", "").strip():
        errors.append("Name is required.")
    if not is_valid_phone(form.get("phone", "")):
        errors.append("Please provide a valid phone number.")
    if not is_valid_email(form.get("email", "")) or not form.get("email", "").strip():
        errors.append("A valid email address is required.")
    if not form.get("specialization", "").strip():
        errors.append("Specialization is required.")

    if errors:
        for e in errors:
            flash(e, "danger")
        conn.close()
        return render_template("doctor_form.html", doctor=form, departments=departments), 400

    photo_file = request.files.get("photo")
    photo_name = save_upload(photo_file, app.config["UPLOAD_FOLDER"], "doctor")

    try:
        conn.execute("""
            INSERT INTO doctors
                (name, gender, department_id, specialization, qualification,
                 experience, phone, email, consultation_fee, availability, photo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            form["name"].strip(), form.get("gender") or None,
            form.get("department_id") or None, form["specialization"].strip(),
            form.get("qualification", "").strip() or None,
            int(form.get("experience") or 0), form["phone"].strip(),
            form["email"].strip(), float(form.get("consultation_fee") or 0),
            form.get("availability", "").strip() or None, photo_name,
        ))
        conn.commit()
        log_action(conn, "DOCTOR_ADD", f"Added doctor {form['name']}")
        flash("Doctor added successfully.", "success")
    except Exception as exc:
        flash(f"Could not add doctor: {exc}", "danger")
    finally:
        conn.close()

    return redirect(url_for("doctors"))


@app.route("/doctors/edit/<int:id>", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def edit_doctor(id):
    conn = get_db_connection()
    doctor = conn.execute("SELECT * FROM doctors WHERE id=?", (id,)).fetchone()
    departments = conn.execute("SELECT * FROM departments ORDER BY name").fetchall()

    if doctor is None:
        conn.close()
        abort(404)

    if request.method == "GET":
        conn.close()
        return render_template("doctor_form.html", doctor=doctor, departments=departments)

    validate_csrf()
    form = request.form

    photo_name = doctor["photo"]
    new_photo = save_upload(request.files.get("photo"), app.config["UPLOAD_FOLDER"], "doctor")
    if new_photo:
        photo_name = new_photo

    conn.execute("""
        UPDATE doctors SET
            name=?, gender=?, department_id=?, specialization=?, qualification=?,
            experience=?, phone=?, email=?, consultation_fee=?, availability=?,
            photo=?, status=?
        WHERE id=?
    """, (
        form["name"].strip(), form.get("gender") or None,
        form.get("department_id") or None, form["specialization"].strip(),
        form.get("qualification", "").strip() or None,
        int(form.get("experience") or 0), form["phone"].strip(),
        form["email"].strip(), float(form.get("consultation_fee") or 0),
        form.get("availability", "").strip() or None, photo_name,
        form.get("status", "Active"), id,
    ))
    conn.commit()
    log_action(conn, "DOCTOR_UPDATE", f"Updated doctor #{id}")
    conn.close()

    flash("Doctor details updated successfully.", "success")
    return redirect(url_for("doctors"))


@app.route("/doctors/delete/<int:id>", methods=["POST"])
@login_required
@roles_required("admin")
def delete_doctor(id):
    validate_csrf()
    conn = get_db_connection()
    conn.execute("DELETE FROM doctors WHERE id=?", (id,))
    conn.commit()
    log_action(conn, "DOCTOR_DELETE", f"Deleted doctor #{id}")
    conn.close()
    flash("Doctor record deleted.", "info")
    return redirect(url_for("doctors"))


# =====================================================================
# APPOINTMENT MANAGEMENT
# =====================================================================
@app.route("/appointments")
@login_required
def appointments():
    status_filter = request.args.get("status", "").strip()
    date_filter = request.args.get("date", "").strip()

    conn = get_db_connection()
    query = """
        SELECT a.id, p.id AS patient_id, p.name AS patient_name,
               d.id AS doctor_id, d.name AS doctor_name,
               a.appointment_date, a.appointment_time, a.reason, a.status
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN doctors d ON a.doctor_id = d.id
        WHERE 1=1
    """
    params = []

    # Doctors only see their own appointments
    if session.get("role") == "doctor" and session.get("doctor_id"):
        query += " AND a.doctor_id = ?"
        params.append(session["doctor_id"])

    if status_filter:
        query += " AND a.status = ?"
        params.append(status_filter)
    if date_filter:
        query += " AND a.appointment_date = ?"
        params.append(date_filter)

    query += " ORDER BY a.appointment_date DESC, a.appointment_time DESC"

    appointment_rows = conn.execute(query, params).fetchall()
    conn.close()

    return render_template(
        "appointments_list.html",
        appointments=appointment_rows,
        status_filter=status_filter,
        date_filter=date_filter,
    )


@app.route("/appointments/book", methods=["GET", "POST"])
@login_required
@roles_required("admin", "receptionist")
def book_appointment():
    conn = get_db_connection()
    patient_rows = conn.execute("SELECT * FROM patients ORDER BY name").fetchall()
    doctor_rows = conn.execute(
        "SELECT * FROM doctors WHERE status='Active' ORDER BY name"
    ).fetchall()

    if request.method == "GET":
        conn.close()
        return render_template(
            "appointment_form.html", appointment=None,
            patients=patient_rows, doctors=doctor_rows
        )

    validate_csrf()
    form = request.form

    errors = []
    if not form.get("patient_id"):
        errors.append("Please select a patient.")
    if not form.get("doctor_id"):
        errors.append("Please select a doctor.")
    if not form.get("appointment_date"):
        errors.append("Please choose an appointment date.")
    if not form.get("appointment_time"):
        errors.append("Please choose an appointment time.")

    if not errors and form.get("appointment_date") < datetime.now().strftime("%Y-%m-%d"):
        errors.append("Appointment date cannot be in the past.")

    # Prevent double-booking the same doctor at the same date/time
    if not errors:
        clash = conn.execute("""
            SELECT 1 FROM appointments
            WHERE doctor_id = ? AND appointment_date = ? AND appointment_time = ?
              AND status = 'Scheduled'
        """, (form["doctor_id"], form["appointment_date"], form["appointment_time"])).fetchone()
        if clash:
            errors.append("This doctor already has an appointment at the selected date/time.")

    if errors:
        for e in errors:
            flash(e, "danger")
        conn.close()
        return render_template(
            "appointment_form.html", appointment=form,
            patients=patient_rows, doctors=doctor_rows
        ), 400

    conn.execute("""
        INSERT INTO appointments
            (patient_id, doctor_id, appointment_date, appointment_time, reason, status)
        VALUES (?, ?, ?, ?, ?, 'Scheduled')
    """, (
        form["patient_id"], form["doctor_id"], form["appointment_date"],
        form["appointment_time"], form.get("reason", "").strip() or None,
    ))
    conn.commit()
    log_action(conn, "APPOINTMENT_BOOK",
               f"Booked appointment for patient #{form['patient_id']} with doctor #{form['doctor_id']}")
    conn.close()

    flash("Appointment booked successfully.", "success")
    return redirect(url_for("appointments"))


@app.route("/appointments/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_appointment(id):
    conn = get_db_connection()
    appointment = conn.execute("SELECT * FROM appointments WHERE id=?", (id,)).fetchone()
    if appointment is None:
        conn.close()
        abort(404)

    # Doctors can only edit their own appointments (to add diagnosis/notes)
    if session.get("role") == "doctor" and appointment["doctor_id"] != session.get("doctor_id"):
        conn.close()
        abort(403)

    patient_rows = conn.execute("SELECT * FROM patients ORDER BY name").fetchall()
    doctor_rows = conn.execute("SELECT * FROM doctors ORDER BY name").fetchall()

    if request.method == "GET":
        conn.close()
        return render_template(
            "appointment_form.html", appointment=appointment,
            patients=patient_rows, doctors=doctor_rows
        )

    validate_csrf()
    form = request.form

    conn.execute("""
        UPDATE appointments SET
            patient_id=?, doctor_id=?, appointment_date=?, appointment_time=?,
            reason=?, status=?, diagnosis=?, prescription=?, notes=?,
            updated_at=datetime('now')
        WHERE id=?
    """, (
        form.get("patient_id", appointment["patient_id"]),
        form.get("doctor_id", appointment["doctor_id"]),
        form.get("appointment_date", appointment["appointment_date"]),
        form.get("appointment_time", appointment["appointment_time"]),
        form.get("reason", "").strip() or None,
        form.get("status", appointment["status"]),
        form.get("diagnosis", "").strip() or None,
        form.get("prescription", "").strip() or None,
        form.get("notes", "").strip() or None,
        id,
    ))
    conn.commit()
    log_action(conn, "APPOINTMENT_UPDATE", f"Updated appointment #{id}")
    conn.close()

    flash("Appointment updated successfully.", "success")
    return redirect(url_for("appointments"))


@app.route("/appointments/delete/<int:id>", methods=["POST"])
@login_required
@roles_required("admin", "receptionist")
def delete_appointment(id):
    validate_csrf()
    conn = get_db_connection()
    conn.execute("DELETE FROM appointments WHERE id=?", (id,))
    conn.commit()
    log_action(conn, "APPOINTMENT_DELETE", f"Deleted appointment #{id}")
    conn.close()
    flash("Appointment cancelled and removed.", "info")
    return redirect(url_for("appointments"))


# =====================================================================
# BILLING MANAGEMENT
# =====================================================================
@app.route("/billing", methods=["GET", "POST"])
@login_required
@roles_required("admin", "receptionist")
def billing():
    conn = get_db_connection()
    patient_rows = conn.execute("SELECT id, name, mrn FROM patients ORDER BY name").fetchall()

    if request.method == "GET":
        conn.close()
        return render_template("billing_generate.html", patients=patient_rows)

    validate_csrf()
    form = request.form

    try:
        consultation_fee = float(form.get("consultation_fee") or 0)
        medicine_charge = float(form.get("medicine_charge") or 0)
        lab_charge = float(form.get("lab_charge") or 0)
        room_charge = float(form.get("room_charge") or 0)
        other_charge = float(form.get("other_charge") or 0)
        discount = float(form.get("discount") or 0)
        tax_percent = float(form.get("tax_percent") or 0)
    except ValueError:
        flash("Please enter valid numeric amounts.", "danger")
        conn.close()
        return redirect(url_for("billing"))

    if not form.get("patient_id"):
        flash("Please select a patient.", "danger")
        conn.close()
        return redirect(url_for("billing"))

    subtotal = (consultation_fee + medicine_charge + lab_charge
                + room_charge + other_charge - discount)
    tax_amount = subtotal * (tax_percent / 100)
    total = round(subtotal + tax_amount, 2)

    invoice_no = generate_invoice_no(conn)

    cursor = conn.execute("""
        INSERT INTO bills
            (invoice_no, patient_id, consultation_fee, medicine_charge,
             lab_charge, room_charge, other_charge, discount, tax_percent,
             total_amount, payment_status, payment_method)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        invoice_no, form["patient_id"], consultation_fee, medicine_charge,
        lab_charge, room_charge, other_charge, discount, tax_percent,
        total, form.get("payment_status", "Unpaid"),
        form.get("payment_method", "").strip() or None,
    ))
    conn.commit()
    bill_id = cursor.lastrowid
    log_action(conn, "BILL_CREATE", f"Generated invoice {invoice_no}")
    conn.close()

    flash(f"Invoice {invoice_no} generated successfully.", "success")
    return redirect(url_for("view_bill", id=bill_id))


@app.route("/bills")
@login_required
@roles_required("admin", "receptionist")
def bills():
    status_filter = request.args.get("status", "").strip()

    conn = get_db_connection()
    query = """
        SELECT b.id, b.invoice_no, p.name AS patient_name, p.mrn,
               b.total_amount, b.payment_status, b.created_at
        FROM bills b
        JOIN patients p ON b.patient_id = p.id
        WHERE 1=1
    """
    params = []
    if status_filter:
        query += " AND b.payment_status = ?"
        params.append(status_filter)
    query += " ORDER BY b.id DESC"

    bill_rows = conn.execute(query, params).fetchall()
    conn.close()

    return render_template("bills_list.html", bills=bill_rows, status_filter=status_filter)


@app.route("/bills/<int:id>")
@login_required
@roles_required("admin", "receptionist")
def view_bill(id):
    conn = get_db_connection()
    bill = conn.execute("""
        SELECT b.*, p.name AS patient_name, p.mrn, p.age, p.gender,
               p.phone, p.address
        FROM bills b
        JOIN patients p ON b.patient_id = p.id
        WHERE b.id = ?
    """, (id,)).fetchone()
    conn.close()

    if bill is None:
        abort(404)

    return render_template("invoice.html", bill=bill)


@app.route("/bills/delete/<int:id>", methods=["POST"])
@login_required
@roles_required("admin")
def delete_bill(id):
    validate_csrf()
    conn = get_db_connection()
    conn.execute("DELETE FROM bills WHERE id=?", (id,))
    conn.commit()
    log_action(conn, "BILL_DELETE", f"Deleted bill #{id}")
    conn.close()
    flash("Invoice deleted.", "info")
    return redirect(url_for("bills"))


@app.route("/bills/mark_paid/<int:id>", methods=["POST"])
@login_required
@roles_required("admin", "receptionist")
def mark_bill_paid(id):
    validate_csrf()
    conn = get_db_connection()
    conn.execute(
        "UPDATE bills SET payment_status='Paid', payment_method=? WHERE id=?",
        (request.form.get("payment_method", "Cash"), id),
    )
    conn.commit()
    log_action(conn, "BILL_PAID", f"Marked bill #{id} as paid")
    conn.close()
    flash("Invoice marked as paid.", "success")
    return redirect(url_for("view_bill", id=id))


# =====================================================================
# STAFF / USER MANAGEMENT (admin only)
# =====================================================================
@app.route("/users")
@login_required
@roles_required("admin")
def users():
    conn = get_db_connection()
    user_rows = conn.execute(
        "SELECT * FROM users ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return render_template("users_list.html", users=user_rows)


@app.route("/users/add", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def add_user():
    conn = get_db_connection()
    doctor_rows = conn.execute("SELECT * FROM doctors ORDER BY name").fetchall()

    if request.method == "GET":
        conn.close()
        return render_template("user_form.html", staff=None, doctors=doctor_rows)

    validate_csrf()
    form = request.form

    errors = []
    if not form.get("username", "").strip():
        errors.append("Username is required.")
    if not form.get("full_name", "").strip():
        errors.append("Full name is required.")
    if len(form.get("password", "")) < 8:
        errors.append("Password must be at least 8 characters long.")
    if form.get("role") not in ("admin", "doctor", "receptionist"):
        errors.append("Please select a valid role.")

    if not errors:
        existing = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (form["username"].strip(),)
        ).fetchone()
        if existing:
            errors.append("That username is already taken.")

    if errors:
        for e in errors:
            flash(e, "danger")
        conn.close()
        return render_template("user_form.html", staff=form, doctors=doctor_rows), 400

    conn.execute("""
        INSERT INTO users (username, password_hash, full_name, role, email, phone, doctor_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        form["username"].strip(), generate_password_hash(form["password"]),
        form["full_name"].strip(), form["role"], form.get("email", "").strip() or None,
        form.get("phone", "").strip() or None,
        form.get("doctor_id") or None if form["role"] == "doctor" else None,
    ))
    conn.commit()
    log_action(conn, "USER_ADD", f"Added staff account {form['username']} ({form['role']})")
    conn.close()

    flash("Staff account created successfully.", "success")
    return redirect(url_for("users"))


@app.route("/users/edit/<int:id>", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def edit_user(id):
    conn = get_db_connection()
    staff = conn.execute("SELECT * FROM users WHERE id=?", (id,)).fetchone()
    doctor_rows = conn.execute("SELECT * FROM doctors ORDER BY name").fetchall()

    if staff is None:
        conn.close()
        abort(404)

    if request.method == "GET":
        conn.close()
        return render_template("user_form.html", staff=staff, doctors=doctor_rows)

    validate_csrf()
    form = request.form

    if form.get("password"):
        if len(form["password"]) < 8:
            flash("Password must be at least 8 characters long.", "danger")
            conn.close()
            return render_template("user_form.html", staff=staff, doctors=doctor_rows), 400
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (generate_password_hash(form["password"]), id),
        )

    conn.execute("""
        UPDATE users SET
            full_name=?, role=?, email=?, phone=?, doctor_id=?, is_active=?
        WHERE id=?
    """, (
        form["full_name"].strip(), form["role"], form.get("email", "").strip() or None,
        form.get("phone", "").strip() or None,
        form.get("doctor_id") or None if form["role"] == "doctor" else None,
        1 if form.get("is_active") else 0,
        id,
    ))
    conn.commit()
    log_action(conn, "USER_UPDATE", f"Updated staff account #{id}")
    conn.close()

    flash("Staff account updated successfully.", "success")
    return redirect(url_for("users"))


@app.route("/users/delete/<int:id>", methods=["POST"])
@login_required
@roles_required("admin")
def delete_user(id):
    validate_csrf()
    if id == session.get("user_id"):
        flash("You cannot delete your own account while logged in.", "danger")
        return redirect(url_for("users"))

    conn = get_db_connection()
    conn.execute("DELETE FROM users WHERE id=?", (id,))
    conn.commit()
    log_action(conn, "USER_DELETE", f"Deleted staff account #{id}")
    conn.close()
    flash("Staff account deleted.", "info")
    return redirect(url_for("users"))


# =====================================================================
# AUDIT LOG (admin only)
# =====================================================================
@app.route("/audit-log")
@login_required
@roles_required("admin")
def audit_log_view():
    conn = get_db_connection()
    logs = conn.execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT 200"
    ).fetchall()
    conn.close()
    return render_template("audit_log.html", logs=logs)


# =====================================================================
# REST API (read endpoints are public-ish for integration demos;
# all mutating endpoints require an authenticated session)
# =====================================================================
@app.route("/api")
def api_home():
    return jsonify({
        "message": f"{HOSPITAL_NAME} Management System API",
        "version": "2.0",
        "endpoints": [
            "/api/patients", "/api/patient/<id>", "/api/doctors",
            "/api/appointments", "/api/bills",
        ],
    })


@app.route("/api/patients")
@login_required
def api_patients():
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM patients").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/patient/<int:id>")
@login_required
def api_patient(id):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM patients WHERE id=?", (id,)).fetchone()
    conn.close()
    if row:
        return jsonify(dict(row))
    return jsonify({"message": "Patient not found"}), 404


@app.route("/api/patient", methods=["POST"])
@login_required
@roles_required("admin", "receptionist")
def api_add_patient():
    data = request.get_json(silent=True) or {}
    required = ["name", "age", "gender", "phone", "address"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"message": f"Missing fields: {', '.join(missing)}"}), 400

    conn = get_db_connection()
    mrn = generate_mrn(conn)
    conn.execute("""
        INSERT INTO patients (mrn, name, age, gender, phone, address, disease)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        mrn, data["name"], data["age"], data["gender"], data["phone"],
        data["address"], data.get("disease"),
    ))
    conn.commit()
    conn.close()
    return jsonify({"message": "Patient added successfully", "mrn": mrn}), 201


@app.route("/api/patient/<int:id>", methods=["PUT"])
@login_required
@roles_required("admin", "receptionist")
def api_update_patient(id):
    data = request.get_json(silent=True) or {}
    conn = get_db_connection()
    existing = conn.execute("SELECT * FROM patients WHERE id=?", (id,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({"message": "Patient not found"}), 404

    conn.execute("""
        UPDATE patients SET name=?, age=?, gender=?, phone=?, address=?, disease=?,
            updated_at=datetime('now')
        WHERE id=?
    """, (
        data.get("name", existing["name"]), data.get("age", existing["age"]),
        data.get("gender", existing["gender"]), data.get("phone", existing["phone"]),
        data.get("address", existing["address"]), data.get("disease", existing["disease"]),
        id,
    ))
    conn.commit()
    conn.close()
    return jsonify({"message": "Patient updated successfully"})


@app.route("/api/patient/<int:id>", methods=["DELETE"])
@login_required
@roles_required("admin")
def api_delete_patient(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM patients WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Patient deleted successfully"})


@app.route("/api/doctors")
@login_required
def api_doctors():
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM doctors").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/appointments")
@login_required
def api_appointments():
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT a.id, p.name AS patient, d.name AS doctor,
               a.appointment_date, a.appointment_time, a.status
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN doctors d ON a.doctor_id = d.id
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/bills")
@login_required
@roles_required("admin", "receptionist")
def api_bills():
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT b.id, b.invoice_no, p.name, b.total_amount, b.payment_status
        FROM bills b
        JOIN patients p ON b.patient_id = p.id
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# =====================================================================
# ERROR HANDLERS
# =====================================================================
@app.errorhandler(400)
def bad_request(e):
    return render_template("error.html", code=400, message=str(e.description or "Bad request.")), 400


@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, message="You don't have permission to view this page."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="The page you're looking for doesn't exist."), 404


@app.errorhandler(413)
def too_large(e):
    return render_template("error.html", code=413, message="The uploaded file is too large (max 4 MB)."), 413


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, message="Something went wrong on our end."), 500


if __name__ == "__main__":
    if not os.path.exists("hospital.db"):
        print("No database found - run `python database.py` first.")
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", host="127.0.0.1", port=5000)
