# Avocado API — FastAPI on Railway
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Railway injects PORT. Optionally seed synthetic demo data on first boot
# when SEED_ON_START=true (safe: seed is a no-op if data already exists).
CMD ["sh", "-c", "if [ \"$SEED_ON_START\" = \"true\" ]; then python -m app.seed; fi; uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
