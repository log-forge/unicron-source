#!/usr/bin/env bash
# Herald ingestion self-check: attempts to insert one log line and one metric
# into VictoriaLogs and VictoriaMetrics via Traefik mTLS routing.
# Non-fatal: emits PASS/FAIL but does not exit non‑zero (unless hard failure logic changed).

set -euo pipefail

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [HERALD-INGEST] $*"; }

if [ "${HERALD_INGEST_CHECK_DISABLE:-0}" = "1" ]; then
  log "Ingestion check disabled via HERALD_INGEST_CHECK_DISABLE=1"
  exit 0
fi


# Preconditions: require TLS artifacts and herald id. Require at least one central URL.
for v in HERALD_CERT HERALD_KEY HERALD_CA_ROOT HERALD_ID; do
  val="${!v:-}"
  if [ -z "$val" ]; then
    log "Skip: missing env $v"
    exit 0
  fi
done

if [ -z "${CENTRAL_MTLS_URL:-}" ] && [ -z "${CENTRAL_URL:-}" ]; then
  log "Skip: missing CENTRAL_MTLS_URL and CENTRAL_URL"
  exit 0
fi

# Prefer CENTRAL_MTLS_URL (mTLS endpoint) if provided, otherwise use CENTRAL_URL.
BASE_URL="${CENTRAL_MTLS_URL:-${CENTRAL_URL}}"
BASE_URL="${BASE_URL%/}"

LOGS_URL="$BASE_URL/unicron/victoria-logs/insert/jsonline?_stream_fields=source&_msg_field=log&_time_field=date"
# Remote write expects protobuf snappy body; our simple plaintext line won't work (HTTP 400).
# Use /api/v1/import/prometheus for single text line ingestion instead.
METRICS_URL="$BASE_URL/unicron/victoria-metrics/api/v1/import/prometheus"

ISO_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EPOCH=$(date +%s)
LOG_PAYLOAD="{\"source\":\"herald-ingest-check\",\"log\":\"HERALD_INGEST_CHECK_LOG\",\"date\":\"$ISO_TS\",\"herald_id\":\"$HERALD_ID\"}"
METRIC_LINE="herald_ingest_check_metric{herald_id=\"$HERALD_ID\"} 1 $EPOCH"

# OTLP HTTP trace check
OTLP_TRACE_URL="$BASE_URL/unicron/otel/v1/traces"
# Minimal ExportTraceServiceRequest JSON (see OTLP protobuf definition). Trace/span IDs must be hex.
OTLP_TRACE_PAYLOAD=$(cat <<'JSON'
{
  "resourceSpans": [
    {
      "resource": {
        "attributes": [
          {"key": "service.name", "value": {"stringValue": "herald-ingest-check"}},
          {"key": "herald.id", "value": {"stringValue": "%HERALD_ID%"}}
        ]
      },
      "scopeSpans": [
        {
          "scope": {"name": "ingest.check"},
          "spans": [
            {
              "traceId": "00000000000000000000000000000002",
              "spanId": "0000000000000002",
              "name": "herald.ingest.check",
              "startTimeUnixNano": %START_TIME%,
              "endTimeUnixNano": %END_TIME%,
              "attributes": [
                {"key": "herald_id", "value": {"stringValue": "%HERALD_ID%"}},
                {"key": "ingest.check", "value": {"boolValue": true}}
              ]
            }
          ]
        }
      ]
    }
  ]
}
JSON
)
NOW_NANO=$(($(date +%s%N)))
END_NANO=$((NOW_NANO + 5000000)) # +5ms
OTLP_TRACE_PAYLOAD=${OTLP_TRACE_PAYLOAD//%HERALD_ID%/${HERALD_ID}}
OTLP_TRACE_PAYLOAD=${OTLP_TRACE_PAYLOAD//%START_TIME%/$NOW_NANO}
OTLP_TRACE_PAYLOAD=${OTLP_TRACE_PAYLOAD//%END_TIME%/$END_NANO}

attempt_curl_otlp_trace() {
  local url="$1"; shift
  curl --silent --show-error --cacert "$HERALD_CA_ROOT" --cert "$HERALD_CERT" --key "$HERALD_KEY" \
    -o /dev/stderr -w "INGEST_HTTP_CODE=%{http_code}\n" \
    -H 'Content-Type: application/json' -X POST --data "$OTLP_TRACE_PAYLOAD" "$url" 2>&1
}

attempt_curl_json() {
  local url="$1"; shift
  curl --silent --show-error --cacert "$HERALD_CA_ROOT" --cert "$HERALD_CERT" --key "$HERALD_KEY" \
    -o /dev/stderr -w "INGEST_HTTP_CODE=%{http_code}\n" \
    -H 'Content-Type: application/json' -X POST --data "$LOG_PAYLOAD" "$url" 2>&1
}

attempt_curl_metric() {
  local url="$1"; shift
  curl --silent --show-error --cacert "$HERALD_CA_ROOT" --cert "$HERALD_CERT" --key "$HERALD_KEY" \
    -o /dev/stderr -w "INGEST_HTTP_CODE=%{http_code}\n" \
    -H 'Content-Type: text/plain' -X POST --data-raw "$METRIC_LINE" "$url" 2>&1
}

retry() {
  local name="$1"; shift
  local max="$1"; shift
  local func="$1"; shift
  local url="$1"; shift
  local attempt=1
  local delay=2
  while [ $attempt -le $max ]; do
    log "Attempt $attempt/$max: $name -> $url"
    out=$($func "$url" || true)
    code=$(printf '%s' "$out" | awk -F= '/INGEST_HTTP_CODE/ {print $2}' | tail -n1)
    if [ -n "$code" ] && [[ "$code" =~ ^2 ]]; then
      log "PASS: $name (HTTP $code)"
      return 0
    fi
    log "WARN: $name failed (HTTP ${code:-?}); retry in ${delay}s"
    sleep $delay
    delay=$(( delay * 2 ))
    attempt=$(( attempt + 1 ))
  done
  log "FAIL: $name after $max attempts"
  return 1
}

# Run checks (non-fatal aggregate)
RC=0
retry "logs-insert" 4 attempt_curl_json "$LOGS_URL" || RC=1
retry "metrics-insert" 4 attempt_curl_metric "$METRICS_URL" || RC=1
# retry "otlp-trace" 4 attempt_curl_otlp_trace "$OTLP_TRACE_URL" || RC=1

if [ $RC -eq 0 ]; then
  log "Ingestion check COMPLETE: all passed"
else
  log "Ingestion check COMPLETE: some failures (see above)."
fi
exit 0
