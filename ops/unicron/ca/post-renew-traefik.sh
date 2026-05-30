#!/bin/sh

# Function to log with timestamp
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [RENEW-HOOK] $1"; }

# Source and target cert directories
STEPPATH="${STEPPATH:-/home/step}"
SOURCE_CERT_DIR="$STEPPATH/certs"
TARGET_CERT_DIR="$STEPPATH/traefik-certs"

# Post-renew hook for Traefik certificates
# Export renewed certs to the shared TLS volume
if [ -d "$TARGET_CERT_DIR" ]; then
  if cp "$SOURCE_CERT_DIR/unicron-traefik-leaf.crt" "$TARGET_CERT_DIR/unicron-traefik-leaf.crt" \
    && cp "$SOURCE_CERT_DIR/unicron-traefik-leaf.key" "$TARGET_CERT_DIR/unicron-traefik-leaf.key" \
    && cp "$SOURCE_CERT_DIR/root_ca.crt" "$TARGET_CERT_DIR/root_ca.crt"; then
    log "Exported Traefik certs to $TARGET_CERT_DIR"
  else
    log "ERROR: Failed to export Traefik certs to $TARGET_CERT_DIR"
  fi
else
  log "WARN: $TARGET_CERT_DIR not present; skipping cert export"
fi

# Touch the dynamic cert file so Traefik's file provider reloads TLS certs.
TARGET_FILE="${TRAEFIK_DYNAMIC_CONFIG_FILE:-/etc/traefik/shared/traefik-config.yaml}"
if touch "$TARGET_FILE" 2>/dev/null; then
  log "Traefik certs renewed successfully, touch OK"
else
  log "ERROR: Could not touch $TARGET_FILE - permission issue?"
  ls -ld $(dirname "$TARGET_FILE") >&2 2>/dev/null || true
  ls -l "$TARGET_FILE" >&2 2>/dev/null || true
fi
