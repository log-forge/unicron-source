#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${SCRIPT_DIR}/common.sh"

HOME_DIR="${HOME:-/root}"
HERALD_CA_ROOT="${HERALD_CA_ROOT:-/herald-data/certs/root_ca.crt}"
HERALD_CERT="${HERALD_CERT:-/herald-data/certs/unicron-herald-leaf.crt}"
HERALD_KEY="${HERALD_KEY:-/herald-data/certs/unicron-herald-leaf.key}"

CENTRAL_MTLS_URL="${CENTRAL_MTLS_URL:-}"
API_BASE_URL="${API_BASE_URL:-/unicron/api}"

if [ -z "$CENTRAL_MTLS_URL" ]; then
  log "Error" "CENTRAL_MTLS_URL is not set"
  exit 2
fi

if [ ! -f "$HERALD_CERT" ] || [ ! -f "$HERALD_KEY" ] || [ ! -f "$HERALD_CA_ROOT" ]; then
  log "Error" "Missing cert material (cert=$HERALD_CERT key=$HERALD_KEY ca=$HERALD_CA_ROOT)"
  exit 2
fi

url="${CENTRAL_MTLS_URL}${API_BASE_URL}/herald/deregister"
log "Info" "Deregistering Herald via mTLS at $url"

tmp_body="/tmp/herald_deregister_body_$$.log"
http_code=$(curl --silent --show-error \
  --cert "$HERALD_CERT" --key "$HERALD_KEY" \
  --cacert "$HERALD_CA_ROOT" \
  -X POST "$url" \
  -H 'Content-Type: application/json' \
  -d '{}' \
  -w '%{http_code}' \
  -o "$tmp_body" || echo '000')

if [ "$http_code" != "200" ]; then
  if [ -s "$tmp_body" ]; then
    # shellcheck disable=SC2002
    failure_body=$(cat "$tmp_body" | tr '\r' '\n' | sed 's/^ *//;s/ *$//')
  else
    failure_body="<empty response body>"
  fi
  rm -f "$tmp_body" 2>/dev/null || true
  log "Error" "Herald deregister failed (HTTP $http_code). Response: $failure_body"
  exit 1
fi

if [ -s "$tmp_body" ]; then
  cat "$tmp_body"
fi
rm -f "$tmp_body" 2>/dev/null || true
log "Info" "Herald deregistered successfully."
