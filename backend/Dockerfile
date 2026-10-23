# CPC Lab backend (FastAPI + SQLAlchemy + Celery-ready)
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data

WORKDIR /app

# System deps for packages that may compile from source if wheels are unavailable
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc libpq5 libpq-dev curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-extras.txt ./
RUN pip install -r requirements.txt -r requirements-extras.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN rm -f requirements.txt requirements-extras.txt

RUN useradd --create-home --uid 10001 cpc \
 && mkdir -p /app/data \
 && chown -R cpc:cpc /app
USER cpc

COPY --chown=cpc:cpc entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=4 \
  CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
