# syntax=docker/dockerfile:1.7

FROM node:20-bookworm-slim AS node-base

ENV NPM_CONFIG_AUDIT=false \
    NPM_CONFIG_FETCH_RETRIES=5 \
    NPM_CONFIG_FETCH_RETRY_MINTIMEOUT=20000 \
    NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT=120000 \
    NPM_CONFIG_FETCH_TIMEOUT=300000 \
    NPM_CONFIG_FUND=false

FROM node-base AS central-auth-deps
WORKDIR /build/central-auth
COPY central/auth/package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

FROM central-auth-deps AS central-auth-build
COPY central/auth/tsconfig.json ./
COPY central/auth/tsup.config.mjs ./
COPY central/auth/src ./src
RUN UNICRON_APPLIANCE_BUILD=true npm run build

FROM node-base AS central-auth-prod-deps
WORKDIR /build/central-auth
COPY central/auth/package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --omit=dev

FROM node-base AS frontend-deps
WORKDIR /build/frontend
COPY central/unicron/frontend/package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

FROM frontend-deps AS frontend-build
WORKDIR /build/frontend
COPY central/unicron/frontend ./
ARG VITE_BETTER_AUTH_URL=
ARG VITE_AUTH_BASE_URL=/unicron/auth
ARG VITE_API_BASE_URL=/unicron/api
ARG VITE_EXTERNAL_API_BASE_URL=
ARG VITE_SHOW_RQ_DEVTOOLS=false
ARG VITE_AUTH_MODE=cookie
ENV UNICRON_APPLIANCE_BUILD=true \
    VITE_AUTH_MODE=${VITE_AUTH_MODE} \
    VITE_BETTER_AUTH_URL=${VITE_BETTER_AUTH_URL} \
    VITE_AUTH_BASE_URL=${VITE_AUTH_BASE_URL} \
    VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_EXTERNAL_API_BASE_URL=${VITE_EXTERNAL_API_BASE_URL} \
    VITE_SHOW_RQ_DEVTOOLS=${VITE_SHOW_RQ_DEVTOOLS}
RUN npm run build

FROM node-base AS frontend-prod-deps
WORKDIR /build/frontend
COPY central/unicron/frontend/package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --omit=dev

FROM mongo:7 AS mongo-runtime
FROM traefik:v3.4 AS traefik-runtime
FROM smallstep/step-cli:0.29.0 AS step-cli-runtime
FROM smallstep/step-ca:0.29.0 AS step-ca-runtime
FROM victoriametrics/victoria-metrics:v1.120.0 AS victoria-metrics-runtime
FROM victoriametrics/victoria-logs:v1.24.0-victorialogs AS victoria-logs-runtime
FROM otel/opentelemetry-collector-contrib:0.128.0 AS otel-runtime

