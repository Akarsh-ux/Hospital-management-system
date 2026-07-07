"""
================================================================
 Hospital Management System - Shared Utilities
================================================================
Database connection helper, authentication / authorization
decorators, ID generators, small validation helpers and the
audit-log writer used across the application.
================================================================
"""

import os
import re
import sqlite3
from datetime import datetime, date
from functools import wraps

from flask import session, redirect, url_for, flash, request, abort

DB_NAME = "hospital.db"

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


# -----------------------------------------------------------
# Database
# -----------------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# -----------------------------------------------------------
# Auth decorators
# -----------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def roles_required(*roles):
    """Restrict a view to one or more roles, e.g. @roles_required('admin')"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            if session.get("role") not in roles:
                flash("You do not have permission to access that page.", "danger")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# -----------------------------------------------------------
# CSRF protection (lightweight, dependency-free)
# -----------------------------------------------------------
def validate_csrf():
    """Aborts the request with 400 if the CSRF token is missing/invalid."""
    token = session.get("csrf_token")
    submitted = request.form.get("csrf_token")
    if not token or not submitted or token != submitted:
        abort(400, description="Invalid or missing CSRF token.")


# -----------------------------------------------------------
# ID / Number generators
# -----------------------------------------------------------
def generate_mrn(conn):
    """Generate a sequential, human readable Medical Record Number."""
    row = conn.execute("SELECT COUNT(*) FROM patients").fetchone()
    next_id = (row[0] or 0) + 1
    year = datetime.now().strftime("%y")
    candidate = f"MRN-{year}-{next_id:05d}"

    # Guard against collisions if records were ever deleted
    while conn.execute(
        "SELECT 1 FROM patients WHERE mrn = ?", (candidate,)
    ).fetchone():
        next_id += 1
        candidate = f"MRN-{year}-{next_id:05d}"

    return candidate


def generate_invoice_no(conn):
    row = conn.execute("SELECT COUNT(*) FROM bills").fetchone()
    next_id = (row[0] or 0) + 1
    year = datetime.now().strftime("%Y")
    candidate = f"INV-{year}-{next_id:06d}"

    while conn.execute(
        "SELECT 1 FROM bills WHERE invoice_no = ?", (candidate,)
    ).fetchone():
        next_id += 1
        candidate = f"INV-{year}-{next_id:06d}"

    return candidate


# -----------------------------------------------------------
# Validation helpers
# -----------------------------------------------------------
PHONE_RE = re.compile(r"^[0-9+\-\s()]{7,15}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_phone(value):
    return bool(value) and bool(PHONE_RE.match(value.strip()))


def is_valid_email(value):
    if not value:
        return True  # email is optional in most forms
    return bool(EMAIL_RE.match(value.strip()))


def calculate_age(dob_str):
    """Calculate age in whole years from an ISO date string (YYYY-MM-DD)."""
    if not dob_str:
        return None
    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
    except ValueError:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS
    )


def save_upload(file_storage, upload_folder, prefix):
    """Safely persist an uploaded image and return its stored filename."""
    from werkzeug.utils import secure_filename

    if not file_storage or file_storage.filename == "":
        return None

    if not allowed_file(file_storage.filename):
        return None

    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    filename = secure_filename(f"{prefix}_{int(datetime.now().timestamp())}.{ext}")
    os.makedirs(upload_folder, exist_ok=True)
    file_storage.save(os.path.join(upload_folder, filename))
    return filename


# -----------------------------------------------------------
# Audit logging
# -----------------------------------------------------------
def log_action(conn, action, details=""):
    username = session.get("username", "system")
    conn.execute(
        "INSERT INTO audit_log (username, action, details) VALUES (?, ?, ?)",
        (username, action, details),
    )
    conn.commit()
