# Voice models are large native wheels, so this is a plain (not slim-alpine)
# image. Whisper and Piper both run on CPU here.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    VOICE_MODELS_DIR=/models

WORKDIR /app

# libgomp is required by ctranslate2 (faster-whisper); espeak-ng data ships in
# the piper wheel, but the shared library is not bundled.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 espeak-ng-data curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-voice.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-voice.txt

COPY . .

RUN mkdir -p /models

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Render injects $PORT; default to 8000 locally.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --ws websockets"]