FROM golang:1.23-bookworm AS appliance-manager-build
WORKDIR /build
COPY ops/appliance/manager/go.mod ./
COPY ops/appliance/manager/*.go ./
RUN go test ./... && \
    CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/unicron-appliance-manager .

FROM python:3.13-slim-bookworm AS appliance-python-build

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends binutils ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
      "pyinstaller>=6.11.0,<7.0.0" \
      "fastapi[standard]>=0.115.14,<0.116.0" \
      "uvicorn[standard]>=0.32.0,<1.0.0" \
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
      "alembic>=1.16.2,<2.0.0" \
      "celery[redis]>=5.4.0,<6.0.0" \
      "jinja2>=3.1.0,<4.0.0" \
      "apprise>=1.9.0,<2.0.0"

WORKDIR /build

COPY libs/unicron_shared /build/libs/unicron_shared
RUN pip install --no-cache-dir /build/libs/unicron_shared

COPY central/unicron/backend/app /build/backend/app
COPY central/unicron/backend/scripts /build/backend/scripts
COPY central/unicron/backend/alembic /build/backend/alembic
COPY central/unicron/backend/alembic.ini /build/backend/alembic.ini
COPY services/alert-engine/app /build/alert-engine/app
COPY services/notifier/app /build/notifier/app
COPY services/notifier/celery_app.py /build/notifier/celery_app.py
COPY ops/appliance/python-entrypoints /build/entrypoints

RUN set -eux; \
    pyinstaller --clean --noconfirm --onefile --strip \
      --name backend-api \
      --distpath /build/dist \
      --workpath /build/work/backend-api \
      --specpath /build/spec \
      --paths /build/backend \
      --collect-submodules app \
      --collect-submodules unicron_shared \
      --collect-submodules uvicorn \
      --collect-submodules socketio \
      --collect-submodules engineio \
      --collect-submodules redis \
      --hidden-import sqlalchemy.dialects.postgresql.asyncpg \
      /build/entrypoints/backend_api.py; \
    pyinstaller --clean --noconfirm --onefile --strip \
      --name backend-migrate \
      --distpath /build/dist \
      --workpath /build/work/backend-migrate \
      --specpath /build/spec \
      --paths /build/backend \
      --collect-submodules app \
      --collect-submodules scripts \
      --collect-submodules unicron_shared \
      --collect-submodules alembic \
      --collect-submodules sqlalchemy.dialects.postgresql \
      --hidden-import logging.config \
      --hidden-import sqlalchemy.dialects.postgresql.asyncpg \
      --add-data /build/backend/alembic:backend/alembic \
      --add-data /build/backend/alembic.ini:backend/alembic.ini \
      /build/entrypoints/backend_migrate.py; \
    pyinstaller --clean --noconfirm --onefile --strip \
      --name alert-engine-api \
      --distpath /build/dist \
      --workpath /build/work/alert-engine-api \
      --specpath /build/spec \
      --paths /build/alert-engine \
      --collect-submodules app \
      --collect-submodules uvicorn \
      --collect-submodules redis \
      --hidden-import sqlalchemy.dialects.postgresql.asyncpg \
      /build/entrypoints/alert_engine_api.py; \
    pyinstaller --clean --noconfirm --onefile --strip \
      --name notifier-api \
      --distpath /build/dist \
      --workpath /build/work/notifier-api \
      --specpath /build/spec \
      --paths /build/notifier \
      --collect-submodules app \
      --collect-submodules uvicorn \
      --collect-submodules celery \
      --collect-submodules kombu \
      --collect-submodules billiard \
      --collect-submodules vine \
      --collect-submodules redis \
      --collect-all apprise \
      --hidden-import app.tasks \
      --hidden-import app.tasks.notification_tasks \
      --hidden-import celery_app \
      --hidden-import sqlalchemy.dialects.postgresql.asyncpg \
      --add-data /build/notifier/app/templates:app/templates \
      /build/entrypoints/notifier_api.py; \
    pyinstaller --clean --noconfirm --onefile --strip \
      --name notifier-worker \
      --distpath /build/dist \
      --workpath /build/work/notifier-worker \
      --specpath /build/spec \
      --paths /build/notifier \
      --collect-submodules app \
      --collect-submodules celery \
      --collect-submodules kombu \
      --collect-submodules billiard \
      --collect-submodules vine \
      --collect-submodules redis \
      --collect-all apprise \
      --hidden-import app.tasks \
      --hidden-import app.tasks.notification_tasks \
      --hidden-import celery_app \
      --hidden-import sqlalchemy.dialects.postgresql.asyncpg \
      --add-data /build/notifier/app/templates:app/templates \
      /build/entrypoints/notifier_worker.py

FROM debian:bookworm-slim AS appliance

ENV NODE_ENV=production \
    UNICRON_DATA_DIR=/var/lib/unicron

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      libatomic1 \
      libcurl4 \
      libgcc-s1 \
      libgssapi-krb5-2 \
      liblzma5 \
      libsasl2-2 \
      libsnappy1v5 \
      libssl3 \
      libstdc++6 \
      libzstd1 \
      postgresql-15 \
      redis-server && \
    rm -rf /var/lib/apt/lists/*

COPY --from=node-base /usr/local/bin/node /usr/local/bin/node
COPY --from=mongo-runtime /usr/bin/mongod /usr/local/bin/mongod
COPY --from=traefik-runtime /usr/local/bin/traefik /usr/local/bin/traefik
COPY --from=step-cli-runtime /usr/local/bin/step /usr/local/bin/step
COPY --from=step-ca-runtime /usr/local/bin/step-ca /usr/local/bin/step-ca
COPY --from=victoria-metrics-runtime /victoria-metrics-prod /usr/local/bin/victoria-metrics
COPY --from=victoria-logs-runtime /victoria-logs-prod /usr/local/bin/victoria-logs
COPY --from=otel-runtime /otelcol-contrib /usr/local/bin/otelcol-contrib
COPY --from=appliance-manager-build /out/unicron-appliance-manager /usr/local/bin/unicron-appliance-manager

RUN groupadd --system mongodb && \
    useradd --system --gid mongodb --home /nonexistent --shell /usr/sbin/nologin mongodb && \
    groupadd --system unicron && \
    useradd --system --gid unicron --home /opt/unicron --shell /usr/sbin/nologin unicron && \
    mkdir -p \
      /home \
      /opt/unicron/bin \
      /var/lib/unicron/backend \
      /var/lib/unicron/central-auth \
      /var/lib/unicron/mongo \
      /var/lib/unicron/notifier \
      /var/lib/unicron/otelcol \
      /var/lib/unicron/postgres \
      /var/lib/unicron/redis \
      /var/lib/unicron/secrets \
      /var/lib/unicron/traefik \
      /var/lib/unicron/victoria-logs \
      /var/lib/unicron/victoria-metrics \
      /var/lib/unicron/pki/certs \
      /var/lib/unicron/pki/config \
      /var/lib/unicron/pki/public \
      /var/lib/unicron/pki/secrets \
      /var/lib/unicron/pki/trust \
      /var/lib/unicron/pki/traefik-certs \
      /var/lib/unicron/pki/ra-provisioner && \
    ln -s /var/lib/unicron/pki /home/step && \
    ln -s /usr/local/bin/unicron-appliance-manager /usr/local/bin/unicron-pki-renew-hook && \
    mkdir -p /usr/local/share/unicron/postgres-seed && \
    chown -R postgres:postgres /usr/local/share/unicron/postgres-seed && \
    chown -R unicron:unicron /opt/unicron && \
    chown -R unicron:unicron \
      /var/lib/unicron/backend \
      /var/lib/unicron/central-auth \
      /var/lib/unicron/notifier \
      /var/lib/unicron/otelcol \
      /var/lib/unicron/victoria-logs \
      /var/lib/unicron/victoria-metrics \
      /var/lib/unicron/pki/trust \
      /var/lib/unicron/pki/ra-provisioner && \
    chmod 0700 /var/lib/unicron/secrets && \
    chown -R postgres:postgres /var/lib/unicron/postgres && \
    chown -R redis:redis /var/lib/unicron/redis && \
    chown -R mongodb:mongodb /var/lib/unicron/mongo

USER postgres
RUN /usr/lib/postgresql/15/bin/initdb \
      -D /usr/local/share/unicron/postgres-seed \
      --username=postgres \
      --auth-local=trust \
      --auth-host=scram-sha-256 && \
    printf "\nlisten_addresses = '127.0.0.1'\nport = 5432\nunix_socket_directories = '/run/postgresql'\n" >> /usr/local/share/unicron/postgres-seed/postgresql.conf
USER root

WORKDIR /opt/unicron

COPY --from=appliance-python-build --chown=unicron:unicron /build/dist/backend-api /opt/unicron/bin/backend-api
COPY --from=appliance-python-build --chown=unicron:unicron /build/dist/backend-migrate /opt/unicron/bin/backend-migrate
COPY --from=appliance-python-build --chown=unicron:unicron /build/dist/alert-engine-api /opt/unicron/bin/alert-engine-api
COPY --from=appliance-python-build --chown=unicron:unicron /build/dist/notifier-api /opt/unicron/bin/notifier-api
COPY --from=appliance-python-build --chown=unicron:unicron /build/dist/notifier-worker /opt/unicron/bin/notifier-worker

COPY --from=central-auth-build --chown=unicron:unicron /build/central-auth/dist /opt/unicron/central-auth/dist
COPY --from=central-auth-prod-deps --chown=unicron:unicron /build/central-auth/node_modules /opt/unicron/central-auth/node_modules
COPY --from=central-auth-prod-deps --chown=unicron:unicron /build/central-auth/package*.json /opt/unicron/central-auth/

COPY --from=frontend-build --chown=unicron:unicron /build/frontend/build /opt/unicron/frontend/build
COPY --from=frontend-build --chown=unicron:unicron /build/frontend/dist /opt/unicron/frontend/dist
COPY --from=frontend-prod-deps --chown=unicron:unicron /build/frontend/node_modules /opt/unicron/frontend/node_modules
COPY --from=frontend-prod-deps --chown=unicron:unicron /build/frontend/package*.json /opt/unicron/frontend/

COPY --chown=unicron:unicron ops/appliance/traefik-config.template.yaml /opt/unicron/appliance/traefik-config.template.yaml
COPY --chown=unicron:unicron ops/appliance/otel-collector-config.yaml /opt/unicron/appliance/otel-collector-config.yaml

RUN find /opt/unicron -type f \( \
        -name '*.map' -o \
        -name '*.py' -o \
        -name '*.sh' -o \
        -name '*.ts' -o \
        -name '*.tsx' \
      \) -delete && \
    chmod +x \
      /usr/local/bin/unicron-appliance-manager \
      /opt/unicron/bin/backend-api \
      /opt/unicron/bin/backend-migrate \
      /opt/unicron/bin/alert-engine-api \
      /opt/unicron/bin/notifier-api \
      /opt/unicron/bin/notifier-worker && \
    rm -f \
      /bin/bash \
      /usr/bin/bash \
      /bin/dash \
      /usr/bin/dash \
      /bin/sh \
      /usr/bin/sh \
      /bin/python \
      /usr/bin/python \
      /bin/python3 \
      /usr/bin/python3 \
      /usr/local/bin/python \
      /usr/local/bin/python3 \
      /bin/openssl \
      /usr/bin/openssl

EXPOSE 80 443 8443

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD ["/usr/local/bin/unicron-appliance-manager", "healthcheck"]

ENTRYPOINT ["/usr/local/bin/unicron-appliance-manager"]
