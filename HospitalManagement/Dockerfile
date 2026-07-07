FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

RUN python database.py

EXPOSE 5000

ENV FLASK_DEBUG=0

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "3", "app:app"]
