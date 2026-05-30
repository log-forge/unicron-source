"""REST API endpoints for notification testing."""

import time
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.deps import UserContext, require_authenticated_user
from app.core.logging import get_logger
from app.services.alert_dispatcher import build_alert_payload, publish_alert

logger = get_logger("alert-engine.routes.notifications")


class TestNotificationRequest(BaseModel):
    """Request model for test notification endpoint."""

    rule_preview: Optional[str] = None
    severity: Optional[str] = None
    channel_ids: Optional[List[str]] = None
    group_ids: Optional[List[str]] = None
    preset_ids: Optional[List[str]] = None


class TestNotificationResponse(BaseModel):
    """Response model for test notification endpoint."""

    status: str
    alert_id: str
    message: str


router = APIRouter(tags=["notifications"])
_VALID_TEST_SEVERITIES = {"critical", "warning", "info"}


def _normalize_test_severity(raw_severity: Optional[str]) -> str:
    severity = str(raw_severity or "info").strip().lower()
    if severity in _VALID_TEST_SEVERITIES:
        return severity
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid severity. Specify critical, warning, or info.",
    )


@router.post(
    "/test-notification",
    response_model=TestNotificationResponse,
    summary="Queue test notification",
    description="Publish a test alert to verify notification pipeline integration.",
)
async def test_notification(
    body: TestNotificationRequest,
    user: UserContext = Depends(require_authenticated_user),
) -> TestNotificationResponse:
    """
    Queue a test notification to verify notification pipeline.

    This endpoint allows users to test the notification pipeline by sending
    a test alert through the canonical alert stream for notifier processing.

    The request must include at least one notification target (channel_ids,
    group_ids, or preset_ids).
    """
    # Validate at least one target is provided
    has_targets = (
        (body.channel_ids and len(body.channel_ids) > 0)
        or (body.group_ids and len(body.group_ids) > 0)
        or (body.preset_ids and len(body.preset_ids) > 0)
    )

    if not has_targets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No notification targets provided. Specify channel_ids, group_ids, or preset_ids.",
        )

    severity = _normalize_test_severity(body.severity)

    # Generate unique test alert ID
    alert_id = f"test_{int(time.time())}"

    # Build rule preview message
    rule_preview = body.rule_preview or "No rule preview provided"
    message = (
        f"This is a test notification to verify the notification pipeline.\n\n"
        f"Rule Preview:\n{rule_preview}"
    )

    # Build alert payload using existing dispatcher pattern
    alert_payload = build_alert_payload(
        alert_id=alert_id,
        rule_id="test-notification",
        rule_name="Test Notification",
        severity=severity,
        fingerprint=f"test-{alert_id}",
        labels={
            "source": "frontend-test",
            "container_name": "alert-engine-frontend",
        },
        annotations={
            "message": message,
            "rule_preview": rule_preview,
        },
        value=1,
        triggered_at=datetime.now(timezone.utc),
        organization_id=str(user.organization_id),
    )

    # Add notification targets to payload for notifier routing
    alert_payload["notification_targets"] = {
        "channel_ids": body.channel_ids or [],
        "group_ids": body.group_ids or [],
        "preset_ids": body.preset_ids or [],
    }

    # Publish to Redis Stream for notifier consumption
    message_id = await publish_alert(alert_payload)

    if message_id is None:
        logger.error(
            "Failed to publish test notification: alert_id=%s, user=%s",
            alert_id,
            user.user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue test notification. Please try again.",
        )

    logger.info(
        "Test notification queued: alert_id=%s, user=%s, severity=%s, targets=%s",
        alert_id,
        user.user_id,
        severity,
        {
            "channel_ids": body.channel_ids,
            "group_ids": body.group_ids,
            "preset_ids": body.preset_ids,
        },
    )

    return TestNotificationResponse(
        status="queued",
        alert_id=alert_id,
        message="Test notification queued to notifier pipeline.",
    )


__all__ = ["router"]
