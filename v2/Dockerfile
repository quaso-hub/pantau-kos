FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── v2 Clean Architecture modules ─────────────────────────────────────────────
COPY v2/main.py .
COPY v2/domain/       domain/
COPY v2/services/     services/
COPY v2/adapters/     adapters/
COPY v2/infrastructure/ infrastructure/

# ── Preserved from v1 ─────────────────────────────────────────────────────────
COPY web/             web/

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "120", "main:flask_app"]
