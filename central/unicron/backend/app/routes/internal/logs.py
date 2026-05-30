"""Internal log ingest pipeline for monitored Fluent Bit log tee.

Accepts monitored container logs from the co-located localhost agent's
Fluent Bit HTTP output and republishes them into `unicron:logs` so the
alert-engine can evaluate log rules without an open browser log session.

Security: Protected by X-Internal-Secret header validation.
"""

from __future__ import annotations

import asyncio
import json
import socket
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session, session_ctx
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.routes.internal.context import verify_internal_secret
from app.services.alerting.log_scope_filter import get_log_scope_filter
from app.services.alerting.streams import LogBatchPublishError, publish_log_batch
from app.utils.httpx_client import build_async_client

logger = get_logger("routes.internal.logs")

router = APIRouter(prefix="/internal/logs", tags=["internal"])


_FANOUT_WORKER_TASK: asyncio.Task | None = None
_FANOUT_WORKER_RUNNING = False
_FANOUT_RECLAIM_CURSOR = "0-0"
_FANOUT_LAST_RECLAIM_AT: float = 0.0
_FANOUT_CONSUMER_NAME = f"central-log-fanout-{socket.gethostname()}"


class LogIngestResponse(BaseModel):
    """Response schema for internal log ingestion."""

    accepted: int = Field(
        ...,
        description="Number of log records accepted for async fanout",
    )
    published: int = Field(
        ...,
        description="Number of log records successfully enqueued",
    )
    dropped: int = Field(
        default=0,
        description="Number of malformed or incomplete records ignored",
    )


def _resource_attrs(record: dict[str, Any]) -> dict[str, Any]:
    """Extract `resource.attributes` when present."""
    resource = record.get("resource")
    if not isinstance(resource, dict):
        return {}
    attributes = resource.get("attributes")
    return attributes if isinstance(attributes, dict) else {}


def _first_value(record: dict[str, Any], *keys: str) -> str:
    """Return the first non-empty string-ish value from record or resource attrs."""
    attrs = _resource_attrs(record)
    for key in keys:
        value = record.get(key)
        if value in (None, ""):
            value = attrs.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, str):
            value = value.strip()
            if value:
                return value
            continue
        return str(value)
    return ""


