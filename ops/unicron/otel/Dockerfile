# Custom OTel Collector image adding a minimal busybox layer for healthcheck utilities
# Reference GH issue: https://github.com/open-telemetry/opentelemetry-collector-contrib/issues/30798
# We copy the upstream otel/opentelemetry-collector-contrib binary from the published image,
# then add busybox (for wget/sh) so docker compose healthcheck can run without failing (scratch base lacks tools).

ARG OTEL_VERSION=latest
FROM otel/opentelemetry-collector-contrib:${OTEL_VERSION} AS upstream

# Stage with busybox userland
FROM busybox:1.37.0-glibc
LABEL org.opencontainers.image.source="https://github.com/open-telemetry/opentelemetry-collector-contrib" \
  maintainer="LogForge contributors"

# Create non-root user (match upstream uid 10001) and dirs
RUN adduser -D -u 10001 otel && \
  mkdir -p /etc/otelcol /var/lib/otelcol && \
  chown -R 10001:10001 /etc/otelcol /var/lib/otelcol

COPY --from=upstream /otelcol-contrib /otelcol

# Copy custom entrypoint (root creates storage path if missing then drops privileges)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 4317 4318 13133

ENTRYPOINT ["/entrypoint.sh"]
CMD ["--config","/etc/otelcol/config.yaml"]
