#!/bin/bash

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

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [HERALD] ${level}$*"
}

spacer() { echo ""; echo ""; }

fatal() {
  if command -v spacer >/dev/null 2>&1; then
    spacer
  fi
  log "Fatal" "$1"
  exit_code="${HERALD_FATAL_EXIT_CODE:-1}"
  exit "$exit_code"
}

require_vars() {
  for v in "$@"; do
    if [ -z "${!v-}" ]; then
      fatal "$v is not set"
    fi
  done
}

build_san_ext() {
  local sans_raw="$1"
  local spiffe="spiffe://unicron/herald/${HERALD_ID}"
  local entries=()
  IFS=',' read -ra parts <<< "$sans_raw"
  for part in "${parts[@]}"; do
    part=$(echo "$part" | sed 's/^ *//;s/ *$//')
    [ -z "$part" ] && continue
    case "$part" in
      spiffe://*) entries+=("URI:$part") ;;
      *[0-9].[0-9]*|*:*:*) entries+=("IP:$part") ;;
      *) entries+=("DNS:$part") ;;
    esac
  done
  entries+=("URI:${spiffe}")
  entries+=("DNS:herald-${HERALD_ID}")
  entries+=("DNS:unicron.central")
  local joined
  joined=$(IFS=,; echo "${entries[*]}")
  echo "subjectAltName=${joined}"
}

write_csr() {
  local mode="$1"
  local san_ext
  san_ext=$(build_san_ext "$HERALD_CERT_SUBJECTS")
  case "$mode" in
    new)
      log "Info" "Generating key + CSR with SANs: $san_ext"
      openssl req \
        -new \
        -newkey rsa:2048 \
        -nodes \
        -keyout "$HERALD_KEY" \
        -subj "/CN=herald-${HERALD_ID}" \
        -addext "$san_ext" \
        -out "$HERALD_CSR"
      ;;
    existing)
      log "Info" "Generating CSR with existing key and SANs: $san_ext"
      openssl req \
        -new \
        -key "$HERALD_KEY" \
        -subj "/CN=herald-${HERALD_ID}" \
        -addext "$san_ext" \
        -out "$HERALD_CSR"
      ;;
    *)
      fatal "Unknown CSR mode: $mode"
      ;;
  esac
}

write_cert_from_response() {
  local resp="$1"
  local cert chain
  cert=$(printf '%s' "$resp" | jq -r '.cert_pem')
  chain=$(printf '%s' "$resp" | jq -r '.chain_pem')
  if [ -z "$cert" ] || [ "$cert" = "null" ]; then
    fatal "Certificate response missing cert_pem"
  fi
  if [ -z "$chain" ] || [ "$chain" = "null" ]; then
    chain=""
  fi
  printf "%s\n%s" "$cert" "$chain" > "$HERALD_CERT"
  log "Info" "Wrote certificate bundle to $HERALD_CERT"
}

request_cert() {
  local url="$1"
  local auth_mode="$2"
  local body resp

  body=$(jq -n --arg csr "$(cat "$HERALD_CSR")" --argjson not_after "$HERALD_CERT_NOT_AFTER_SECONDS" \
    '{csr_pem:$csr,not_after_seconds:$not_after}')

  case "$auth_mode" in
    bearer)
      resp=$(
        curl --silent --show-error \
          --cacert "$HERALD_CA_ROOT" \
          -H "Authorization: Bearer $HERALD_ENROLL_TOKEN" \
          -H "Content-Type: application/json" \
          -d "$body" \
          "$url"
      )
      ;;
    mtls)
      resp=$(
        curl --silent --show-error \
          --cert "$HERALD_CERT" --key "$HERALD_KEY" \
          --cacert "$HERALD_CA_ROOT" \
          -H "Content-Type: application/json" \
          -d "$body" \
          "$url"
      )
      ;;
    *)
      fatal "Unknown cert auth mode: $auth_mode"
      ;;
  esac

  write_cert_from_response "$resp"
}

issue_cert() {
  local csr_mode="$1"
  local url="$2"
  local auth_mode="$3"
  write_csr "$csr_mode"
  request_cert "$url" "$auth_mode"
}