def _normalize_timestamp(value: Any) -> str:
    """Convert common Fluent Bit time shapes into an ISO8601 UTC string."""
    if isinstance(value, str):
        value = value.strip()
        if value:
            return value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    elif isinstance(value, dict):
        sec = value.get("sec")
        if sec is None:
            sec = value.get("seconds")
        if isinstance(sec, (int, float)):
            nsec = value.get("nsec")
            if nsec is None:
                nsec = value.get("nanosec")
            fraction = (float(nsec) / 1_000_000_000.0) if isinstance(
                nsec, (int, float)
            ) else 0.0
            dt = datetime.fromtimestamp(float(sec) + fraction, tz=timezone.utc)
            return dt.isoformat().replace("+00:00", "Z")

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _flatten_payload(payload: Any) -> list[dict[str, Any]]:
    """Flatten a JSON payload into a list of record dicts."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        for key in ("records", "logs"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]

    return []


def _parse_payload(raw_body: bytes) -> list[dict[str, Any]]:
    """Parse JSON, JSON array, or newline-delimited JSON payloads."""
    if not raw_body:
        return []

    text = raw_body.decode("utf-8", errors="replace").strip()
    if not text:
        return []

    try:
        return _flatten_payload(json.loads(text))
    except json.JSONDecodeError:
        records: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.extend(_flatten_payload(json.loads(line)))
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="Malformed log payload",
                ) from exc
        return records


def _normalize_record(
    record: dict[str, Any],
    *,
    forced_host_id: str | None = None,
) -> dict[str, Any] | None:
    """Normalize a Fluent Bit log record into the alert stream schema."""
    host_id = _first_value(record, "herald.id", "herald_id", "service.instance.id")
    if forced_host_id:
        host_id = forced_host_id
    container_name = _first_value(
        record,
        "container.name",
        "container_name",
        "service.name",
    )
    if not host_id or not container_name:
        return None

    message = record.get("log")
    if message in (None, ""):
        message = record.get("message")
    if message in (None, ""):
        message = record.get("body")
    if message in (None, ""):
        return None

    if not isinstance(message, str):
        message = json.dumps(message, ensure_ascii=True)
    message = message.rstrip("\r\n")
    if not message:
        return None

    timestamp_value = (
        record.get("timestamp")
        if record.get("timestamp") is not None
        else record.get("date")
    )
    if timestamp_value is None:
        timestamp_value = record.get("time")

    return {
        "host_id": host_id,
        "container_key": f"{host_id}:{container_name}",
        "container_name": container_name,
        "message": message,
        "timestamp": _normalize_timestamp(timestamp_value),
    }


def _to_victoria_log_row(log_data: dict[str, Any]) -> dict[str, Any] | None:
    """Convert normalized ingest record into VictoriaLogs jsonline row."""
    message = str(log_data.get("message", "") or "").strip()
    if not message:
        return None

    host_id = str(log_data.get("host_id", "") or "").strip()
    container_name = str(log_data.get("container_name", "") or "").strip()
    container_key = str(log_data.get("container_key", "") or "").strip()
    if not container_key and host_id and container_name:
        container_key = f"{host_id}:{container_name}"

    row: dict[str, Any] = {
        "date": _normalize_timestamp(log_data.get("timestamp")),
        "log": message,
        "source": "fluentbit_ingest",
        "service_namespace": "unicron.herald",
    }

    if host_id:
        row["host_id"] = host_id
        row["herald_id"] = host_id
        row["service_instance_id"] = host_id
        row["herald_name"] = host_id
    if container_name:
        row["container_name"] = container_name
        row["service_name"] = container_name
    if container_key:
        row["container_key"] = container_key

    return row


async def _store_victoria_logs(logs: list[dict[str, Any]]) -> int:
    """Persist normalized logs to VictoriaLogs via jsonline ingest."""
    if not logs:
        return 0

    rows = []
    for item in logs:
        row = _to_victoria_log_row(item)
        if row is not None:
            rows.append(row)

    if not rows:
        return 0

    payload = "\n".join(json.dumps(row, ensure_ascii=True) for row in rows) + "\n"
    url = (
        f"{settings.VLOGS_BASE.rstrip('/')}/insert/jsonline"
        "?_stream_fields=host_id,container_key,container_name,herald_id,herald_name,service_name,service_namespace"
        "&_msg_field=log&_time_field=date"
    )
    try:
        async with build_async_client(timeout=10.0) as client:
            response = await client.post(
                url,
                data=payload,
                headers={"Content-Type": "application/x-ndjson"},
            )
        if response.status_code >= 400:
            logger.warning(
                "VictoriaLogs ingest failed",
                extra={
                    "status_code": response.status_code,
                    "row_count": len(rows),
                    "body": response.text[:512],
                },
            )
            return 0
        return len(rows)
    except Exception:
        logger.warning(
            "VictoriaLogs ingest request failed",
            exc_info=True,
            extra={"row_count": len(rows)},
        )
        return 0


async def _record_ingest_counters(**increments: int) -> None:
    """Best-effort Redis counter updates for ingest backpressure visibility."""
    to_apply = {
        key: int(value)
        for key, value in increments.items()
        if isinstance(value, (int, float)) and int(value) > 0
    }
    if not to_apply:
        return
    try:
        redis = await get_redis()
        now_ts = int(time.time())
        actionable_fields = (
            "dropped_publish",
            "dropped_malformed",
            "dropped_oversize",
            "requests_rejected_oversize",
        )
        actionable_event = any(to_apply.get(field, 0) > 0 for field in actionable_fields)
        oversize_reject_event = to_apply.get("requests_rejected_oversize", 0) > 0
        async with redis.pipeline(transaction=False) as pipe:
            for field, value in to_apply.items():
                pipe.hincrby(settings.INGEST_LOG_COUNTER_KEY, field, value)
            if actionable_event:
                pipe.hset(settings.INGEST_LOG_COUNTER_KEY, "last_actionable_drop_ts", now_ts)
            if oversize_reject_event:
                pipe.hset(settings.INGEST_LOG_COUNTER_KEY, "last_oversize_reject_ts", now_ts)
            await pipe.execute()
    except Exception:
        # Ingest path must remain best-effort even if telemetry counters fail.
        logger.debug("Failed to update ingest counters", exc_info=True)


def _source_counter_increments(source: str, **increments: int) -> dict[str, int]:
    """Attach source-specific counter keys while preserving generic counters."""
    source_key = "".join(
        ch if ch.isalnum() else "_"
        for ch in str(source or "unknown").strip().lower()
    ).strip("_") or "unknown"

    merged: dict[str, int] = {}
    for key, value in increments.items():
        if not isinstance(value, (int, float)):
            continue
        amount = int(value)
        if amount <= 0:
            continue
        merged[key] = amount
        merged[f"{source_key}_{key}"] = amount
    return merged


def _extract_claimed_messages(result: Any) -> list[tuple[str, dict[str, Any]]]:
    """Normalize XAUTOCLAIM response to a list of (message_id, fields)."""
    if not result or not isinstance(result, (list, tuple)) or len(result) < 2:
        return []

    raw_messages = result[1]
    if not isinstance(raw_messages, list):
        return []

    normalized: list[tuple[str, dict[str, Any]]] = []
    for item in raw_messages:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        message_id, fields = item
        if isinstance(message_id, bytes):
            message_id = message_id.decode("utf-8", errors="replace")
        if not isinstance(message_id, str) or not message_id:
            continue
        if not isinstance(fields, dict):
            fields = {}
        normalized.append((message_id, fields))
    return normalized


def _decode_ingest_envelope(payload: Any) -> tuple[str, list[dict[str, Any]]]:
    """Decode queued ingest envelope into (source, normalized_logs)."""
    if not isinstance(payload, dict):
        return "unknown", []

    # Strict format: {"source": "agent|internal", "logs": [ ... ]}
    if "logs" in payload:
        source = str(payload.get("source", "unknown") or "unknown").strip().lower()
        logs_raw = payload.get("logs")
        if isinstance(logs_raw, list):
            logs = [item for item in logs_raw if isinstance(item, dict)]
            return source or "unknown", logs
        return source or "unknown", []

    return "unknown", []


def _has_stream_messages(batches: Any) -> bool:
    """Return True when XREADGROUP-like batches contain at least one message."""
    if not isinstance(batches, list):
        return False
    for item in batches:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        _, stream_messages = item
        if isinstance(stream_messages, list) and stream_messages:
            return True
    return False


async def _enqueue_for_fanout(
    logs: list[dict[str, Any]],
    *,
    source: str,
) -> bool:
    """Enqueue normalized logs for async fanout processing."""
    if not logs:
        return True

    envelope = {
        "source": source,
        "received_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "logs": logs,
    }
    redis = await get_redis()
    try:
        await redis.xadd(
            settings.REDIS_STREAM_LOG_INGEST,
            {"data": json.dumps(envelope, ensure_ascii=True)},
            maxlen=settings.REDIS_LOG_INGEST_STREAM_MAX_LEN,
            approximate=True,
        )
        return True
    except Exception:
        logger.warning("Failed to enqueue log fanout envelope", exc_info=True)
        return False


async def _process_fanout_envelope(
    *,
    session: AsyncSession,
    source: str,
    logs: list[dict[str, Any]],
) -> None:
    """Process one queued envelope: storage write + scoped publish."""
    if not logs:
        return

    stored_victoria = await _store_victoria_logs(logs)
    dropped_storage = max(0, len(logs) - stored_victoria)

    scope_filter = get_log_scope_filter()
    relevant = await scope_filter.filter_relevant(session, logs)
    dropped_scope = max(0, len(logs) - len(relevant))

    publish_retry_required = False
    publish_error_reason: str | None = None
    published = 0
    dropped_publish = 0
    try:
        published = await publish_log_batch(relevant)
        dropped_publish = max(0, len(relevant) - published)
    except LogBatchPublishError as exc:
        publish_retry_required = True
        published = max(0, min(exc.published, len(relevant)))
        dropped_publish = max(0, len(relevant) - published)
        publish_error_reason = exc.reason

    dropped_total = dropped_storage + dropped_scope + dropped_publish
    await _record_ingest_counters(
        **_source_counter_increments(
            source,
            fanout_batches_total=1,
            fanout_records_total=len(logs),
            records_stored_victoria=stored_victoria,
            dropped_storage=dropped_storage,
            records_scoped_in=len(relevant),
            dropped_scope=dropped_scope,
            records_published=published,
            dropped_publish=dropped_publish,
            dropped_total=dropped_total,
            requests_retry_required=1 if publish_retry_required else 0,
        )
    )

    if dropped_total:
        logger.warning(
            "Dropped records during async log fanout",
            extra={
                "source": source,
                "normalized": len(logs),
                "stored_victoria": stored_victoria,
                "accepted": len(relevant),
                "published": published,
                "dropped_storage": dropped_storage,
                "dropped_scope": dropped_scope,
                "dropped_publish": dropped_publish,
                "publish_retry_required": publish_retry_required,
                "publish_error_reason": publish_error_reason,
            },
        )

    if publish_retry_required:
        raise LogBatchPublishError(
            published=published,
            total=len(relevant),
            reason=publish_error_reason or "async_publish_retry_required",
        )


async def _maybe_reclaim_fanout(redis) -> list[tuple[str, dict[str, Any]]]:
    """Reclaim stale pending fanout messages from dead consumers."""
    global _FANOUT_LAST_RECLAIM_AT, _FANOUT_RECLAIM_CURSOR
    if not settings.REDIS_LOG_INGEST_RECLAIM_ENABLED:
        return []

    now = time.monotonic()
    if now - _FANOUT_LAST_RECLAIM_AT < settings.REDIS_LOG_INGEST_RECLAIM_INTERVAL_SECONDS:
        return []
    _FANOUT_LAST_RECLAIM_AT = now

    try:
        result = await redis.xautoclaim(
            settings.REDIS_STREAM_LOG_INGEST,
            settings.REDIS_LOG_INGEST_CONSUMER_GROUP,
            _FANOUT_CONSUMER_NAME,
            settings.REDIS_LOG_INGEST_RECLAIM_IDLE_MS,
            start_id=_FANOUT_RECLAIM_CURSOR,
            count=settings.REDIS_LOG_INGEST_RECLAIM_BATCH_SIZE,
        )
        if isinstance(result, (list, tuple)) and result:
            next_cursor = result[0]
            if isinstance(next_cursor, bytes):
                next_cursor = next_cursor.decode("utf-8", errors="replace")
            if isinstance(next_cursor, str) and next_cursor:
                _FANOUT_RECLAIM_CURSOR = next_cursor

        reclaimed = _extract_claimed_messages(result)
        if reclaimed:
            logger.info("Reclaimed %d pending log fanout envelopes", len(reclaimed))
        return reclaimed
    except Exception:
        logger.warning("Log fanout reclaim failed", exc_info=True)
        return []


async def _process_fanout_messages(
    redis,
    messages: list[tuple[str, dict[str, Any]]],
    *,
    source: str,
) -> bool:
    """Process queued envelopes and ack successes. Returns True if retries remain."""
    if not messages:
        return False

    ack_ids: list[str] = []
    retry_pending = False

    async with session_ctx() as session:
        for message_id, fields in messages:
            if isinstance(message_id, bytes):
                message_id = message_id.decode("utf-8", errors="replace")
            if not isinstance(message_id, str) or not message_id:
                continue

            try:
                payload_raw = fields.get("data") if isinstance(fields, dict) else None
                if isinstance(payload_raw, bytes):
                    payload_raw = payload_raw.decode("utf-8", errors="replace")
                payload = json.loads(payload_raw or "{}")
                envelope_source, logs = _decode_ingest_envelope(payload)
                if not logs:
                    await _record_ingest_counters(
                        **_source_counter_increments(
                            envelope_source or "unknown",
                            fanout_batches_total=1,
                            fanout_malformed_envelopes=1,
                        )
                    )
                    ack_ids.append(message_id)
                    continue

                await _process_fanout_envelope(
                    session=session,
                    source=envelope_source or "unknown",
                    logs=logs,
                )
                ack_ids.append(message_id)
            except LogBatchPublishError:
                retry_pending = True
                logger.warning(
                    "Deferring ack for log fanout envelope due to downstream publish retry requirement",
                    extra={"message_id": message_id, "source": source},
                )
                continue
            except Exception:
                retry_pending = True
                logger.warning(
                    "Failed to process log fanout envelope; will retry",
                    exc_info=True,
                    extra={"message_id": message_id, "source": source},
                )

    if ack_ids:
        await redis.xack(
            settings.REDIS_STREAM_LOG_INGEST,
            settings.REDIS_LOG_INGEST_CONSUMER_GROUP,
            *ack_ids,
        )

    return retry_pending


async def _fanout_loop() -> None:
    """Queue consumer loop: ingest envelopes -> storage + scoped alert stream publish."""
    redis = await get_redis()

    while _FANOUT_WORKER_RUNNING:
        try:
            reclaimed = await _maybe_reclaim_fanout(redis)
            if reclaimed:
                retry_pending = await _process_fanout_messages(
                    redis,
                    reclaimed,
                    source="reclaimed",
                )
                if retry_pending:
                    await asyncio.sleep(0.5)
                continue

            pending = await redis.xreadgroup(
                groupname=settings.REDIS_LOG_INGEST_CONSUMER_GROUP,
                consumername=_FANOUT_CONSUMER_NAME,
                streams={settings.REDIS_STREAM_LOG_INGEST: "0"},
                count=settings.REDIS_LOG_INGEST_BATCH_SIZE,
            )
            if _has_stream_messages(pending):
                for _, stream_messages in pending:
                    retry_pending = await _process_fanout_messages(
                        redis,
                        stream_messages,
                        source="pending",
                    )
                    if retry_pending:
                        await asyncio.sleep(0.5)
                continue

            messages = await redis.xreadgroup(
                groupname=settings.REDIS_LOG_INGEST_CONSUMER_GROUP,
                consumername=_FANOUT_CONSUMER_NAME,
                streams={settings.REDIS_STREAM_LOG_INGEST: ">"},
                count=settings.REDIS_LOG_INGEST_BATCH_SIZE,
                block=settings.REDIS_LOG_INGEST_BLOCK_MS,
            )
            if not _has_stream_messages(messages):
                continue

            for _, stream_messages in messages:
                retry_pending = await _process_fanout_messages(
                    redis,
                    stream_messages,
                    source="live",
                )
                if retry_pending:
                    await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            logger.info("Log fanout worker loop cancelled")
            break
        except Exception:
            logger.error("Error in log fanout worker loop", exc_info=True)
            await asyncio.sleep(1.0)


async def start_log_fanout_worker() -> None:
    """Start background worker that processes queued log fanout envelopes."""
    global _FANOUT_WORKER_TASK, _FANOUT_WORKER_RUNNING
    if _FANOUT_WORKER_RUNNING:
        logger.info("Log fanout worker already running")
        return

    _FANOUT_WORKER_RUNNING = True
    _FANOUT_WORKER_TASK = asyncio.create_task(_fanout_loop())
    logger.info(
        "Log fanout worker started: stream=%s group=%s consumer=%s",
        settings.REDIS_STREAM_LOG_INGEST,
        settings.REDIS_LOG_INGEST_CONSUMER_GROUP,
        _FANOUT_CONSUMER_NAME,
    )


async def stop_log_fanout_worker() -> None:
    """Stop background log fanout worker gracefully."""
    global _FANOUT_WORKER_TASK, _FANOUT_WORKER_RUNNING
    if not _FANOUT_WORKER_RUNNING:
        return

    _FANOUT_WORKER_RUNNING = False
    if _FANOUT_WORKER_TASK is not None:
        _FANOUT_WORKER_TASK.cancel()
        try:
            await _FANOUT_WORKER_TASK
        except asyncio.CancelledError:
            pass
    _FANOUT_WORKER_TASK = None
    logger.info("Log fanout worker stopped")


async def ingest_logs_payload(
    raw_body: bytes,
    session: AsyncSession,
    *,
    source: str,
    forced_host_id: str | None = None,
    require_host_match: bool = False,
) -> LogIngestResponse:
    """Normalize and enqueue Fluent Bit logs for async fanout processing."""
    source_label = str(source or "unknown").strip().lower() or "unknown"
    body_bytes = len(raw_body)
    soft_limit = max(1, int(settings.INTERNAL_LOGS_MAX_BODY_BYTES))
    hard_limit = max(soft_limit, int(settings.INTERNAL_LOGS_HARD_MAX_BODY_BYTES))

    if body_bytes > hard_limit:
        await _record_ingest_counters(
            **_source_counter_increments(
                source_label,
                requests_total=1,
                bytes_received=body_bytes,
                requests_rejected_oversize=1,
                requests_rejected_oversize_hard=1,
                dropped_oversize=1,
                dropped_oversize_hard=1,
            )
        )
        raise HTTPException(
            status_code=413,
            detail="Log payload too large",
        )

    if body_bytes > soft_limit:
        await _record_ingest_counters(
            **_source_counter_increments(
                source_label,
                requests_oversize_soft=1,
                bytes_oversize_soft=body_bytes - soft_limit,
            )
        )
        logger.debug(
            "Accepted oversize log ingest request within hard limit",
            extra={
                "source": source_label,
                "body_bytes": body_bytes,
                "soft_limit_bytes": soft_limit,
                "hard_limit_bytes": hard_limit,
            },
        )

    try:
        records = _parse_payload(raw_body)
    except HTTPException:
        await _record_ingest_counters(
            **_source_counter_increments(
                source_label,
                requests_total=1,
                bytes_received=body_bytes,
                requests_malformed=1,
            )
        )
        raise

    normalized: list[dict[str, Any]] = []
    dropped_malformed = 0
    identity_mismatches = 0
    for record in records:
        if forced_host_id and require_host_match:
            payload_host_id = _first_value(
                record,
                "herald.id",
                "herald_id",
                "service.instance.id",
            )
            if payload_host_id and payload_host_id != forced_host_id:
                identity_mismatches += 1
                continue

        log_data = _normalize_record(record, forced_host_id=forced_host_id)
        if log_data is None:
            dropped_malformed += 1
            continue
        normalized.append(log_data)

    await _record_ingest_counters(
        **_source_counter_increments(
            source_label,
            requests_total=1,
            bytes_received=body_bytes,
            records_received=len(records),
            records_normalized=len(normalized),
            dropped_malformed=dropped_malformed,
            dropped_identity_mismatch=identity_mismatches,
        )
    )

    if identity_mismatches > 0:
        logger.warning(
            "Rejected log ingest request due to host identity mismatch",
            extra={
                "source": source_label,
                "forced_host_id": forced_host_id,
                "identity_mismatches": identity_mismatches,
                "received": len(records),
            },
        )
        raise HTTPException(status_code=403, detail="Herald identity mismatch")

    if not normalized:
        if records and dropped_malformed:
            logger.warning(
                "Dropped all log ingest records",
                extra={
                    "source": source_label,
                    "received": len(records),
                    "dropped": dropped_malformed,
                },
            )
        return LogIngestResponse(accepted=0, published=0, dropped=dropped_malformed)

    _ = session  # retained for route compatibility; fanout now runs async in worker.

    enqueue_ok = await _enqueue_for_fanout(normalized, source=source_label)
    enqueued = len(normalized) if enqueue_ok else 0
    dropped_enqueue = max(0, len(normalized) - enqueued)
    dropped_total = dropped_malformed + dropped_enqueue

    await _record_ingest_counters(
        **_source_counter_increments(
            source_label,
            records_enqueued=enqueued,
            dropped_enqueue=dropped_enqueue,
            dropped_total=dropped_total,
            requests_retry_required=1 if dropped_enqueue > 0 else 0,
        )
    )

    if dropped_total:
        logger.warning(
            "Dropped records during log ingest",
            extra={
                "source": source_label,
                "received": len(records),
                "normalized": len(normalized),
                "enqueued": enqueued,
                "dropped_malformed": dropped_malformed,
                "dropped_enqueue": dropped_enqueue,
            },
        )

    if dropped_enqueue > 0:
        raise HTTPException(
            status_code=503,
            detail="Log ingest queue temporarily unavailable; retry required",
        )

    return LogIngestResponse(
        accepted=enqueued,
        published=enqueued,
        dropped=dropped_total,
    )


@router.post("/ingest", response_model=LogIngestResponse)
async def ingest_logs(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_internal_secret),
) -> LogIngestResponse:
    """Accept monitored logs from Fluent Bit and publish them to Redis."""
    return await ingest_logs_payload(
        await request.body(),
        session,
        source="internal",
    )


__all__ = ["router", "LogIngestResponse", "ingest_logs_payload"]
