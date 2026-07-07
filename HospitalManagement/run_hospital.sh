#!/usr/bin/env bash
set -e

echo "================================================"
echo "  Hospital Management System - Starting Up"
echo "================================================"

if [ ! -f "hospital.db" ]; then
    echo "Creating database..."
    python3 database.py
fi

echo "Starting Flask application..."
python3 app.py
