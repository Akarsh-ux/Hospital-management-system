# 🏥 Hospital Management System (Enhanced / Commercial Edition)

A production-ready Hospital Management System built with **Flask** and
**SQLite**, redesigned for real clinic/hospital use with role-based
access control, secure authentication, patient medical records,
appointment scheduling with conflict detection, invoicing, an audit
trail, and a modern responsive UI.

---

## ✨ What's New in This Enhanced Version

| Area | Before | Now |
|---|---|---|
| Passwords | Hardcoded `admin`/`admin123`, plaintext | Hashed (Werkzeug PBKDF2), configurable admin account |
| Access control | Single shared login | **Role-based**: Admin / Doctor / Receptionist |
| Security | No CSRF protection, no security headers | CSRF tokens on all forms, security headers, session timeout |
| Patients | Name, age, gender, phone, address, disease | + MRN, DOB, blood group, email, emergency contact, medical history, allergies, photo, active/inactive status |
| Doctors | Name, specialization, experience, phone, email | + Department, qualification, consultation fee, availability, photo, active/inactive status |
| Appointments | Basic booking | + Double-booking prevention, past-date validation, diagnosis/prescription/notes, status workflow |
| Billing | Basic charges | + Auto invoice numbers, discounts & tax, payment status/method, printable invoice |
| Dashboard | Static counters | + Revenue this month, pending bills, 7-day appointment trend chart, department distribution chart |
| Staff management | None | Admin can create/manage staff accounts |
| Auditing | None | Full audit log of logins, creates, updates and deletes |
| UI | Plain HTML tables | Responsive Bootstrap 5 UI with sidebar navigation, search & pagination |
| Deployment | `python app.py` only | + Dockerfile, docker-compose, gunicorn-ready |

---

## 🔐 Roles & Permissions

| Feature | Admin | Receptionist | Doctor |
|---|:---:|:---:|:---:|
| Dashboard | ✅ | ✅ | ✅ |
| Register / edit patients | ✅ | ✅ | View only |
| Manage doctors | ✅ | View only | View only |
| Book / manage appointments | ✅ | ✅ | View own + add clinical notes |
| Billing & invoices | ✅ | ✅ | ❌ |
| Staff accounts | ✅ | ❌ | ❌ |
| Audit log | ✅ | ❌ | ❌ |

---

## 🛠 Technology Stack

- Python 3 / Flask 3
- SQLite (zero-config, file based)
- Jinja2 templates
- Bootstrap 5 + Bootstrap Icons (CDN)
- Chart.js (CDN) for dashboard analytics
- Werkzeug password hashing

---

## 📁 Project Structure

```
HospitalManagement/
├── app.py                  # Application routes & business logic
├── database.py              # Schema creation + seed data
├── utils.py                  # Auth decorators, validators, helpers
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── run_hospital.bat          # Windows launcher
├── run_hospital.sh           # macOS/Linux launcher
├── README.md
│
├── static/
│   ├── style.css
│   ├── logo.png
│   ├── js/main.js
│   └── uploads/               # Patient & doctor photos
│
└── templates/
    ├── base.html
    ├── login.html
    ├── dashboard.html
    ├── patients_list.html / patient_form.html / patient_view.html
    ├── doctors_list.html / doctor_form.html
    ├── appointments_list.html / appointment_form.html
    ├── billing_generate.html / bills_list.html / invoice.html
    ├── users_list.html / user_form.html
    ├── profile.html / audit_log.html / error.html
```

---

## ⚙ Installation (Local)

```bash
# 1. Clone / unzip the project
cd HospitalManagement

# 2. (Recommended) create a virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Initialize the database (creates hospital.db + default admin)
python database.py

# 5. Run the app
python app.py
```

Then open **http://127.0.0.1:5000** in your browser.

### Default login

```
Username: admin
Password: Admin@123
```

**⚠️ Change this password immediately** via *My Profile → Change Password*
after your first login, and create named staff accounts for real use
(*Staff Accounts → Add Staff Account*).

---

## 🔑 Environment Variables (Production)

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Flask session signing key — **set a long random value in production** | random per-run |
| `HOSPITAL_NAME` | Branding shown across the UI | `CareWell Hospital` |
| `FLASK_DEBUG` | Enable Flask debug mode (never `1` in production) | `0` |

```bash
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export HOSPITAL_NAME="My Hospital"
```

---

## 🐳 Docker Deployment

```bash
docker compose up --build -d
```

The app will be available on **http://localhost:5000**, backed by a
persisted `hospital.db` file and `static/uploads` folder on the host.

For a real production deployment, put this behind a reverse proxy
(Nginx/Caddy) with HTTPS termination, and swap SQLite for PostgreSQL
if you expect heavy concurrent write load.

---

## 🗄 Database Schema (Summary)

- **users** – staff accounts, hashed passwords, role, linked doctor profile
- **departments** – hospital departments (Cardiology, Pediatrics, etc.)
- **doctors** – profile, department, qualification, consultation fee, availability
- **patients** – MRN, demographics, medical history, allergies, emergency contact
- **appointments** – scheduling, status workflow, diagnosis/prescription/notes
- **bills** – itemized invoice, discount/tax, payment status & method
- **audit_log** – who did what, when

---

## 🌐 REST API

All endpoints (except `/api`) require an authenticated session.

| Method | Endpoint | Notes |
|---|---|---|
| GET | `/api` | API info |
| GET | `/api/patients` | List patients |
| GET | `/api/patient/<id>` | Single patient |
| POST | `/api/patient` | Add patient (admin/receptionist) |
| PUT | `/api/patient/<id>` | Update patient (admin/receptionist) |
| DELETE | `/api/patient/<id>` | Delete patient (admin) |
| GET | `/api/doctors` | List doctors |
| GET | `/api/appointments` | List appointments |
| GET | `/api/bills` | List bills (admin/receptionist) |

---

## 🚀 Suggested Next Steps for a Full Commercial Rollout

- Move from SQLite to PostgreSQL/MySQL for multi-user concurrency at scale
- Add email/SMS appointment reminders (e.g. via SendGrid/Twilio)
- Add real PDF generation for invoices (e.g. WeasyPrint/ReportLab) instead of browser print
- Add lab/pharmacy inventory modules
- Add two-factor authentication for admin accounts
- Add automated backups of `hospital.db`
- Add HIPAA/GDPR-oriented data retention & encryption-at-rest policies for real patient data

---

## 📄 License

Provided for educational and internal deployment purposes. Review and
harden security (secrets management, HTTPS, backups, compliance) before
using with real patient data in a production hospital environment.
