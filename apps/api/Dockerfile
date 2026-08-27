# Avocado API — FastAPI on Railway
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Tesseract powers OCR for scanned textbook PDFs (app/doc_text.py). PyMuPDF
# renders the pages, so poppler is not needed. Pango/Cairo/GDK-Pixbuf +
# DejaVu fonts let WeasyPrint render DI packets to PDF (app/export_html.py).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
        libcairo2 libffi8 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Railway injects PORT. Optionally seed synthetic demo data on first boot
# when SEED_ON_START=true (safe: seed is a no-op if data already exists).
CMD ["sh", "-c", "if [ \"$SEED_ON_START\" = \"true\" ]; then python -m app.seed; fi; uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
