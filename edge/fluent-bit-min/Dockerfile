# syntax=docker/dockerfile:1.7

ARG FLUENT_BIT_VERSION=3.1.4

# Build a plugin-trimmed Fluent Bit for the target platform.
FROM --platform=$TARGETPLATFORM debian:bookworm-slim AS builder
ARG FLUENT_BIT_VERSION

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    cmake \
    curl \
    pkg-config \
    libssl-dev \
    bison \
    flex \
    zlib1g-dev \
    ccache \
    ninja-build \
 && rm -rf /var/lib/apt/lists/*

ENV CCACHE_DIR=/root/.cache/ccache

WORKDIR /src

# Fetch Fluent Bit source matching the requested version
RUN curl -fsSL -o fluent-bit.tar.gz \
    https://github.com/fluent/fluent-bit/archive/refs/tags/v${FLUENT_BIT_VERSION}.tar.gz \
    && tar -xf fluent-bit.tar.gz

WORKDIR /src/fluent-bit-${FLUENT_BIT_VERSION}/build

# Enable only the plugins required by the go-streamer Fluent Bit pipeline.
RUN --mount=type=cache,target=/root/.cache/ccache cmake -G Ninja .. \
    -DCMAKE_BUILD_TYPE=MinSizeRel \
    -DFLB_ALL=Off \
    -DFLB_SHARED_LIB=Off \
    -DFLB_IN_TAIL=On \
    -DFLB_IN_FORWARD=On \
    -DFLB_IN_HTTP=On \
    -DFLB_OUT_HTTP=On \
    -DFLB_HTTP_SERVER=On \
    -DFLB_TLS=Off \
    -DFLB_REGEX=On \
    -DFLB_SQLITE=On \
    -DFLB_CONFIG_YAML=Off \
    -DCMAKE_C_COMPILER_LAUNCHER=ccache \
    -DCMAKE_CXX_COMPILER_LAUNCHER=ccache

RUN --mount=type=cache,target=/root/.cache/ccache cmake --build . --parallel

RUN install -Dm755 bin/fluent-bit /out/fluent-bit/bin/fluent-bit \
    && strip --strip-unneeded /out/fluent-bit/bin/fluent-bit

# Stage all runtime shared libraries linked by fluent-bit.
# This avoids missing-lib crashes (for example libz.so.1) in the final agent image.
RUN set -eux; \
    ldd /out/fluent-bit/bin/fluent-bit \
      | awk '/=> \// {print $3} /^\/[^[:space:]]+/ {print $1}' \
      | sort -u \
      | while read -r lib; do \
          [ -f "$lib" ] || continue; \
          install -Dm755 "$lib" "/out/usr/lib/$(basename "$lib")"; \
        done


# -----------------
# Minimal runtime
# -----------------
FROM --platform=$TARGETPLATFORM gcr.io/distroless/cc-debian12:nonroot AS runtime

ENV PATH="/fluent-bit/bin:${PATH}" \
    LD_LIBRARY_PATH="/usr/lib"

COPY --from=builder /out/fluent-bit/bin/fluent-bit /fluent-bit/bin/fluent-bit
COPY --from=builder /out/usr/lib /usr/lib
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt

VOLUME ["/tmp"]

EXPOSE 24224 2021

ENTRYPOINT ["fluent-bit"]
CMD ["--help"]
