#!/bin/sh
set -eu

interval="${HEARTBEAT_INTERVAL_SECONDS:-10}"
tick=0

echo "{\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"service\":\"event-target\",\"level\":\"info\",\"message\":\"event target ready\",\"interval_seconds\":${interval}}"

trap 'echo "{\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"service\":\"event-target\",\"level\":\"info\",\"message\":\"event target received shutdown signal\"}"; exit 0' INT TERM

while true; do
  tick=$((tick + 1))
  echo "{\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"service\":\"event-target\",\"level\":\"info\",\"message\":\"event target heartbeat\",\"tick\":${tick}}"
  sleep "${interval}"
done
