# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.13.0
ARG PYTHON_MAJOR=3.13
ARG OTEL_MIN_IMAGE=localhost:5000/unicron-otel-min:latest
ARG FLUENT_BIT_MIN_IMAGE=localhost:5000/unicron-fluent-bit-min:latest
ARG UPX_VERSION=4.2.4

FROM debian:bookworm-slim AS python-source
ARG PYTHON_VERSION
ARG PYTHON_MAJOR
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    ca-certificates \
    curl \
    libbz2-dev \
    libexpat1-dev \
    libffi-dev \
    libgdbm-compat-dev \
    libgdbm-dev \
    liblzma-dev \
    libncurses-dev \
    libreadline-dev \
    libsqlite3-dev \
    libssl-dev \
    tk-dev \
    uuid-dev \
    xz-utils \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /tmp/python-build
RUN curl -fsSLo python.tgz "https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz" \
    && tar -xzf python.tgz \
    && cd Python-${PYTHON_VERSION} \
    && ./configure --prefix=/usr/local --enable-optimizations --with-lto --enable-shared \
    && make -j"$(nproc)" \
    && make altinstall
RUN ldconfig \
    && /usr/local/bin/python${PYTHON_MAJOR} -m ensurepip --upgrade \
    && ln -sf python${PYTHON_MAJOR} /usr/local/bin/python3 \
    && ln -sf python3 /usr/local/bin/python \
    && ln -sf pip${PYTHON_MAJOR} /usr/local/bin/pip3 \
    && ln -sf pip3 /usr/local/bin/pip \
    && ldconfig

