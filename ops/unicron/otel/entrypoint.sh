#!/bin/sh
set -eu

# NOTE: busybox:glibc variant used here doesn't ship 'su' with full PAM; keeping root
# execution but ensuring dirs owned by otel UID (10001) for file_storage safety.
OTEL_UID=10001
STORAGE_DIR=/var/lib/otelcol/storage
BASE_DIR=/var/lib/otelcol

if [ ! -d "$STORAGE_DIR" ]; then
  mkdir -p "$STORAGE_DIR"
fi
chown -R ${OTEL_UID}:${OTEL_UID} "$BASE_DIR" || true
ls -ld "$STORAGE_DIR" || true

exec /otelcol "$@"
