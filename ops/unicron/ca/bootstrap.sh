#!/bin/sh
set -eu

STEPPATH=${STEPPATH:-/home/step}
STEPPATH_CERTS=$STEPPATH/certs
STEPPATH_SECRETS=$STEPPATH/secrets
STEPPATH_PUBLIC=$STEPPATH/public
STEPPATH_CONFIG=$STEPPATH/config

POST_RENEW_TRAEFIK_SCRIPT=$STEPPATH/post-renew-traefik.sh
BOOTSTRAP_STAMP=$STEPPATH/.bootstrapped
RA_DB_PATH=$STEPPATH/ra-db

# Certs
STEP_CA_ROOT_CA_CERT=$STEPPATH_CERTS/root_ca.crt
STEP_CA_ROOT_FINGERPRINT=$STEPPATH_CERTS/root_ca_fingerprint.txt
TRAEFIK_CERT=$STEPPATH_CERTS/unicron-traefik-leaf.crt
TRAEFIK_KEY=$STEPPATH_CERTS/unicron-traefik-leaf.key
LOCALHOST_CERT=$STEPPATH_CERTS/unicron-localhost-leaf.crt
LOCALHOST_KEY=$STEPPATH_CERTS/unicron-localhost-leaf.key

# Secrets
STEP_CA_PW=$STEPPATH_SECRETS/ca.jwk.pw
STEP_CA_PROVISIONER_PW=$STEPPATH_SECRETS/provisioner.jwk.pw
RA_JWK_PW=$STEPPATH_SECRETS/ra.jwk.pw
RA_JWK_JSON=$STEPPATH_SECRETS/ra.jwk.json

# Public keys
RA_JWK_JSON_PUB=$STEPPATH_PUBLIC/ra.jwk.json.pub

# Step CA configs
STEP_CA_CONFIG=$STEPPATH_CONFIG/ca.json
RA_CONFIG=$STEPPATH_CONFIG/ra-ca.json

# Export directories for least-privilege mounts
STEPPATH_TRUST=$STEPPATH/trust
STEPPATH_TRAEFIK_EXPORT=$STEPPATH/traefik-certs
STEPPATH_RA_PROVISIONER_EXPORT=$STEPPATH/ra-provisioner

# Provisioner renewal defaults (overridable via environment)
RA_DEFAULT_TLS_CERT_DURATION=${RA_DEFAULT_TLS_CERT_DURATION:-"24h"}
RA_MAX_TLS_CERT_DURATION=${RA_MAX_TLS_CERT_DURATION:-"168h"}
TRAEFIK_RENEW_EXPIRES_IN_SECONDS=${TRAEFIK_RENEW_EXPIRES_IN_SECONDS:-28800}
TRAEFIK_CERT_NOT_AFTER_SECONDS=${TRAEFIK_CERT_NOT_AFTER_SECONDS:-43200}

# Function to log with timestamp. Usage:
# log "message"            # no level
# log Info "message"       # with level
log() {
  if [ $# -eq 0 ]; then
    return 0
  fi

  case "$1" in
    Debug|Info|Warn|Warning|Error|Fatal)
      level="[$1] "
      shift
      ;;
    *)
      level=""
      ;;
  esac

  msg="$*"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [BOOTSTRAP] $level $msg";
}

# Strict flow control (always fatal)
fatal() {
  log "Fatal" "$1";
  exit 1;
}

# Simple spacer for log readability
spacer() {
  echo "";
  echo "";
}

# Require a strictly positive integer; fatal with a helpful message otherwise
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

csv_to_flags() {
  flag="$1"
  csv="$2"
  result=""
  oldifs="$IFS"
  IFS=","
  for raw in $csv; do
    value="$(trim "$raw")"
    [ -n "$value" ] || continue
    result="$result $flag $value"
  done
  IFS="$oldifs"
  printf '%s' "$result"
}

