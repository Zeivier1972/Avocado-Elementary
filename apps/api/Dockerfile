# Avocado API — FastAPI on Railway
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Tesseract powers OCR for scanned textbook PDFs (app/doc_text.py). PyMuPDF
# renders the pages, so poppler is not needed.
# Chromium renders DI packets to real PDFs (app/export_html.py -> html_to_pdf);
# the font packages give it decent glyphs + color emoji in the printed PDF.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        chromium \
        fonts-liberation \
        fonts-dejavu-core \
        fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Railway injects PORT. Optionally seed synthetic demo data on first boot
# when SEED_ON_START=true (safe: seed is a no-op if data already exists).
CMD ["sh", "-c", "if [ \"$SEED_ON_START\" = \"true\" ]; then python -m app.seed; fi; uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
