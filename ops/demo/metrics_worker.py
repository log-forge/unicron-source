#!/usr/bin/env python3

import hashlib
import json
import os
import pathlib
import time
import urllib.error
import urllib.request


MEMORY_ALLOC_MB = int(os.environ.get("MEMORY_ALLOC_MB", "24"))
METRICS_INTERVAL_SECONDS = float(os.environ.get("METRICS_INTERVAL_SECONDS", "12"))
TARGET_URL = os.environ.get("TARGET_URL", "http://unicron-demo-web:8080/healthz")
SCRATCH_FILE = pathlib.Path("/tmp/unicron-demo-metrics.bin")


def emit(level: str, message: str, **fields: object) -> None:
    payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "service": "metrics-worker",
        "level": level,
        "message": message,
    }
    payload.update(fields)
    print(json.dumps(payload, sort_keys=True), flush=True)


def run_cpu_burst() -> int:
    iterations = 0
    block = os.urandom(1024 * 1024)
    deadline = time.monotonic() + 2.5
    while time.monotonic() < deadline:
        hashlib.sha256(block).hexdigest()
        iterations += 1
    return iterations


def hit_demo_web() -> list[object]:
    statuses: list[object] = []
    for _ in range(3):
        try:
            with urllib.request.urlopen(TARGET_URL, timeout=3) as response:
                statuses.append(response.status)
        except urllib.error.URLError as exc:
            statuses.append(f"error:{exc.reason}")
        except Exception as exc:
            statuses.append(f"error:{exc}")
        time.sleep(0.2)
    return statuses


def main() -> None:
    emit(
        "info",
        "metrics worker ready",
        target_url=TARGET_URL,
        memory_alloc_mb=MEMORY_ALLOC_MB,
    )

    cycle = 0
    while True:
        cycle += 1
        started = time.monotonic()
        scratch_buffer = bytearray(MEMORY_ALLOC_MB * 1024 * 1024)
        hash_iterations = run_cpu_burst()
        SCRATCH_FILE.write_bytes(os.urandom(2 * 1024 * 1024))
        statuses = hit_demo_web()
        scratch_buffer[0:4] = b"demo"

        emit(
            "info",
            "metrics cycle complete",
            cycle=cycle,
            allocated_mb=MEMORY_ALLOC_MB,
            cpu_iterations=hash_iterations,
            http_statuses=statuses,
            scratch_file=str(SCRATCH_FILE),
        )

        del scratch_buffer
        elapsed = time.monotonic() - started
        time.sleep(max(0.0, METRICS_INTERVAL_SECONDS - elapsed))


if __name__ == "__main__":
    main()
