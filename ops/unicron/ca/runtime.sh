#!/bin/sh
set -eu

STEPPATH=${STEPPATH:-/home/step}
STEPPATH_CERTS=$STEPPATH/certs
STEPPATH_CONFIG=$STEPPATH/config
STEPPATH_SECRETS=$STEPPATH/secrets
STEPPATH_TRUST=$STEPPATH/trust
STEPPATH_TRAEFIK_EXPORT=$STEPPATH/traefik-certs
STEPPATH_RA_PROVISIONER_EXPORT=$STEPPATH/ra-provisioner

BOOTSTRAP_STAMP=$STEPPATH/.bootstrapped
POST_RENEW_TRAEFIK_SCRIPT=$STEPPATH/post-renew-traefik.sh

STEP_CA_ROOT_CA_CERT=$STEPPATH_CERTS/root_ca.crt
STEP_CA_ROOT_FINGERPRINT=$STEPPATH_CERTS/root_ca_fingerprint.txt
TRAEFIK_CERT=$STEPPATH_CERTS/unicron-traefik-leaf.crt
TRAEFIK_KEY=$STEPPATH_CERTS/unicron-traefik-leaf.key
LOCALHOST_CERT=$STEPPATH_CERTS/unicron-localhost-leaf.crt
LOCALHOST_KEY=$STEPPATH_CERTS/unicron-localhost-leaf.key

STEP_CA_PW=$STEPPATH_SECRETS/ca.jwk.pw
RA_JWK_PW=$STEPPATH_SECRETS/ra.jwk.pw
RA_JWK_JSON=$STEPPATH_SECRETS/ra.jwk.json
RA_JWK_JSON_PUB=$STEPPATH/public/ra.jwk.json.pub

STEP_CA_CONFIG=$STEPPATH_CONFIG/ca.json
RA_CONFIG=$STEPPATH_CONFIG/ra-ca.json

TRAEFIK_RENEW_EXPIRES_IN_SECONDS=${TRAEFIK_RENEW_EXPIRES_IN_SECONDS:-28800}
TRAEFIK_CERT_SANS=${TRAEFIK_CERT_SANS:-}
STEP_CA_PID=
RENEW_PID=

log() {
  level="$1"
  shift
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [PKI-RUNTIME] [$level] $*"
}

fatal() {
  log "Fatal" "$1"
  exit 1
}

require_file() {
  file="$1"
  desc="$2"
  [ -s "$file" ] || fatal "Missing or empty $desc: $file"
}

require_positive_int() {
  var_name="$1"
  val="$2"
  case "$val" in
    ''|*[!0-9]*) fatal "$var_name must be a positive integer (got '$val')." ;;
  esac
  if [ "$val" -le 0 ] 2>/dev/null; then
    fatal "$var_name must be greater than zero (got '$val')."
  fi
}

