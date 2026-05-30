"""Shared stream reliability helpers for alert-engine consumers."""

from __future__ import annotations

import json
from typing import Any


def extract_claimed_messages(result: Any) -> list[tuple[str, dict[str, Any]]]:
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


async def publish_dlq(
    redis,
    *,
    dlq_stream: str,
    dlq_max_len: int,
    source_stream: str,
    consumer_group: str,
    consumer_name: str,
    message_id: str,
    fields: dict[str, Any],
    error: str,
) -> None:
    """Publish failed message metadata to a DLQ stream."""
    payload = {
        "source_stream": source_stream,
        "consumer_group": consumer_group,
        "consumer_name": consumer_name,
        "message_id": message_id,
        "error": error,
        "fields": fields,
    }
    await redis.xadd(
        dlq_stream,
        {"data": json.dumps(payload, ensure_ascii=True)},
        maxlen=dlq_max_len,
        approximate=True,
    )

