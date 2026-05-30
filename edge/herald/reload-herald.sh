#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${SCRIPT_DIR}/common.sh"

PID_FILE="/var/run/gunicorn.pid"
HERALD_CERT="${HERALD_CERT:-/etc/herald/certs/unicron-herald-leaf.crt}"
HERALD_KEY="${HERALD_KEY:-/etc/herald/certs/unicron-herald-leaf.key}"

# 1. Basic sanity checks
log "Info" "Certificate renewal script triggered"
if [ ! -f "$HERALD_CERT" ]; then
  log "Info" "ERROR: Certificate not found at $HERALD_CERT"; exit 1; fi
if [ ! -f "$HERALD_KEY" ]; then
  log "Info" "ERROR: Key not found at $HERALD_KEY"; exit 1; fi

# 2. Optional: quick openssl parse (not failing if openssl absent)
if command -v openssl >/dev/null 2>&1; then
  EXPIRY=$(openssl x509 -in "$HERALD_CERT" -noout -enddate 2>/dev/null | cut -d= -f2 || true)
  [ -n "$EXPIRY" ] && log "Info" "New certificate notAfter: $EXPIRY"
fi

# 3. Determine Gunicorn master PID
if [ -f "$PID_FILE" ]; then
  GUNICORN_PID=$(cat "$PID_FILE" || true)
else
  GUNICORN_PID=$(pgrep -f "gunicorn.*app.main:app" | head -1 || true)
fi

if [ -z "${GUNICORN_PID:-}" ]; then
  log "Info" "ERROR: Could not find Gunicorn PID to reload"; exit 1; fi

if ! kill -0 "$GUNICORN_PID" 2>/dev/null; then
  log "Info" "ERROR: Gunicorn PID $GUNICORN_PID not running"; exit 1; fi

# 4. Send HUP for graceful reload
log "Info" "Sending SIGHUP to Gunicorn master PID $GUNICORN_PID"
kill -HUP "$GUNICORN_PID"

# 5. Optionally wait for new workers (best-effort)
WAIT_SECONDS=${HERALD_RELOAD_WAIT:-5}
log "Info" "Waiting $WAIT_SECONDS s for workers to recycle..."
sleep "$WAIT_SECONDS"

log "Info" "Reload signal complete"

# 6. Restart Fluent Bit & OpenTelemetry Collector so they pick up new cert/key
restart_component() {
  local name="$1"; shift
  local bin_path="$1"; shift
  local start_cmd=("$@")
  local pid_file="/var/run/${name}.pid"

  local pid=""
  if [ -f "$pid_file" ]; then
    pid=$(cat "$pid_file" 2>/dev/null || true)
  fi
  # Fallback to pgrep -fo (oldest) if pid invalid
  if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    case "$name" in
      fluent-bit) pid=$(pgrep -fo "/fluent-bit/bin/fluent-bit" || true);;
      otelcol) pid=$(pgrep -fo "/otelcol/otelcol" || pgrep -fo "/otelcol/otelcol-contrib" || true);;
    esac
  fi

  if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    log "Info" "${name}: process not running; skip restart"
    return 0
  fi

  log "Info" "${name}: stopping PID $pid for cert reload"
  kill "$pid" || true
  # Wait up to 5s for exit
  for i in 1 2 3 4 5; do
    if ! kill -0 "$pid" 2>/dev/null; then
      break
    fi
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null; then
    log "Info" "${name}: still running after 5s, sending SIGKILL"
    kill -KILL "$pid" || true
  fi

  if [ ! -x "$bin_path" ]; then
    log "Info" "${name}: binary $bin_path not found; cannot restart"
    return 1
  fi

  log "Info" "${name}: starting ..."
  "${start_cmd[@]}" &
  new_pid=$!
  echo "$new_pid" > "$pid_file" || true
  log "Info" "${name}: restarted with PID $new_pid"
}

# Restart Fluent Bit (quick gap acceptable).
restart_component fluent-bit /fluent-bit/bin/fluent-bit /fluent-bit/bin/fluent-bit -c /app/herald/configs/fluent-bit.conf

# Determine otel executable path
if [ -x "/otelcol/otelcol" ]; then
  _otel_exec=/otelcol/otelcol
elif [ -x "/otelcol/otelcol-contrib" ]; then
  _otel_exec=/otelcol/otelcol-contrib
else
  _otel_exec=""
fi
if [ -n "$_otel_exec" ]; then
  restart_component otelcol "$_otel_exec" "$_otel_exec" --config /app/herald/configs/otel-edge.yaml
else
  log "Info" "otelcol: binary not found; skip restart"
fi

log "Info" "Herald reload after certificate renewal completed successfully"