trim() {
  printf '%s' "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

sync_export_certs() {
  log "Info" "Exporting validated public certs for least-privilege mounts."
  mkdir -p "$STEPPATH_TRUST" "$STEPPATH_TRAEFIK_EXPORT" "$STEPPATH_RA_PROVISIONER_EXPORT"
  cp "$STEP_CA_ROOT_CA_CERT" "$STEPPATH_TRUST/root_ca.crt"
  cp "$STEP_CA_ROOT_FINGERPRINT" "$STEPPATH_TRUST/root_ca_fingerprint.txt"
  cp "$TRAEFIK_CERT" "$STEPPATH_TRAEFIK_EXPORT/unicron-traefik-leaf.crt"
  cp "$TRAEFIK_KEY" "$STEPPATH_TRAEFIK_EXPORT/unicron-traefik-leaf.key"
  cp "$STEP_CA_ROOT_CA_CERT" "$STEPPATH_TRAEFIK_EXPORT/root_ca.crt"
  cp "$RA_JWK_JSON" "$STEPPATH_RA_PROVISIONER_EXPORT/ra.jwk.json"
  cp "$RA_JWK_PW" "$STEPPATH_RA_PROVISIONER_EXPORT/ra.jwk.pw"
  chmod 0444 \
    "$STEPPATH_TRUST/root_ca.crt" \
    "$STEPPATH_TRUST/root_ca_fingerprint.txt" \
    "$STEPPATH_TRAEFIK_EXPORT/root_ca.crt" \
    "$STEPPATH_TRAEFIK_EXPORT/unicron-traefik-leaf.crt" 2>/dev/null || true
  if id unicron >/dev/null 2>&1; then
    chown unicron:unicron \
      "$STEPPATH_RA_PROVISIONER_EXPORT/ra.jwk.json" \
      "$STEPPATH_RA_PROVISIONER_EXPORT/ra.jwk.pw" 2>/dev/null || true
  fi
  chmod 0400 \
    "$STEPPATH_RA_PROVISIONER_EXPORT/ra.jwk.json" \
    "$STEPPATH_RA_PROVISIONER_EXPORT/ra.jwk.pw" 2>/dev/null || true

  target_file="${TRAEFIK_DYNAMIC_CONFIG_FILE:-/etc/traefik/shared/traefik-config.yaml}"
  if touch "$target_file" 2>/dev/null; then
    log "Info" "Touched $target_file to trigger Traefik reload."
  else
    log "Warn" "Could not touch $target_file; Traefik may reload certs on next config change."
  fi
}

validate_pki() {
  log "Info" "Validating production PKI material."

  [ -f "$BOOTSTRAP_STAMP" ] || fatal "Bootstrap stamp missing: $BOOTSTRAP_STAMP. Run the explicit stepca-init job before starting runtime services."

  require_file "$STEP_CA_ROOT_CA_CERT" "root CA certificate"
  require_file "$STEP_CA_ROOT_FINGERPRINT" "root CA fingerprint"
  require_file "$STEP_CA_CONFIG" "CA configuration"
  require_file "$RA_CONFIG" "RA configuration"
  require_file "$RA_JWK_JSON" "RA private JWK"
  require_file "$RA_JWK_JSON_PUB" "RA public JWK"
  require_file "$TRAEFIK_CERT" "Traefik certificate"
  require_file "$TRAEFIK_KEY" "Traefik private key"
  require_file "$LOCALHOST_CERT" "localhost certificate"
  require_file "$LOCALHOST_KEY" "localhost private key"
  require_file "$STEP_CA_PW" "CA password file"
  require_file "$RA_JWK_PW" "RA provisioner password file"

  actual_fingerprint=$(step certificate fingerprint "$STEP_CA_ROOT_CA_CERT")
  expected_fingerprint=$(tr -d '[:space:]' < "$STEP_CA_ROOT_FINGERPRINT")
  [ "$actual_fingerprint" = "$expected_fingerprint" ] || \
    fatal "Root CA fingerprint mismatch: expected $expected_fingerprint got $actual_fingerprint"

  grep -q '"name"[[:space:]]*:[[:space:]]*"ra@unicron"' "$STEP_CA_CONFIG" || \
    fatal "CA configuration does not contain required provisioner ra@unicron."
  grep -q "$actual_fingerprint" "$RA_CONFIG" || \
    fatal "RA configuration does not reference current root fingerprint."

  step certificate verify "$TRAEFIK_CERT" --roots "$STEP_CA_ROOT_CA_CERT" || \
    fatal "Traefik certificate does not verify against root CA."

  oldifs="$IFS"
  IFS=","
  for raw in ${TRAEFIK_CERT_SANS:-}; do
    san="$(trim "$raw")"
    [ -n "$san" ] || continue
    log "Info" "Validating Traefik certificate SAN: $san"
    step certificate verify "$TRAEFIK_CERT" --roots "$STEP_CA_ROOT_CA_CERT" --host "$san" || \
      fatal "Traefik certificate missing or invalid for SAN: $san"
  done
  IFS="$oldifs"
}

start_renew_daemon() {
  require_positive_int "TRAEFIK_RENEW_EXPIRES_IN_SECONDS" "$TRAEFIK_RENEW_EXPIRES_IN_SECONDS"
  [ -f "$POST_RENEW_TRAEFIK_SCRIPT" ] || fatal "Post-renew hook missing: $POST_RENEW_TRAEFIK_SCRIPT"
  chmod +x "$POST_RENEW_TRAEFIK_SCRIPT" 2>/dev/null || true
  [ -x "$POST_RENEW_TRAEFIK_SCRIPT" ] || fatal "Post-renew hook is not executable: $POST_RENEW_TRAEFIK_SCRIPT"

  log "Info" "Starting Traefik certificate renew daemon."
  step ca renew "$TRAEFIK_CERT" "$TRAEFIK_KEY" \
    --ca-url "https://unicron-stepca:9000" \
    --root "$STEP_CA_ROOT_CA_CERT" \
    --exec "$POST_RENEW_TRAEFIK_SCRIPT" \
    --expires-in "${TRAEFIK_RENEW_EXPIRES_IN_SECONDS}s" \
    --daemon &
  RENEW_PID=$!
  log "Info" "Traefik certificate renew daemon started with PID $RENEW_PID"
}

start_step_ca() {
  log "Info" "Starting step-ca runtime."
  step-ca --password-file "$STEP_CA_PW" "$STEP_CA_CONFIG" &
  STEP_CA_PID=$!
  log "Info" "step-ca started with PID $STEP_CA_PID"
}

wait_for_step_ca_health() {
  attempts=0
  max_attempts=60
  log "Info" "Waiting for step-ca health endpoint."
  until curl --fail -sk https://localhost:9000/health >/dev/null 2>&1; do
    if ! kill -0 "$STEP_CA_PID" 2>/dev/null; then
      wait "$STEP_CA_PID" || true
      fatal "step-ca exited before becoming healthy."
    fi
    attempts=$((attempts + 1))
    if [ "$attempts" -ge "$max_attempts" ]; then
      fatal "Timed out waiting for step-ca health endpoint."
    fi
    sleep 1
  done
  log "Info" "step-ca health endpoint is ready."
}

shutdown_children() {
  log "Info" "Received shutdown signal; stopping child processes."
  if [ -n "$RENEW_PID" ]; then
    kill "$RENEW_PID" 2>/dev/null || true
  fi
  if [ -n "$STEP_CA_PID" ]; then
    kill "$STEP_CA_PID" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
}

supervise_children() {
  trap 'shutdown_children; exit 143' TERM INT
  while :; do
    if ! kill -0 "$STEP_CA_PID" 2>/dev/null; then
      wait "$STEP_CA_PID"
      exit $?
    fi
    if [ -n "$RENEW_PID" ] && ! kill -0 "$RENEW_PID" 2>/dev/null; then
      log "Fatal" "Traefik certificate renew daemon exited unexpectedly."
      kill "$STEP_CA_PID" 2>/dev/null || true
      wait "$STEP_CA_PID" 2>/dev/null || true
      exit 1
    fi
    sleep 5
  done
}

validate_pki
sync_export_certs
start_step_ca
wait_for_step_ca_health
start_renew_daemon
supervise_children
