"""Notification dispatch tasks.

Provides Celery tasks for notification delivery with priority queue support:
- send_notification: Normal priority (warning/info alerts)
- send_notification_high: High priority (critical/error alerts)
- queue_notification: Helper to route by severity
"""

import asyncio
from datetime import datetime
from typing import Any, Awaitable, Dict, Optional

from celery.signals import worker_process_shutdown
from celery.utils.log import get_task_logger
from sqlalchemy import select

from app.core.database import async_session_maker, close_database
from app.core.logging import CredentialScrubFilter
from app.core.redis import close_redis
from app.models.channel_model import NotificationChannel
from app.models.channel_preset_model import ChannelPreset
from app.models.notification_preference_model import NotificationPreference
from app.services.preference_service import GLOBAL_PREFERENCE_ID
from app.services.ai_service import ai_service
from app.services.ai_settings_service import ai_settings_service
from app.services.delivery_service import delivery_service
from app.services.rate_limit_service import (
    NotificationRateLimitExceeded,
    enforce_delivery_rate_limit,
)
from app.services.template_service import template_service

# Import celery_app using relative path from project root
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from celery_app import celery_app

logger = get_task_logger(__name__)
# Attach credential scrub filter to Celery task logger so notification
# log messages never leak plaintext credentials.
if not any(isinstance(f, CredentialScrubFilter) for f in logger.filters):
    logger.addFilter(CredentialScrubFilter())

__all__ = [
    "send_notification",
    "send_notification_high",
    "queue_notification",
]

# Retry configuration: exponential backoff
# Attempts: 1, 2, 3, 4, 5 (5 total)
# Delays: 60s, 120s, 240s, 480s (1min, 2min, 4min, 8min)
MAX_RETRIES = 4
RETRY_BACKOFF = 60  # Base delay in seconds

_task_loop: Optional[asyncio.AbstractEventLoop] = None


def _get_task_loop() -> asyncio.AbstractEventLoop:
    global _task_loop
    if _task_loop is None or _task_loop.is_closed():
        _task_loop = asyncio.new_event_loop()
    return _task_loop


def _run_async_in_task_loop(coro: Awaitable[Dict[str, Any]]) -> Dict[str, Any]:
    loop = _get_task_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@worker_process_shutdown.connect
def _close_task_runtime_resources(**kwargs) -> None:
    global _task_loop
    loop = _task_loop
    if loop is None or loop.is_closed():
        _task_loop = None
        return

    try:
        loop.run_until_complete(close_redis())
        loop.run_until_complete(close_database())
    except Exception:
        logger.debug("Notifier worker cleanup skipped", exc_info=True)
    finally:
        loop.close()
        _task_loop = None


def is_quiet_hours(preference: Optional[NotificationPreference]) -> bool:
    """Check if current time is within global quiet hours."""
    if not preference or not preference.quiet_hours_start or not preference.quiet_hours_end:
        return False

    # Get current time for the configured quiet-hours window (simplified UTC comparison).
    now = datetime.utcnow().time()
    start = preference.quiet_hours_start
    end = preference.quiet_hours_end

    # Handle overnight quiet hours (e.g., 22:00 to 07:00)
    if start <= end:
        return start <= now <= end
    else:
        return now >= start or now <= end


def severity_passes_filter(
    alert_severity: str,
    min_severity: Optional[str],
) -> bool:
    """Check if alert severity passes the minimum filter."""
    if not min_severity:
        return True

    severity_order = {"info": 0, "warning": 1, "critical": 2}
    alert_level = severity_order.get(alert_severity, 0)
    min_level = severity_order.get(min_severity, 0)

    return alert_level >= min_level


def _organization_id_from_alert_data(alert_data: Dict[str, Any]) -> str:
    labels = alert_data.get("labels") or {}
    org_id = str(
        alert_data.get("organization_id")
        or labels.get("organization_id")
        or "local"
    ).strip()
    return org_id or "local"


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=RETRY_BACKOFF,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=MAX_RETRIES,
)
def send_notification(
    self,
    channel_id: str,
    alert_id: str,
    alert_data: Dict[str, Any],
):
    """
    Send notification to a single channel.

    Args:
        channel_id: Target channel ID
        alert_id: Alert ID for logging
        alert_data: Alert data including title, message, severity, context
    """
    logger.info(f"Processing notification for alert {alert_id} to channel {channel_id}")

    return _run_async_in_task_loop(
        _send_notification_async(channel_id, alert_id, alert_data)
    )