FROM debian:bookworm-slim AS python-base
COPY --from=python-source /usr/local /usr/local
ENV PATH="/usr/local/bin:${PATH}"
RUN apt-get update && apt-get install --no-install-recommends -y \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/* \
    && ldconfig

FROM ${FLUENT_BIT_MIN_IMAGE} AS fluentbit

FROM ${OTEL_MIN_IMAGE} AS otelcol

FROM debian:bookworm-slim AS upx
ARG TARGETARCH
ARG UPX_VERSION
RUN apt-get update && apt-get install --no-install-recommends -y ca-certificates curl xz-utils \
    && rm -rf /var/lib/apt/lists/*
RUN set -eux; \
    url_base="https://github.com/upx/upx/releases/download/v${UPX_VERSION}"; \
    case "${TARGETARCH}" in \
    amd64) upx_pkg="upx-${UPX_VERSION}-amd64_linux.tar.xz" ;; \
    arm64) upx_pkg="upx-${UPX_VERSION}-arm64_linux.tar.xz" ;; \
    *) echo "unsupported TARGETARCH ${TARGETARCH}"; exit 1 ;; \
    esac; \
    curl -fsSL "${url_base}/${upx_pkg}" -o /tmp/upx.tar.xz; \
    mkdir -p /tmp/upx; \
    tar -xf /tmp/upx.tar.xz -C /tmp/upx --strip-components=1; \
    install -m 755 /tmp/upx/upx /usr/local/bin/upx; \
    rm -rf /tmp/upx /tmp/upx.tar.xz

FROM debian:bookworm-slim AS otelcol_compressed
COPY --from=upx /usr/local/bin/upx /usr/local/bin/upx
COPY --from=otelcol /otelcol/otelcol /otelcol/otelcol
RUN upx --best --lzma /otelcol/otelcol

FROM debian:bookworm-slim AS fluentbit_compressed
COPY --from=upx /usr/local/bin/upx /usr/local/bin/upx
RUN apt-get update && apt-get install --no-install-recommends -y libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=fluentbit /fluent-bit /opt/fluent-bit
RUN upx --best --lzma /opt/fluent-bit/bin/fluent-bit

FROM python-base AS pyinstaller
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

COPY ./libs/unicron_shared /workspace/unicron_shared
COPY edge/herald /workspace/edge/herald

RUN pip install --no-cache-dir \
    "fastapi>=0.120.2,<0.121.0" \
    "uvicorn[standard]>=0.38.0,<0.39.0" \
    "gunicorn>=23.0.0,<24.0.0" \
    "pydantic>=2.11.7,<3.0.0" \
    "pydantic-settings>=2.10.1,<3.0.0" \
    "python-dotenv>=1.1.1,<2.0.0" \
    "orjson>=3.10.18,<4.0.0" \
    "httpx[http2]>=0.28.1,<0.29.0" \
    "h2>=4.2.0,<5.0.0" \
    "aiohttp>=3.12.15,<4.0.0" \
    "python-socketio[asyncio-client]>=5.13.0,<6.0.0" \
    "docker>=7.1.0,<8.0.0" \
    "setuptools>=80.9.0" \
    "pyinstaller>=6.10.0,<7.0.0"

RUN apt-get update && apt-get install --no-install-recommends -y binutils && rm -rf /var/lib/apt/lists/*
COPY --from=upx /usr/local/bin/upx /usr/local/bin/upx

RUN python - <<'PY'
import shutil
from pathlib import Path
import sysconfig

paths = sysconfig.get_paths()
purelib = Path(paths['purelib'])
pkg_dir = purelib / 'unicron_shared'
pkg_dir.mkdir(parents=True, exist_ok=True)
shutil.copytree('/workspace/unicron_shared/unicron_shared/unicron_shared_classes', pkg_dir / 'unicron_shared_classes', dirs_exist_ok=True)
shutil.copytree('/workspace/unicron_shared/unicron_shared/unicron_shared_models', pkg_dir / 'unicron_shared_models', dirs_exist_ok=True)
shutil.copy('/workspace/unicron_shared/unicron_shared/__init__.py', pkg_dir / '__init__.py')
PY

RUN pyinstaller -F -n herald-api \
    /workspace/edge/herald/app/serve_gunicorn.py \
    --hidden-import orjson \
    --hidden-import h2 \
    --hidden-import httpx \
    --collect-all unicron_shared \
    --collect-all pydantic \
    --collect-all pydantic_settings \
    --clean

RUN upx --best --lzma /workspace/dist/herald-api

FROM debian:bookworm-slim AS runtime

ENV PATH="/usr/local/bin:/fluent-bit/bin:${PATH}"

RUN apt-get update && apt-get install --no-install-recommends -y \
    bash \
    ca-certificates \
    curl \
    openssl \
    gawk \
    jq \
    libluajit-5.1-2 \
    libyaml-0-2 \
    libcurl4 \
    libsasl2-2 \
    libpq5 \
    libssl3 \
    libzstd1 \
    liblzma5 \
    liblz4-1 \
    libsystemd0 \
    libcap2 \
    libgcrypt20 \
    libgpg-error0 \
    libstdc++6 \
    tzdata \
    && rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man /usr/share/locale

RUN mkdir -p /usr/local/lib/lua/5.1
COPY --from=fluentbit /usr/local/lib/lua/5.1/cjson.so /usr/local/lib/lua/5.1/cjson.so

# Copy only the Fluent Bit binary; plugins used are built-in
COPY --from=fluentbit_compressed /opt/fluent-bit/bin /fluent-bit/bin

COPY --from=otelcol_compressed /otelcol/otelcol /otelcol/otelcol
RUN chmod +x /otelcol/otelcol

COPY --from=pyinstaller /workspace/dist/herald-api /usr/local/bin/herald-api

WORKDIR /app/herald

COPY edge/herald/app ./app
COPY edge/herald/configs ./configs
COPY edge/herald/lua ./lua
COPY edge/herald/common.sh /usr/local/bin/common.sh
COPY edge/herald/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY edge/herald/reload-herald.sh /usr/local/bin/reload-herald.sh
COPY edge/herald/ingestion-check.sh /usr/local/bin/ingestion-check.sh
COPY edge/herald/deregister-herald.sh /usr/local/bin/deregister-herald.sh

RUN chmod +x /usr/local/bin/common.sh /usr/local/bin/entrypoint.sh /usr/local/bin/reload-herald.sh /usr/local/bin/ingestion-check.sh /usr/local/bin/deregister-herald.sh

VOLUME ["/herald-data"]

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
