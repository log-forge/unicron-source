"""Internal OTLP log intake for durable-lane alert fanout.

Accepts OTLP/HTTP protobuf log exports from the central collector and
normalizes them into the existing Redis alert stream schema. VictoriaLogs
storage remains owned by the collector; this endpoint is fanout-only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
    ExportLogsServiceResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.logging import get_logger
from app.routes.internal.context import verify_internal_secret
from app.services.alerting.log_scope_filter import get_log_scope_filter
from app.services.alerting.streams import LogBatchPublishError, publish_log_batch

logger = get_logger("routes.internal.otlp_logs")

router = APIRouter(prefix="/internal/logs", tags=["internal"])

OTLP_PROTO_CONTENT_TYPE = "application/x-protobuf"


def _any_value_to_python(value) -> Any:
    kind = value.WhichOneof("value")
    if kind == "string_value":
        return value.string_value
    if kind == "bool_value":
        return value.bool_value
    if kind == "int_value":
        return value.int_value
    if kind == "double_value":
        return value.double_value
    if kind == "array_value":
        return [_any_value_to_python(item) for item in value.array_value.values]
    if kind == "kvlist_value":
        return {
            item.key: _any_value_to_python(item.value)
            for item in value.kvlist_value.values
            if str(item.key or "").strip()
        }
    if kind == "bytes_value":
        try:
            return value.bytes_value.decode("utf-8")
        except Exception:
            return value.bytes_value.hex()
    return None


def _attributes_to_dict(values) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in values:
        key = str(item.key or "").strip()
        if not key:
            continue
        out[key] = _any_value_to_python(item.value)
    return out


def _normalize_time_unix_nano(value: int) -> str:
    nanos = int(value or 0)
    if nanos <= 0:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    dt = datetime.fromtimestamp(nanos / 1_000_000_000, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _string_value(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
            continue
        return str(value)
    return ""


def _normalize_otlp_record(resource_attrs: dict[str, Any], log_attrs: dict[str, Any], record) -> dict[str, Any] | None:
    merged = dict(resource_attrs)
    merged.update(log_attrs)

    host_id = _string_value(merged, "herald_id", "host_id", "service.instance.id")
    container_key = _string_value(merged, "container_key", "container_id")
    container_name = _string_value(merged, "container_name", "service_name", "service.name")

    if not container_key and host_id and container_name:
        container_key = f"{host_id}:{container_name}"
    if not host_id and ":" in container_key:
        host_id = container_key.split(":", 1)[0].strip()

    message = _string_value(log_attrs, "msg", "message")
    if not message and record.HasField("body"):
        body = _any_value_to_python(record.body)
        if isinstance(body, str):
            message = body.strip()
        elif body not in (None, ""):
            message = str(body)

    if not host_id or not container_key or not container_name or not message:
        return None

    normalized = {
        "host_id": host_id,
        "container_key": container_key,
        "container_id": container_key,
        "container_name": container_name,
        "message": message,
        "timestamp": _normalize_time_unix_nano(record.time_unix_nano or record.observed_time_unix_nano),
        "herald_id": _string_value(merged, "herald_id"),
        "herald_name": _string_value(merged, "herald_name"),
        "docker_container_id": _string_value(merged, "docker_container_id"),
        "service_name": _string_value(merged, "service_name", "service.name"),
        "service_namespace": _string_value(merged, "service_namespace", "service.namespace"),
        "severity": _string_value(log_attrs, "severity") or str(record.severity_text or "").strip(),
        "stream": _string_value(log_attrs, "stream"),
    }
    if "msg_json" in log_attrs:
        normalized["msg_json"] = log_attrs["msg_json"]
    return normalized


def decode_otlp_log_payload(raw_body: bytes) -> list[dict[str, Any]]:
    request = ExportLogsServiceRequest()
    request.ParseFromString(raw_body)

    normalized: list[dict[str, Any]] = []
    for resource_logs in request.resource_logs:
        resource_attrs = _attributes_to_dict(resource_logs.resource.attributes)
        for scope_logs in resource_logs.scope_logs:
            for record in scope_logs.log_records:
                log_attrs = _attributes_to_dict(record.attributes)
                entry = _normalize_otlp_record(resource_attrs, log_attrs, record)
                if entry is not None:
                    normalized.append(entry)
    return normalized


def _otlp_success_response() -> Response:
    return Response(
        content=ExportLogsServiceResponse().SerializeToString(),
        media_type=OTLP_PROTO_CONTENT_TYPE,
    )


@router.post("/otlp/v1/logs")
async def ingest_otlp_logs(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_internal_secret),
) -> Response:
    raw_body = await request.body()
    try:
        normalized = decode_otlp_log_payload(raw_body)
    except DecodeError as exc:
        raise HTTPException(status_code=400, detail="Malformed OTLP log payload") from exc

    if not normalized:
        return _otlp_success_response()

    scope_filter = get_log_scope_filter()
    relevant = await scope_filter.filter_relevant(session, normalized)
    dropped = max(0, len(normalized) - len(relevant))

    try:
        published = await publish_log_batch(relevant)
    except LogBatchPublishError as exc:
        logger.warning(
            "OTLP alert fanout publish failed; collector should retry",
            extra={
                "accepted": len(normalized),
                "relevant": len(relevant),
                "published": exc.published,
                "reason": exc.reason,
            },
        )
        raise HTTPException(
            status_code=503,
            detail="Alert fanout unavailable; retry required",
        ) from exc

    logger.debug(
        "OTLP alert fanout published batch",
        extra={
            "accepted": len(normalized),
            "published": published,
            "dropped": dropped,
        },
    )
    return _otlp_success_response()


__all__ = ["router", "decode_otlp_log_payload"]