async def _send_notification_async(
    channel_id: str,
    alert_id: str,
    alert_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Async implementation of notification sending."""
    async with async_session_maker() as db:
        # Load channel
        result = await db.execute(
            select(NotificationChannel).where(NotificationChannel.id == channel_id)
        )
        channel = result.scalar_one_or_none()

        if not channel:
            preset_result = await db.execute(
                select(ChannelPreset).where(ChannelPreset.id == channel_id)
            )
            preset = preset_result.scalar_one_or_none()
            if not preset:
                logger.error(f"Channel {channel_id} not found")
                return {"success": False, "error": "Channel not found"}

            if not preset.enabled:
                logger.info(f"Preset {channel_id} is disabled, skipping")
                return {"success": False, "error": "Preset disabled"}

            channel = NotificationChannel(
                id=preset.id,
                channel_type=preset.channel_type,
                label=preset.label,
                config=preset.config,
                enabled=preset.enabled,
                verified=False,
            )

        if not channel.enabled:
            logger.info(f"Channel {channel_id} is disabled, skipping")
            return {"success": False, "error": "Channel disabled"}

        # Load global preference for quiet hours and severity filter
        pref_result = await db.execute(
            select(NotificationPreference).where(
                NotificationPreference.id == GLOBAL_PREFERENCE_ID
            )
        )
        preference = pref_result.scalar_one_or_none()

        # Check quiet hours
        if is_quiet_hours(preference):
            logger.info("Global quiet hours active, skipping notification")
            return {"success": False, "error": "Quiet hours active"}

        # Check severity filter
        alert_severity = alert_data.get("severity", "info")
        if preference and not severity_passes_filter(alert_severity, preference.min_severity):
            logger.info(f"Alert severity {alert_severity} below minimum {preference.min_severity}")
            return {"success": False, "error": "Below severity threshold"}

        # Guard providers/channels from burst overload.
        # Raise to leverage Celery retry backoff instead of dropping immediately.
        try:
            await enforce_delivery_rate_limit(channel)
        except NotificationRateLimitExceeded as e:
            logger.warning(
                "Delivery rate limit hit for channel %s (%s): %s",
                channel.id,
                channel.channel_type,
                str(e),
            )
            raise

        # AI enrichment (graceful -- None means fallback to original message).
        # Worker tasks load org-scoped settings at delivery time so saved
        # settings apply even when the API process and worker are separate.
        organization_id = _organization_id_from_alert_data(alert_data)
        try:
            effective_ai_settings = await ai_settings_service.get_effective_settings(
                db,
                organization_id,
            )
            if effective_ai_settings.ai_enabled:
                ai_result = await ai_service.enrich(
                    alert_id=alert_id,
                    alert_data=alert_data,
                    preprompt=alert_data.get("ai_preprompt"),
                    regex_gate=alert_data.get("ai_regex_gate"),
                    effective_settings=effective_ai_settings,
                )
                if ai_result:
                    alert_data["ai_summary"] = ai_result.get("ai_summary", "")
                    logger.info(
                        "AI enrichment applied for alert %s (%d chars)",
                        alert_id,
                        len(alert_data["ai_summary"]),
                    )
        except Exception as e:
            logger.warning(
                "AI enrichment failed for alert %s, proceeding without: %s",
                alert_id,
                str(e),
            )
            # Continue without AI enrichment -- notification must still send

        # Render template
        rendered_body = template_service.render(
            channel.channel_type,
            alert_data,
            custom_template=channel.config.get("custom_template"),
        )

        # Send via delivery service (severity enables Pushover priority mapping)
        success = await delivery_service.deliver(
            db,
            channel,
            alert_id,
            alert_data.get("title", "Alert"),
            rendered_body,
            severity=alert_severity,
        )

        return {"success": success, "channel_id": channel_id}


@celery_app.task(
    bind=True,
    name="app.tasks.notification_tasks.send_notification_high",
    autoretry_for=(Exception,),
    retry_backoff=RETRY_BACKOFF,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=MAX_RETRIES,
)
def send_notification_high(
    self,
    channel_id: str,
    alert_id: str,
    alert_data: Dict[str, Any],
):
    """
    Send high-priority notification (critical/error severity).

    Same implementation as send_notification but routed to high priority queue.
    """
    logger.info(
        f"Processing HIGH PRIORITY notification for alert {alert_id} to channel {channel_id}"
    )
    return _run_async_in_task_loop(
        _send_notification_async(channel_id, alert_id, alert_data)
    )


def queue_notification(
    channel_id: str,
    alert_id: str,
    alert_data: Dict[str, Any],
) -> str:
    """
    Queue notification to appropriate priority queue based on severity.

    Args:
        channel_id: Target notification channel ID.
        alert_id: Alert ID for tracking.
        alert_data: Alert payload including severity.

    Returns:
        Celery task ID.
    """
    severity = alert_data.get("severity", "info").lower()

    # Route critical and error to high priority queue
    if severity in ("critical", "error"):
        task = send_notification_high.delay(channel_id, alert_id, alert_data)
        logger.debug(
            "Queued high-priority notification: task_id=%s, severity=%s",
            task.id,
            severity,
        )
    else:
        task = send_notification.delay(channel_id, alert_id, alert_data)
        logger.debug(
            "Queued normal-priority notification: task_id=%s, severity=%s",
            task.id,
            severity,
        )

    return task.id
