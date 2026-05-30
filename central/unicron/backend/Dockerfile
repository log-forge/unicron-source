# ── Stage 1: Grab the `step` CLI from the official image ──
FROM smallstep/step-cli:0.29.0 AS cli

# ── Stage 2: Back-end runtime ──
FROM python:3.13-slim AS runtime

WORKDIR /app/backend

# Copy shared package source; we vendor it into site-packages below.
COPY ./libs/unicron_shared /unicron_shared
ENV PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app:/app/backend

# Install system dependencies (optional, e.g. for poetry or curl)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl procps && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python runtime dependencies (avoid Poetry/path builds for fastest unblock)
RUN pip install --no-cache-dir \
    "fastapi[standard]>=0.115.14,<0.116.0" \
    "pydantic>=2.11.7,<3.0.0" \
    "pydantic-settings>=2.10.1,<3.0.0" \
    "python-dotenv>=1.1.1,<2.0.0" \
    "orjson>=3.10.18,<4.0.0" \
    "sqlmodel>=0.0.24,<0.0.25" \
    "asyncpg>=0.30.0,<0.31.0" \
    "apscheduler>=3.11.0,<4.0.0" \
    "cryptography>=45.0.5,<46.0.0" \
    "gunicorn>=23.0.0,<24.0.0" \
    "python-socketio[asgi]>=5.13.0,<6.0.0" \
    "redis>=6.4.0,<7.0.0" \
    "httpx>=0.28.1,<0.29.0" \
    "protobuf>=5.29.0,<6.0.0" \
    "opentelemetry-proto>=1.31.0,<2.0.0" \
    "alembic>=1.16.2,<2.0.0"

# Vendor the local unicron_shared package into site-packages so imports resolve
RUN mkdir -p /usr/local/lib/python3.13/site-packages/unicron_shared \
    && cp -r /unicron_shared/unicron_shared/unicron_shared_classes /usr/local/lib/python3.13/site-packages/unicron_shared/unicron_shared_classes \
    && cp -r /unicron_shared/unicron_shared/unicron_shared_models /usr/local/lib/python3.13/site-packages/unicron_shared/unicron_shared_models \
    && cp /unicron_shared/unicron_shared/__init__.py /usr/local/lib/python3.13/site-packages/unicron_shared/__init__.py

# Copy in the `step` binary from the first stage
COPY --from=cli /usr/local/bin/step /usr/local/bin/step

# Copy backend code
COPY ./central/unicron/backend/app ./app/
COPY ./central/unicron/backend/scripts ./scripts
COPY ./central/unicron/backend/alembic ./alembic
COPY ./central/unicron/backend/alembic.ini ./alembic.ini

CMD ["uvicorn", "app.main:asgi_app", "--host", "0.0.0.0", "--port", "8000"]