csv_to_json_strings() {
  csv="$1"
  result=""
  oldifs="$IFS"
  IFS=","
  for raw in $csv; do
    value="$(trim "$raw")"
    [ -n "$value" ] || continue
    if [ -n "$result" ]; then
      result="$result, "
    fi
    result="$result\"$value\""
  done
  IFS="$oldifs"
  printf '%s' "$result"
}

verify_traefik_sans() {
  oldifs="$IFS"
  IFS=","
  for raw in ${TRAEFIK_CERT_SANS:-}; do
    san="$(trim "$raw")"
    [ -n "$san" ] || continue
    log "Info" "Verifying Traefik certificate for SAN: $san"
    step certificate verify "$TRAEFIK_CERT" --roots "$STEP_CA_ROOT_CA_CERT" --host "$san" || \
      fatal "Traefik certificate verification for SAN '$san' failed."
  done
  IFS="$oldifs"
}

# Export validated material for other services through least-privilege mounts.
sync_export_certs() {
  spacer
  log "Info" "Exporting validated material for least-privilege mounts..."
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

  # Ask Traefik to reload dynamic config so updated cert material is picked up.
  TARGET_FILE="${TRAEFIK_DYNAMIC_CONFIG_FILE:-/etc/traefik/shared/traefik-config.yaml}"
  if touch "$TARGET_FILE" 2>/dev/null; then
    log "Info" "Touched $TARGET_FILE to trigger Traefik reload"
  else
    log "Warn" "Could not touch $TARGET_FILE; Traefik may continue serving stale cert until next config reload"
  fi
}

has_any_pki_material() {
  for file in \
    "$STEP_CA_CONFIG" \
    "$STEP_CA_ROOT_CA_CERT" \
    "$STEPPATH_CERTS/intermediate_ca.crt" \
    "$STEPPATH_SECRETS/root_ca_key" \
    "$STEPPATH_SECRETS/intermediate_ca_key" \
    "$RA_JWK_JSON" \
    "$RA_JWK_JSON_PUB" \
    "$RA_CONFIG" \
    "$TRAEFIK_CERT" \
    "$TRAEFIK_KEY" \
    "$LOCALHOST_CERT" \
    "$LOCALHOST_KEY"; do
    if [ -e "$file" ]; then
      return 0
    fi
  done
  return 1
}

log "Info" "Starting unicron bootstrap process..."

# Check if required files exist
spacer
log "Info" "Checking for presence of CA and provisioner password files..."
for secret in "$STEP_CA_PW" "$STEP_CA_PROVISIONER_PW" "$RA_JWK_PW"; do
  if [ ! -f "$secret" ] || [ ! -s "$secret" ]; then
    fatal "Required secret file not found: $secret"
  fi
done

# Validate required renew/cert durations
log "Info" "Validating TRAEFIK_RENEW_EXPIRES_IN_SECONDS and TRAEFIK_CERT_NOT_AFTER_SECONDS..."
require_positive_int "TRAEFIK_RENEW_EXPIRES_IN_SECONDS" "$TRAEFIK_RENEW_EXPIRES_IN_SECONDS"
require_positive_int "TRAEFIK_CERT_NOT_AFTER_SECONDS" "$TRAEFIK_CERT_NOT_AFTER_SECONDS"
if [ "$TRAEFIK_RENEW_EXPIRES_IN_SECONDS" -ge "$TRAEFIK_CERT_NOT_AFTER_SECONDS" ]; then
  fatal "TRAEFIK_RENEW_EXPIRES_IN_SECONDS ($TRAEFIK_RENEW_EXPIRES_IN_SECONDS) must be less than TRAEFIK_CERT_NOT_AFTER_SECONDS ($TRAEFIK_CERT_NOT_AFTER_SECONDS)."
fi

