"""Backpressure and ingest visibility helpers for health endpoints."""

from __future__ import annotations

import re
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis

logger = get_logger("alert-engine.services.stream_metrics")

_STATUS_RANK = {"ok": 0, "warning": 1, "critical": 2, "unknown": 3}
_PROM_LINE_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{[^}]*\})?\s+(?P<value>[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)"
)


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


async def _safe_xlen(redis, stream: str) -> int:
    try:
        return _to_int(await redis.xlen(stream), 0)
    except Exception:
        return 0


async def _read_group(redis, stream: str, group: str) -> dict[str, Any]:
    try:
        groups = await redis.xinfo_groups(stream)
    except Exception:
        return {"exists": False, "pending": 0, "lag": 0, "consumers": 0}

    for raw in groups or []:
        name = _to_str(raw.get("name"))
        if name != group:
            continue

        lag_raw = raw.get("lag")
        lag = _to_int(lag_raw, 0) if lag_raw is not None else None
        return {
            "exists": True,
            "pending": _to_int(raw.get("pending"), 0),
            "lag": lag,
            "consumers": _to_int(raw.get("consumers"), 0),
            "last_delivered_id": _to_str(raw.get("last-delivered-id")),
        }

    return {"exists": False, "pending": 0, "lag": 0, "consumers": 0}


def _stream_status(*, pending: int, lag: int, dlq_depth: int) -> tuple[str, list[str]]:
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

    return status, alerts


async def collect_stream_backpressure() -> dict[str, Any]:
    """Collect lag/pending/DLQ counters for stream pipelines."""
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
    stream_specs = (
        (
            "logs",
            settings.REDIS_STREAM_LOGS,
            settings.REDIS_LOG_CONSUMER_GROUP,
            settings.REDIS_STREAM_LOGS_DLQ,
        ),
        (
            "containers",
            settings.REDIS_STREAM_CONTAINERS,
            settings.REDIS_CONTAINER_CONSUMER_GROUP,
            settings.REDIS_STREAM_CONTAINERS_DLQ,
        ),
        (
            "events",
            settings.REDIS_STREAM_EVENTS,
            settings.REDIS_EVENT_CONSUMER_GROUP,
            settings.REDIS_STREAM_EVENTS_DLQ,
        ),
        (
            "alerts",
            settings.REDIS_STREAM_ALERTS,
            settings.REDIS_NOTIFIER_CONSUMER_GROUP,
            settings.REDIS_STREAM_ALERTS_DLQ,
        ),
    )

    result_streams: dict[str, Any] = {}
    overall_status = "ok"
    alerts: list[str] = []
    total_pending = 0
    total_lag = 0
    total_dlq_depth = 0

    for name, stream, group, dlq_stream in stream_specs:
        stream_len = await _safe_xlen(redis, stream)
        dlq_len = await _safe_xlen(redis, dlq_stream)
        group_info = await _read_group(redis, stream, group)
        pending = _to_int(group_info.get("pending"), 0)
        lag_value = group_info.get("lag")
        lag_estimated = lag_value is None
        lag = _to_int(lag_value, stream_len if lag_estimated else 0)

        stream_status, stream_alerts = _stream_status(
            pending=pending,
            lag=lag,
            dlq_depth=dlq_len,
        )
        overall_status = _merge_status(overall_status, stream_status)
        alerts.extend([f"{name}: {entry}" for entry in stream_alerts])

        total_pending += pending
        total_lag += lag
        total_dlq_depth += dlq_len

        result_streams[name] = {
            "stream": stream,
            "consumer_group": group,
            "length": stream_len,
            "pending": pending,
            "lag": lag,
            "lag_estimated": lag_estimated,
            "consumers": _to_int(group_info.get("consumers"), 0),
            "dlq_stream": dlq_stream,
            "dlq_depth": dlq_len,
            "status": stream_status,
        }

    return {
        "status": overall_status,
        "streams": result_streams,
        "totals": {
            "pending": total_pending,
            "lag": total_lag,
            "dlq_depth": total_dlq_depth,
        },
        "alerts": alerts,
    }


