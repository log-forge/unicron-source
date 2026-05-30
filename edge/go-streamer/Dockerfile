# Build arguments for image references
ARG OTEL_MIN_IMAGE=unicron-otel-min:latest
ARG FLUENT_BIT_MIN_IMAGE=unicron-fluent-bit-min:latest

# Stage 1: Build go-streamer binary
FROM --platform=$BUILDPLATFORM golang:1.25-alpine AS builder
ARG TARGETOS=linux
ARG TARGETARCH
WORKDIR /app
COPY go.mod ./
COPY *.go ./
COPY internal/ ./internal/
RUN go mod tidy
RUN go mod download
COPY templates/ ./templates/
RUN CGO_ENABLED=0 GOOS="${TARGETOS}" GOARCH="${TARGETARCH:-$(go env GOARCH)}" \
    go build -ldflags="-w -s" -o go-streamer .

# Stage 2: OTel Collector binary
FROM ${OTEL_MIN_IMAGE} AS otel

# Stage 3: Fluent Bit binary
FROM ${FLUENT_BIT_MIN_IMAGE} AS fluentbit

# Stage 4: Static tini binary for distroless PID1 reaping
FROM alpine:3.21 AS tini
RUN apk add --no-cache tini-static

# Stage 5: Runtime filesystem scaffolding (no shell in final image)
FROM busybox:1.37.0-glibc AS runtimefs
RUN mkdir -p /var/lib/otelcol/queue /tmp/flb

# Stage 6: Runtime image (distroless; no shell/package manager)
FROM gcr.io/distroless/cc-debian12
WORKDIR /app

# Create runtime writable paths expected by telemetry templates.
COPY --from=runtimefs /var/lib/otelcol/queue /var/lib/otelcol/queue
COPY --from=runtimefs /tmp/flb /tmp/flb
COPY --from=tini /sbin/tini-static /tini

# Copy go-streamer binary and templates
COPY --from=builder /app/go-streamer /app/go-streamer
COPY --from=builder /app/templates /app/templates

# Copy OTel Collector binary from otel stage
COPY --from=otel /otelcol/otelcol /usr/local/bin/otelcol

# Copy Fluent Bit binary and its staged shared libraries from the
# fluent-bit-min runtime image. The trimmed Fluent Bit build places
# linked runtime libs under /usr/lib, not /lib.
COPY --from=fluentbit /fluent-bit/bin/fluent-bit /usr/local/bin/fluent-bit
COPY --from=fluentbit /usr/lib/lib*.so* /opt/fluent-bit/lib/

# Environment variables for binary paths
ENV OTEL_COLLECTOR_BIN=/usr/local/bin/otelcol \
    FLUENT_BIT_BIN=/usr/local/bin/fluent-bit \
    LD_LIBRARY_PATH=/opt/fluent-bit/lib

ENTRYPOINT ["/tini", "--", "/app/go-streamer"]
