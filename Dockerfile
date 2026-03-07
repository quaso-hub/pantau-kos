FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
COPY domain/ domain/
COPY services/ services/
COPY adapters/ adapters/
COPY infrastructure/ infrastructure/
COPY web/ web/
# gunicorn serves flask_app from main.py; --timeout 120 for long analysis requests
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "120", "main:flask_app"]
