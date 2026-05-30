#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${SCRIPT_DIR}/common.sh"

HERALD_CA_ROOT="/herald-data/certs/root_ca.crt"; export HERALD_CA_ROOT
HERALD_CERT="/herald-data/certs/unicron-herald-leaf.crt"; export HERALD_CERT
HERALD_KEY="/herald-data/certs/unicron-herald-leaf.key"; export HERALD_KEY
HERALD_CSR="/herald-data/certs/unicron-herald-leaf.csr"
HERALD_CERT_NOT_AFTER_SECONDS="${HERALD_CERT_NOT_AFTER_SECONDS:-43200}"; export HERALD_CERT_NOT_AFTER_SECONDS # 12h
HERALD_CERT_RENEW_EXPIRES_IN_SECONDS="${HERALD_CERT_RENEW_EXPIRES_IN_SECONDS:-3600}"; export HERALD_CERT_RENEW_EXPIRES_IN_SECONDS # renew when <1h left

ensure_dirs() {
  mkdir -p "$(dirname "$HERALD_CERT")"
}

fetch_root_ca() {
  local tmp_json
  tmp_json=$(mktemp)
  log "Info" "Fetching root CA from $CENTRAL_URL${API_BASE_URL}/ca/root ..."
  curl -fsSLk "$CENTRAL_URL${API_BASE_URL}/ca/root" -o "$tmp_json"
  local pem
  pem=$(jq -r '.root_ca_pem' "$tmp_json")
  rm -f "$tmp_json"
  echo "$pem" > "$HERALD_CA_ROOT.tmp"

  local fp current expected
  current=$(openssl x509 -in "$HERALD_CA_ROOT.tmp" -noout -fingerprint -sha256 | cut -d= -f2 | tr -d ':' | tr 'A-F' 'a-f')
  expected=$(printf '%s' "$CA_FINGERPRINT" | tr -d ':\r\n' | tr 'A-F' 'a-f')
  if [ "$current" != "$expected" ]; then
    fatal "Root CA fingerprint mismatch (got $current expected $expected)"
  fi
  mv "$HERALD_CA_ROOT.tmp" "$HERALD_CA_ROOT"
  log "Info" "Root CA pinned successfully."
}

bootstrap_cert() {
  log "Info" "Requesting bootstrap cert..."
  issue_cert new "$CENTRAL_URL${API_BASE_URL}/cert/bootstrap" bearer
}

renew_cert_if_needed() {
  if openssl x509 -checkend "$HERALD_CERT_RENEW_EXPIRES_IN_SECONDS" -noout -in "$HERALD_CERT"; then
    return 0
  fi
  log "Info" "Certificate expiring soon; requesting renewal"
  issue_cert existing "$CENTRAL_MTLS_URL${API_BASE_URL}/cert/sign" mtls
  /usr/local/bin/reload-herald.sh || true
}

start_renew_loop() {
  while true; do
    sleep 300
    renew_cert_if_needed || log "Warn" "Renewal attempt failed; will retry"
  done &
}

register_herald() {
  spacer
  log "Info" "Registering Herald with Central over mtls at $CENTRAL_MTLS_URL$API_BASE_URL/herald/register ..."
  local attempt=0 max_attempts=4 backoff=2 sleep_time=$backoff
  while [ $attempt -lt $max_attempts ]; do
    attempt=$((attempt + 1))
    log "Info" "Registration attempt $attempt of $max_attempts..."
    tmp_body=$(mktemp)
    http_code=$(
      curl --silent --show-error \
        --cert "$HERALD_CERT" --key "$HERALD_KEY" \
        --cacert "$HERALD_CA_ROOT" \
        -X POST "${CENTRAL_MTLS_URL}${API_BASE_URL}/herald/register" \
        -H 'Content-Type: application/json' \
        -d '{}' \
        -w '%{http_code}' \
        -o "$tmp_body" || echo '000'
    )
    if [ "$http_code" = "200" ]; then
      log "Info" "Herald registration succeeded."
      rm -f "$tmp_body"
      break
    fi
    failure_body="<empty response body>"
    if [ -s "$tmp_body" ]; then
      failure_body=$(cat "$tmp_body" | tr '\r' '\n' | sed 's/^ *//;s/ *$//')
    fi
    rm -f "$tmp_body"
    log "Warn" "Herald registration failed (HTTP $http_code). Response: $failure_body"
    if [ $attempt -lt $max_attempts ]; then
      log "Info" "Retrying in $sleep_time seconds..."
      sleep $sleep_time
      sleep_time=$((sleep_time * backoff))
    else
      fatal "Herald registration failed after $max_attempts attempts (last HTTP $http_code). Response: $failure_body"
    fi
  done
}

start_services() {
  spacer
  # OTel Collector and Fluent Bit are now managed by go-streamer (Phase 39).
  # Binaries remain installed in the container for go-streamer to supervise.

  log "Info" "Performing ingestion self-check..."
  if /usr/local/bin/ingestion-check.sh; then
    log "Info" "Ingestion self-check succeeded."
  else
    fatal "Ingestion self-check failed."
  fi

  spacer
  log "Info" "Starting Herald web server..."
  if [ -x "/usr/local/bin/herald-api" ]; then
    exec /usr/local/bin/herald-api
  fi

  exec gunicorn app.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:$HERALD_PORT \
    --certfile "$HERALD_CERT" \
    --keyfile "$HERALD_KEY" \
    --workers 2 \
    --timeout 120 \
    --graceful-timeout 30 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --preload \
    --pid /var/run/gunicorn.pid \
    --access-logfile - \
    --error-logfile -
}

main() {
  log "Info" "Starting Herald entrypoint..."
  require_vars HERALD_ID HERALD_NAME HERALD_PORT CENTRAL_URL CENTRAL_MTLS_URL CA_FINGERPRINT HERALD_ENROLL_TOKEN HERALD_CERT_SUBJECTS API_BASE_URL
  ensure_dirs
  fetch_root_ca
  bootstrap_cert
  register_herald
  start_renew_loop
  start_services
}

main "$@"