# Ensure the post-renew hook exists and is executable (required for live reload)
log "Info" "Checking post-renew hook script at $POST_RENEW_TRAEFIK_SCRIPT..."
if [ ! -f "$POST_RENEW_TRAEFIK_SCRIPT" ]; then
  fatal "Post-renew hook not found: $POST_RENEW_TRAEFIK_SCRIPT"
fi
if [ ! -x "$POST_RENEW_TRAEFIK_SCRIPT" ]; then
  chmod +x "$POST_RENEW_TRAEFIK_SCRIPT" 2>/dev/null || true
  if [ ! -x "$POST_RENEW_TRAEFIK_SCRIPT" ]; then
    fatal "Post-renew hook is not executable: $POST_RENEW_TRAEFIK_SCRIPT"
  fi
fi

# If the bootstrap stamp file exists, skip the bootstrap steps and exec step-ca directly
if [ -f "$BOOTSTRAP_STAMP" ]; then
  spacer
  log "Info" "Bootstrap stamp file $BOOTSTRAP_STAMP found; validating existing PKI material."

  # Check if certs exist and fail fatal if not (aggregate missing files into one error)
  missing_files=""
  for file_info in \
    "$STEP_CA_ROOT_CA_CERT:root CA certificate" \
    "$STEP_CA_CONFIG:CA configuration file" \
    "$STEP_CA_ROOT_FINGERPRINT:root CA fingerprint file" \
    "$RA_JWK_JSON:RA JWK JSON" \
    "$RA_JWK_JSON_PUB:RA JWK JSON public key" \
    "$TRAEFIK_CERT:Traefik certificate" \
    "$TRAEFIK_KEY:Traefik private key" \
    "$LOCALHOST_CERT:localhost certificate" \
    "$LOCALHOST_KEY:localhost private key"; do
    file=${file_info%%:*}
    desc=${file_info#*:}
    if [ ! -s "$file" ]; then
      log "Error" "Missing or empty file: $file ($desc)"
      if [ -z "$missing_files" ]; then
        missing_files="$file ($desc)"
      else
        missing_files="$missing_files; $file ($desc)"
      fi
    fi
  done
  if [ -n "$missing_files" ]; then
    fatal "One or more required cert/key files are missing or empty: $missing_files. Restore a valid PKI backup or intentionally recreate the PKI volume."
  fi

  # Validate Traefik cert and SANs. Runtime renewal is owned by runtime.sh.
  log "Info" "Verifying Traefik certificate"
  step certificate verify "$TRAEFIK_CERT" --roots "$STEP_CA_ROOT_CA_CERT" || fatal "Traefik certificate verification failed."
  verify_traefik_sans

  # Export certs after validation so shared volumes match the canonical PKI volume.
  sync_export_certs

  log "Info" "PKI initialization already complete and valid."
  exit 0
fi

# Log all environment variables (for debugging purposes)
spacer
log "Info" "Environment Variables:"
env | while IFS= read -r line; do log "Info" "$line"; done

# Create --san flags for Step CA init command
spacer
log "Info" "Transforming environment variables for Step CA and Traefik SANs..."
step_ca_dns="$(csv_to_flags "--dns" "${STEP_CA_DNS:-}")"
log "Info" "Transformed STEP_CA_DNS to step_ca_dns: $step_ca_dns"
step_ca_ra_dns="$(csv_to_flags "--dns" "${STEP_RA_DNS:-}")"
log "Info" "Transformed STEP_RA_DNS to step_ca_ra_dns: $step_ca_ra_dns"
step_ca_ra_dns_array="$(csv_to_json_strings "${STEP_RA_DNS:-}")"
log "Info" "Transformed STEP_RA_DNS to step_ca_ra_dns_array: $step_ca_ra_dns_array"
traefik_cert_sans="$(csv_to_flags "--san" "${TRAEFIK_CERT_SANS:-}")"
log "Info" "Transformed TRAEFIK_CERT_SANS to traefik_cert_sans: $traefik_cert_sans"

# Create directories and files if they don't exist
spacer
log "Info" "Ensuring necessary directories and files exist..."
for dir in "$STEPPATH_CERTS" "$STEPPATH_SECRETS" "$STEPPATH_PUBLIC" "$STEPPATH_CONFIG" "$RA_DB_PATH"; do
  if [ -n "$dir" ]; then
    log "Info" "Creating directory if it doesnt exist: $dir"
    mkdir -p "$dir"
  fi
  if [ "$dir" = "$RA_DB_PATH" ]; then
    log "Info" "Setting ownership of RA DB path ($RA_DB_PATH) to UID 1000:GID 1000"
    chown 1000:1000 "$RA_DB_PATH"
  fi
done

# Initialize Step CA PKI. Production bootstrap is intentionally fail-closed:
# partial PKI material without the bootstrap stamp requires operator action,
# not silent repair or overwrite.
spacer
if has_any_pki_material; then
  fatal "PKI material exists but bootstrap stamp $BOOTSTRAP_STAMP is missing. Refusing to initialize over partial state. Restore a valid backup, create the stamp only after validation, or intentionally remove the PKI volumes and rerun init."
fi
log "Info" "Initializing Step CA PKI..."
step ca init \
  --deployment-type standalone \
  --name "unicron CA" \
  $step_ca_dns \
  --address ":9000" \
  --provisioner admin \
  --password-file "$STEP_CA_PW" \
  --provisioner-password-file "$STEP_CA_PROVISIONER_PW" \
  --no-db

# Print and store the fingerprint of a certificate
spacer
log "Info" "Storing root CA fingerprint to $STEP_CA_ROOT_FINGERPRINT"
ca_root_fingerprint=$(step certificate fingerprint "$STEP_CA_ROOT_CA_CERT")
log "Info" "Root CA Fingerprint: $ca_root_fingerprint"
echo "$ca_root_fingerprint" > "$STEP_CA_ROOT_FINGERPRINT"

# Create JWKs (JSON Web Keys) for Step RA (Registration Authority)
spacer
if [ -s "$RA_JWK_JSON_PUB" ] && [ -s "$RA_JWK_JSON" ]; then
  log "Info" "Existing Step RA JWK files found; skipping JWK generation."
else
  log "Info" "Creating JWK for Step RA"
  rm -f "$RA_JWK_JSON_PUB" "$RA_JWK_JSON"
  step crypto jwk create \
    "$RA_JWK_JSON_PUB" "$RA_JWK_JSON" \
    --kty OKP --curve Ed25519 \
    --password-file "$RA_JWK_PW"
fi

# Create configuration file for an RA that uses the JWK provisioner to connect to the CA
# ${UNICRON_CENTRAL_FQDN:-unicron.central}
spacer
log "Info" "Creating RA configuration file at $RA_CONFIG:"
cat > "$RA_CONFIG" <<EOF
{
  "address": ":9100",
  "dnsNames": [${step_ca_ra_dns_array}],
  "logger": {
    "format": "text",
    "level": "debug"
  },
  "db": {
    "type": "badgerV2",
    "dataSource": "$RA_DB_PATH"
  },
  "authority": {
    "type": "stepcas",
    "certificateAuthority": "https://${UNICRON_CENTRAL_FQDN:-unicron.central}:9000",
    "certificateAuthorityFingerprint": "$ca_root_fingerprint",
    "certificateIssuer": {
      "type": "jwk",
      "provisioner": "ra@unicron"
    },
    "provisioners": [
      {
        "type": "JWK",
        "name": "ra@unicron",
        "key": $(cat "$RA_JWK_JSON_PUB")
      }
    ]
  }
}
EOF
cat "$RA_CONFIG"

# Add JWK 'ra@unicron' provisioner to the CA configuration
spacer
if grep -q '"name"[[:space:]]*:[[:space:]]*"ra@unicron"' "$STEP_CA_CONFIG"; then
  log "Info" "JWK provisioner 'ra@unicron' already present in the CA configuration; skipping provisioner add."
else
  log "Info" "Adding JWK provisioner 'ra@unicron' to the CA"
  step ca provisioner add ra@unicron \
    --type=JWK \
    --private-key "$RA_JWK_JSON" \
    --public-key "$RA_JWK_JSON_PUB" \
    --password-file "$RA_JWK_PW" \
    --allow-renewal-after-expiry \
    --x509-default-dur "$RA_DEFAULT_TLS_CERT_DURATION" \
    --x509-max-dur "$RA_MAX_TLS_CERT_DURATION" \
    --ca-config "$STEP_CA_CONFIG"
fi

# Generate a new private key and certificate signed by the root certificate for Traefik and Dev
spacer
log "Info" "Generating Traefik certificate signed by the root CA"
step ca certificate \
  unicron-traefik \
  "$TRAEFIK_CERT" \
  "$TRAEFIK_KEY" \
  --offline \
  --force \
  --ca-config "$STEP_CA_CONFIG" \
  $traefik_cert_sans \
  --password-file "$STEP_CA_PW" \
  --provisioner "ra@unicron" \
  --provisioner-password-file "$RA_JWK_PW" \
  --not-after ${TRAEFIK_CERT_NOT_AFTER_SECONDS}s || fatal "Failed to generate Traefik certificate"
# Verify the generated Traefik certificate
log "Info" "Verifying Traefik certificate:"
verify_traefik_sans

# Issue a Dev localhost certificate for testing purposes
spacer
log "Info" "Issuing a development localhost certificate for testing purposes"
step ca certificate \
  unicron-localhost \
  "$LOCALHOST_CERT" \
  "$LOCALHOST_KEY" \
  --offline \
  --force \
  --ca-config "$STEP_CA_CONFIG" \
  $traefik_cert_sans \
  --san spiffe://unicron/herald/localhost-herald-id \
  --san spiffe://unicron/herald/localhost-herald-common-name \
  --password-file "$STEP_CA_PW" \
  --provisioner "ra@unicron" \
  --provisioner-password-file "$RA_JWK_PW"

# Export public certs for other services
sync_export_certs

spacer
log "Info" "Creating bootstrap stamp file: $BOOTSTRAP_STAMP"
touch "$BOOTSTRAP_STAMP"

# # Idempotent permissions: if 'step' user exists, chown directories/files to it and set safe perms
# spacer
# log "Info" "Checking for presence of 'step' user to set ownership and permissions"
# if id step >/dev/null 2>&1; then
#   log "Info" "Setting ownership to 'step' and applying safe permissions"
#   # create a group that Traefik can be added to for read-only cert access
#   if ! getent group stepgroup >/dev/null 2>&1; then
#     addgroup -S stepgroup || true
#     # add step user to stepgroup
#     usermod -a -G stepgroup step || true
#   fi

#   # set ownership to step:stepgroup so that group can read certs
#   chown -R step:stepgroup "$STEPPATH" || true

#   # restrict secrets to owner only 
#   chmod 700 "$STEPPATH_SECRETS" || true
#   find "$STEPPATH_SECRETS" -type f -exec chmod 600 {} \; || true

#   # certs: owner rwx, group rx (so Traefik in stepgroup can read), others none
#   find "$STEPPATH_CERTS" -type d -exec chmod 750 {} \; || true
#   find "$STEPPATH_CERTS" -type f -exec chmod 640 {} \; || true

#   # config dir: owner rwx, group rx
#   chmod 750 "$STEPPATH_CONFIG" || true
# else
#   log "Info" "User 'step' not present; skipping chown/chmod steps"
# fi
# log "Info" "Current ownership and permissions of $STEPPATH:"
# ls -lR "$STEPPATH" || true

spacer
log "Info" "PKI initialization complete. Runtime startup is handled by runtime.sh."
exit 0
