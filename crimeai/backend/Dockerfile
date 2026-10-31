# syntax=docker/dockerfile:1.7
# One image definition, three targets: worker (adds OCR), dev, api (default).

FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

FROM base AS deps
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip==26.2.1 setuptools==84.0.0 \
    && /opt/venv/bin/pip install -r requirements.txt \
    && /opt/venv/bin/python -m spacy download en_core_web_sm

FROM base AS runtime
COPY --from=deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/opt/hf-cache
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin crimeai
COPY --chown=crimeai:crimeai . .
RUN mkdir -p /app/var/uploads /opt/hf-cache && chown -R crimeai:crimeai /app/var /opt/hf-cache
USER crimeai
# Bake the embedding model into the image so cold starts never download it.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small')"
# Everything the services load is now in the image; never reach out to the model hub at runtime.
# Changing EMBEDDING_MODEL or turning on ENABLE_ZERO_SHOT therefore means baking that model here too.
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

FROM runtime AS worker
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-osd tesseract-ocr-eng \
       tesseract-ocr-hin tesseract-ocr-mar tesseract-ocr-ben tesseract-ocr-asm tesseract-ocr-tel tesseract-ocr-tam \
       tesseract-ocr-kan tesseract-ocr-mal tesseract-ocr-guj tesseract-ocr-pan tesseract-ocr-ori tesseract-ocr-urd \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-ocr.txt .
RUN /opt/venv/bin/pip install -r requirements-ocr.txt
USER crimeai
CMD ["celery", "-A", "app.workers.celery_app:celery_app", "worker", "--loglevel=INFO", "--concurrency=2", "--queues=default,ml,nlp"]

FROM runtime AS dev
USER root
COPY requirements-dev.txt .
RUN /opt/venv/bin/pip install -r requirements-dev.txt
USER crimeai
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Last stage is the default build target, so platforms that cannot pick a target build the API.
FROM runtime AS api
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1
# One process per container; scale with replicas. Proxy headers give real client IPs to the rate limiter.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-127.0.0.1} --timeout-graceful-shutdown 20"]
