# FinUnderWrite serving image for Hugging Face Spaces (and local Docker).
# Free Spaces CPU Basic: listen on 7860, run as UID 1000. No torch/sdv.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src \
    HOME=/home/user \
    PORT=7860 \
    WEB_CONCURRENCY=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        poppler-utils \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 user

WORKDIR /app

COPY --chown=user:user requirements.txt ./
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY --chown=user:user . .

USER user
EXPOSE 7860

# Migrations then serve. Spaces sets/expects app_port 7860; override with $PORT elsewhere.
CMD ["sh", "-c", "alembic upgrade head && gunicorn finunderwrite.api:app -k uvicorn.workers.UvicornWorker --workers ${WEB_CONCURRENCY:-1} --bind 0.0.0.0:${PORT:-7860} --timeout 120"]
