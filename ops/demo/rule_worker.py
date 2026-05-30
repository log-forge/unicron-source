#!/usr/bin/env python3

import json
import os
import pathlib
import signal
import time


STATE_DIR = pathlib.Path(os.environ.get("DEMO_STATE_DIR", "/tmp/unicron-demo"))
HEARTBEAT_INTERVAL_SECONDS = float(os.environ.get("NORMAL_INTERVAL_SECONDS", "15"))
POLL_INTERVAL_SECONDS = 0.5
DEFAULT_BURST_COUNT = 5

running = True


def emit(level: str, message: str, **fields: object) -> None:
    payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "service": "rule-worker",
        "level": level,
        "message": message,
    }
    payload.update(fields)
    print(json.dumps(payload, sort_keys=True), flush=True)


def request_stop(signum: int, _frame: object) -> None:
    global running
    emit("info", "rule worker received shutdown signal", signal=signum)
    running = False


def _consume(flag_name: str) -> bool:
    flag_path = STATE_DIR / flag_name
    if not flag_path.exists():
        return False
    flag_path.unlink(missing_ok=True)
    return True


def _read_burst_count() -> int:
    count_path = STATE_DIR / "emit-burst-count"
    try:
        count = int(count_path.read_text(encoding="utf-8").strip())
        return max(1, count)
    except Exception:
        return DEFAULT_BURST_COUNT
    finally:
        count_path.unlink(missing_ok=True)


def emit_requested_logs() -> None:
    if _consume("emit-main"):
        emit(
            "info",
            "DEMO_FLOW_TRIGGER manual remediation trigger emitted",
            keyword="DEMO_FLOW_TRIGGER",
            trigger_kind="main",
        )

    if _consume("emit-error"):
        emit(
            "error",
            "DEMO_ERROR_TRIGGER synthetic error pattern emitted",
            keyword="DEMO_ERROR_TRIGGER",
            trigger_kind="error",
        )

    if _consume("emit-warning"):
        emit(
            "warning",
            "DEMO_WARNING_TRIGGER synthetic warning pattern emitted",
            keyword="DEMO_WARNING_TRIGGER",
            trigger_kind="warning",
        )

    if _consume("emit-burst"):
        count = _read_burst_count()
        emit(
            "info",
            "DEMO_BURST_TRIGGER starting synthetic burst",
            trigger_kind="burst",
            burst_count=count,
        )
        for index in range(count):
            emit(
                "info",
                "DEMO_FLOW_TRIGGER burst remediation trigger emitted",
                keyword="DEMO_FLOW_TRIGGER",
                trigger_kind="burst",
                sequence=index + 1,
                total=count,
            )
            time.sleep(0.15)


def main() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    emit(
        "info",
        "rule worker ready",
        state_dir=str(STATE_DIR),
        heartbeat_interval_seconds=HEARTBEAT_INTERVAL_SECONDS,
    )

    next_heartbeat_at = time.monotonic()
    heartbeat_tick = 0

    while running:
        now = time.monotonic()
        if now >= next_heartbeat_at:
            heartbeat_tick += 1
            emit(
                "info",
                "rule worker heartbeat",
                tick=heartbeat_tick,
                status="ready",
            )
            next_heartbeat_at = now + HEARTBEAT_INTERVAL_SECONDS

        emit_requested_logs()
        time.sleep(POLL_INTERVAL_SECONDS)

    emit("info", "rule worker exiting cleanly")


if __name__ == "__main__":
    main()
