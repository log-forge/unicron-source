"""Alert dispatcher service for publishing alerts to Redis Stream.

Provides reliable message delivery from alert-engine to notifier service
via Redis Streams with automatic stream trimming.
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis

logger = get_logger("alert-engine.services.alert_dispatcher")


async def publish_alert(alert_data: Dict[str, Any]) -> Optional[str]:
    """
    Publish alert to Redis Stream for notifier consumption.

    The alert payload is serialized to JSON and published to the
    configured Redis Stream with automatic trimming.

    Args:
        alert_data: Alert payload containing:
            - alert_id: Unique alert identifier
            - rule_id: Rule that triggered the alert
            - rule_name: Human-readable rule name
            - severity: Alert severity level
            - labels: Alert labels for routing/filtering
            - annotations: Additional context for display
            - value: Trigger value (e.g., log count)
            - triggered_at: ISO timestamp of trigger
            - organization_id: Organization scope

    Returns:
        Stream message ID on success, None on failure.
    """
    try:
        redis = await get_redis()

        # Serialize alert data to JSON
        message_data = {"data": json.dumps(alert_data)}

        # Publish to stream with maxlen trimming
        message_id = await redis.xadd(
            settings.REDIS_STREAM_ALERTS,
            message_data,
            maxlen=settings.REDIS_STREAM_MAX_LEN,
        )

        logger.info(
            "Alert published to stream: message_id=%s, alert_id=%s, rule_id=%s",
            message_id,
            alert_data.get("alert_id"),
            alert_data.get("rule_id"),
        )

        return message_id

    except Exception as e:
        logger.error(
            "Failed to publish alert to stream: alert_id=%s, error=%s",
            alert_data.get("alert_id"),
            str(e),
        )
        return None


def build_alert_payload(
    alert_id: str,
    rule_id: str,
    rule_name: str,
    severity: str,
    fingerprint: Optional[str],
    labels: Dict[str, str],
    annotations: Dict[str, Any],
    value: Any,
    triggered_at: datetime,
    organization_id: str,
) -> Dict[str, Any]:
    """
    Build standardized alert payload for stream publishing.

    Args:
        alert_id: Unique alert identifier
        rule_id: Rule that triggered the alert
        rule_name: Human-readable rule name
        severity: Alert severity level (critical, warning, info)
        fingerprint: Dedup fingerprint used for notifier idempotency
        labels: Alert labels for routing/filtering
        annotations: Additional context for display/notification
        value: Trigger value (e.g., log count, metric value)
        triggered_at: Datetime when alert was triggered
        organization_id: Organization scope

    Returns:
        Standardized alert payload dictionary.
    """
    return {
        "alert_id": alert_id,
        "rule_id": rule_id,
        "rule_name": rule_name,
        "severity": severity,
        "fingerprint": fingerprint or "",
        "labels": labels,
        "annotations": annotations,
        "value": value,
        "triggered_at": triggered_at.isoformat(),
        "organization_id": organization_id,
    }


__all__ = ["publish_alert", "build_alert_payload"]
