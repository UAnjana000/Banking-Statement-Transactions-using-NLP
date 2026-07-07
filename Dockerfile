# finunderwrite serving image (lightweight: no torch/sdv/sentence-transformers).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

# System deps for native/scanned PDF handling (OCR runs offline, but wrappers
# and native PDF parsing still benefit from these binaries).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        poppler-utils \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install ONLY the lightweight serving runtime (never requirements-ml.txt).
COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

# Apply DB migrations at boot, then serve. 1-2 workers for a 512 MB budget.
CMD ["sh", "-c", "alembic upgrade head && gunicorn finunderwrite.api:app -k uvicorn.workers.UvicornWorker --workers ${WEB_CONCURRENCY:-2} --bind 0.0.0.0:${PORT:-8000} --timeout 120"]
