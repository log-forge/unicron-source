"""Redis stream backpressure helpers for notifier health endpoints."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.redis import get_redis

_STATUS_RANK = {"ok": 0, "warning": 1, "critical": 2, "unknown": 3}


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_str(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value) if value is not None else ""


def _merge_status(current: str, candidate: str) -> str:
    if _STATUS_RANK.get(candidate, 0) > _STATUS_RANK.get(current, 0):
        return candidate
    return current


async def collect_notifier_stream_backpressure() -> dict[str, Any]:
    """Collect lag/pending/DLQ counters for notifier stream consumption."""
    try:
        redis = await get_redis()
    except Exception as exc:
        return {
            "status": "unknown",
            "streams": {},
            "totals": {"pending": 0, "lag": 0, "dlq_depth": 0},
            "alerts": [f"redis unavailable for stream metrics: {exc}"],
            "error": str(exc),
        }

    stream = settings.REDIS_STREAM_ALERTS
    group = settings.REDIS_CONSUMER_GROUP
    dlq_stream = settings.REDIS_STREAM_ALERTS_DLQ

    try:
        stream_length = _to_int(await redis.xlen(stream), 0)
    except Exception:
        stream_length = 0

    try:
        dlq_depth = _to_int(await redis.xlen(dlq_stream), 0)
    except Exception:
        dlq_depth = 0

    pending = 0
    lag_value: int | None = None
    consumers = 0
    try:
        groups = await redis.xinfo_groups(stream)
        for raw in groups or []:
            if _to_str(raw.get("name")) != group:
                continue
            pending = _to_int(raw.get("pending"), 0)
            lag_raw = raw.get("lag")
            lag_value = _to_int(lag_raw, 0) if lag_raw is not None else None
            consumers = _to_int(raw.get("consumers"), 0)
            break
    except Exception:
        pass

    lag_estimated = lag_value is None
    lag = _to_int(lag_value, stream_length if lag_estimated else 0)

    status = "ok"
    alerts: list[str] = []
    if pending >= settings.STREAM_PENDING_CRITICAL:
        status = _merge_status(status, "critical")
        alerts.append(f"pending={pending} (critical)")
    elif pending >= settings.STREAM_PENDING_WARN:
        status = _merge_status(status, "warning")
        alerts.append(f"pending={pending} (warning)")

    if lag >= settings.STREAM_LAG_CRITICAL:
        status = _merge_status(status, "critical")
        alerts.append(f"lag={lag} (critical)")
    elif lag >= settings.STREAM_LAG_WARN:
        status = _merge_status(status, "warning")
        alerts.append(f"lag={lag} (warning)")

    if dlq_depth >= settings.STREAM_DLQ_CRITICAL:
        status = _merge_status(status, "critical")
        alerts.append(f"dlq={dlq_depth} (critical)")
    elif dlq_depth >= settings.STREAM_DLQ_WARN:
        status = _merge_status(status, "warning")
        alerts.append(f"dlq={dlq_depth} (warning)")

    return {
        "status": status,
        "streams": {
            "alerts": {
                "stream": stream,
                "consumer_group": group,
                "length": stream_length,
                "pending": pending,
                "lag": lag,
                "lag_estimated": lag_estimated,
                "consumers": consumers,
                "dlq_stream": dlq_stream,
                "dlq_depth": dlq_depth,
                "status": status,
            }
        },
        "totals": {
            "pending": pending,
            "lag": lag,
            "dlq_depth": dlq_depth,
        },
        "alerts": [f"alerts: {entry}" for entry in alerts],
    }