async def collect_central_log_ingest_counters() -> dict[str, Any]:
    """Read Central ingest/drop counters persisted in Redis."""
    try:
        redis = await get_redis()
    except Exception as exc:
        return {"status": "unknown", "error": str(exc)}
    try:
        raw = await redis.hgetall(settings.INGEST_LOG_COUNTER_KEY)
    except Exception as exc:
        return {"status": "unknown", "error": str(exc)}

    counters = {_to_str(key): _to_int(value) for key, value in (raw or {}).items()}
    dropped_total = counters.get("dropped_total", 0)
    dropped_scope = counters.get("dropped_scope", 0)
    dropped_publish = counters.get("dropped_publish", 0)
    dropped_malformed = counters.get("dropped_malformed", 0)
    dropped_oversize = counters.get("dropped_oversize", 0)
    requests_total = counters.get("requests_total", 0)
    actionable_dropped_total = dropped_publish + dropped_malformed + dropped_oversize
    last_actionable_drop_ts = counters.get("last_actionable_drop_ts", 0)
    last_oversize_reject_ts = counters.get("last_oversize_reject_ts", 0)
    window_seconds = max(1, int(settings.INGEST_HEALTH_WINDOW_SECONDS))
    now_ts = int(time.time())
    recent_actionable_drop = (
        last_actionable_drop_ts > 0
        and (now_ts - last_actionable_drop_ts) <= window_seconds
    )
    recent_oversize_reject = (
        last_oversize_reject_ts > 0
        and (now_ts - last_oversize_reject_ts) <= window_seconds
    )

    status = "ok"
    alerts: list[str] = []
    if recent_actionable_drop:
        status = "warning"
        age_seconds = max(0, now_ts - last_actionable_drop_ts)
        alerts.append(
            "central log ingest recent_actionable_drop "
            f"age={age_seconds}s window={window_seconds}s"
        )
    if recent_oversize_reject:
        status = "critical"
        age_seconds = max(0, now_ts - last_oversize_reject_ts)
        alerts.append(
            "central log ingest recent_oversize_reject "
            f"age={age_seconds}s window={window_seconds}s"
        )

    return {
        "status": status,
        "counter_key": settings.INGEST_LOG_COUNTER_KEY,
        "window_seconds": window_seconds,
        "requests_total": requests_total,
        "actionable_dropped_total": actionable_dropped_total,
        "dropped_total": dropped_total,
        "dropped_scope": dropped_scope,
        "recent_actionable_drop": recent_actionable_drop,
        "recent_oversize_reject": recent_oversize_reject,
        "last_actionable_drop_ts": last_actionable_drop_ts or None,
        "last_oversize_reject_ts": last_oversize_reject_ts or None,
        "counters": counters,
        "alerts": alerts,
    }


def _parse_prometheus_sums(metrics_text: str) -> dict[str, float]:
    sums: dict[str, float] = {}
    for raw_line in metrics_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _PROM_LINE_RE.match(line)
        if not match:
            continue
        name = match.group("name")
        try:
            value = float(match.group("value"))
        except ValueError:
            continue
        sums[name] = sums.get(name, 0.0) + value
    return sums


def _metric_sum(metrics_sums: dict[str, float], *names: str) -> float:
    """Return first available prometheus metric sum from an alias list."""
    for name in names:
        if name in metrics_sums:
            return metrics_sums[name]
    return 0.0


async def collect_otlp_metrics_path_status() -> dict[str, Any]:
    """Collect OTLP metrics ingest pressure from OTel Collector self-metrics."""
    if not settings.OTEL_COLLECTOR_METRICS_URL:
        return {"status": "unknown", "error": "OTEL_COLLECTOR_METRICS_URL not configured"}

    try:
        timeout = max(1, settings.OTEL_COLLECTOR_METRICS_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(settings.OTEL_COLLECTOR_METRICS_URL)
            response.raise_for_status()
            metrics_sums = _parse_prometheus_sums(response.text)
    except Exception as exc:
        return {
            "status": "unknown",
            "error": str(exc),
            "endpoint": settings.OTEL_COLLECTOR_METRICS_URL,
        }

    accepted_points = int(
        _metric_sum(
            metrics_sums,
            "otelcol_receiver_accepted_metric_points_total",
            "otelcol_receiver_accepted_metric_points",
        )
    )
    refused_points = int(
        _metric_sum(
            metrics_sums,
            "otelcol_receiver_refused_metric_points_total",
            "otelcol_receiver_refused_metric_points",
        )
    )
    processor_refused_points = int(
        _metric_sum(
            metrics_sums,
            "otelcol_processor_refused_metric_points_total",
            "otelcol_processor_refused_metric_points",
        )
    )
    send_failed_points = int(
        _metric_sum(
            metrics_sums,
            "otelcol_exporter_send_failed_metric_points_total",
            "otelcol_exporter_send_failed_metric_points",
        )
    )
    queue_size = int(metrics_sums.get("otelcol_exporter_queue_size", 0))
    queue_capacity = int(metrics_sums.get("otelcol_exporter_queue_capacity", 0))
    queue_saturation = (
        (float(queue_size) / float(queue_capacity)) if queue_capacity > 0 else None
    )

    status = "ok"
    alerts: list[str] = []
    if refused_points > 0 or processor_refused_points > 0:
        status = _merge_status(status, "critical")
        alerts.append(
            "OTLP metrics path is refusing metric points "
            f"(receiver={refused_points}, processor={processor_refused_points})"
        )
    if send_failed_points > 0:
        status = _merge_status(status, "warning")
        alerts.append(f"OTLP metrics export failures detected ({send_failed_points})")
    if queue_saturation is not None:
        if queue_saturation >= settings.OTEL_QUEUE_SATURATION_CRITICAL:
            status = _merge_status(status, "critical")
            alerts.append(
                f"OTLP exporter queue saturation={queue_saturation:.2f} (critical)"
            )
        elif queue_saturation >= settings.OTEL_QUEUE_SATURATION_WARN:
            status = _merge_status(status, "warning")
            alerts.append(
                f"OTLP exporter queue saturation={queue_saturation:.2f} (warning)"
            )

    return {
        "status": status,
        "endpoint": settings.OTEL_COLLECTOR_METRICS_URL,
        "accepted_metric_points": accepted_points,
        "refused_metric_points": refused_points,
        "processor_refused_metric_points": processor_refused_points,
        "send_failed_metric_points": send_failed_points,
        "queue_size": queue_size,
        "queue_capacity": queue_capacity,
        "queue_saturation": queue_saturation,
        "alerts": alerts,
    }
