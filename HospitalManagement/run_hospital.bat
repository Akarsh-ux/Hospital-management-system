@echo off
echo ================================================
echo   Hospital Management System - Starting Up
echo ================================================

if not exist hospital.db (
    echo Creating database...
    python database.py
)

echo Starting Flask application...
python app.py

pause
