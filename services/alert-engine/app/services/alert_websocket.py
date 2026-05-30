"""WebSocket broadcast service for alert state changes.

Publishes alert events to the `unicron:alert-updates` Redis pub/sub channel
using plain JSON messages. Central's alert relay subscribes to this channel
and forwards events to browser WebSocket clients.

Message types:
- alert:fired -- Self-contained payload with all display fields so Central
  can render without calling back to alert-engine.
- alert:state_changed -- Lightweight payload for ack/resolve transitions.

This follows the same plain-JSON pub/sub pattern used by container_websocket.py
and Central's container_ws_relay.py (NOT the Socket.IO adapter format).
"""

import json
from datetime import datetime
from typing import Optional

from app.core.logging import get_logger

logger = get_logger("alert-engine.services.alert_websocket")

# Plain Redis pub/sub channel -- Central subscribes to relay to browsers
ALERT_WS_CHANNEL = "unicron:alert-updates"


async def publish_alert_fired(
    alert_id: str,
    rule_id: str,
    rule_name: str,
    rule_type: str,
    container_name: str,
    host_id: str,
    severity: str,
    message: str,
    trigger_value: str,
    threshold: str,
    status: str,
    started_at: datetime,
    updated_at: datetime,
    organization_id: str,
) -> None:
    """
    Publish an alert:fired event with self-contained payload.

    Called after a new alert is committed to DB. The payload includes all
    display fields so Central can render the alert in the UI without
    making a callback to alert-engine.

    Args:
        alert_id: The alert ID.
        rule_id: The rule that fired.
        rule_name: Human-readable rule name.
        rule_type: keyword | rate | absence | container_event.
        container_name: Container name (from labels.container_id).
        host_id: Host identifier (from labels.host_id).
        severity: critical | warning | info.
        message: Alert message from evaluation.
        trigger_value: The value that triggered the alert.
        threshold: The threshold that was exceeded.
        status: Alert status (firing).
        started_at: When the alert started.
        updated_at: When the alert was last updated.
        organization_id: Org ID for tenant filtering.
    """
    from app.core.redis import get_redis

    try:
        redis = await get_redis()

        payload = {
            "type": "alert:fired",
            "data": {
                "alert_id": alert_id,
                "rule_id": rule_id,
                "rule_name": rule_name,
                "rule_type": rule_type,
                "container_name": container_name,
                "host_id": host_id,
                "severity": severity,
                "message": message,
                "trigger_value": trigger_value,
                "threshold": threshold,
                "status": status,
                "started_at": started_at.isoformat() if isinstance(started_at, datetime) else str(started_at),
                "updated_at": updated_at.isoformat() if isinstance(updated_at, datetime) else str(updated_at),
                "organization_id": organization_id,
            },
        }

        await redis.publish(ALERT_WS_CHANNEL, json.dumps(payload))

        logger.debug(
            "Published alert:fired to %s: alert_id=%s, rule=%s, severity=%s",
            ALERT_WS_CHANNEL,
            alert_id,
            rule_name,
            severity,
        )
    except Exception as e:
        # Never raise -- publish failures are non-blocking
        logger.warning(
            "Failed to publish alert:fired for %s: %s",
            alert_id,
            str(e),
        )


async def publish_alert_stacked(
    alert_id: str,
    count: int,
    last_seen: datetime,
    organization_id: str,
) -> None:
    """
    Publish an alert:stacked event when stack count increments.

    Called after a stacked alert is updated in DB. The payload includes
    the updated count and last_seen so the UI can update in real-time
    without polling.

    Args:
        alert_id: The alert ID.
        count: Updated stacking count.
        last_seen: When the alert last fired.
        organization_id: Org ID for tenant filtering.
    """
    from app.core.redis import get_redis

    try:
        redis = await get_redis()

        payload = {
            "type": "alert:stacked",
            "data": {
                "alert_id": alert_id,
                "count": count,
                "last_seen": last_seen.isoformat() if isinstance(last_seen, datetime) else str(last_seen),
                "organization_id": organization_id,
            },
        }

        await redis.publish(ALERT_WS_CHANNEL, json.dumps(payload))

        logger.debug(
            "Published alert:stacked to %s: alert_id=%s, count=%d",
            ALERT_WS_CHANNEL,
            alert_id,
            count,
        )
    except Exception as e:
        # Never raise -- publish failures are non-blocking
        logger.warning(
            "Failed to publish alert:stacked for %s: %s",
            alert_id,
            str(e),
        )


async def publish_alert_state_changed(
    alert_id: str,
    status: str,
    action: str,
    updated_at: datetime,
    organization_id: str,
) -> None:
    """
    Publish an alert:state_changed event for ack/resolve transitions.

    Args:
        alert_id: The alert ID.
        status: New status (acknowledged, resolved).
        action: The action (acknowledged, resolved).
        updated_at: Timestamp of the state change.
        organization_id: Org ID for tenant filtering.
    """
    from app.core.redis import get_redis

    try:
        redis = await get_redis()

        payload = {
            "type": "alert:state_changed",
            "data": {
                "alert_id": alert_id,
                "status": status,
                "action": action,
                "updated_at": updated_at.isoformat() if isinstance(updated_at, datetime) else str(updated_at),
                "organization_id": organization_id,
            },
        }

        await redis.publish(ALERT_WS_CHANNEL, json.dumps(payload))

        logger.debug(
            "Published alert:state_changed to %s: alert_id=%s, status=%s, action=%s",
            ALERT_WS_CHANNEL,
            alert_id,
            status,
            action,
        )
    except Exception as e:
        # Never raise -- publish failures are non-blocking
        logger.warning(
            "Failed to publish alert:state_changed for %s: %s",
            alert_id,
            str(e),
        )


async def broadcast_alert_state_change(
    alert_id: str,
    status: str,
    action: str,
    updated_at: datetime,
    organization_id: str,
) -> None:
    """
    Backward-compatible wrapper for publish_alert_state_changed.

    Existing callers in state_service.py use this function name.
    Delegates to publish_alert_state_changed() which publishes
    to the plain Redis pub/sub channel.

    Args:
        alert_id: The alert ID.
        status: New status (acknowledged, resolved).
        action: The action (acknowledged, resolved).
        updated_at: Timestamp of the state change.
        organization_id: Org ID for tenant filtering.
    """
    await publish_alert_state_changed(
        alert_id=alert_id,
        status=status,
        action=action,
        updated_at=updated_at,
        organization_id=organization_id,
    )


__all__ = [
    "ALERT_WS_CHANNEL",
    "broadcast_alert_state_change",
    "publish_alert_fired",
    "publish_alert_stacked",
    "publish_alert_state_changed",
]
