"""High-level notification dispatch orchestration."""

from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.models.channel_model import NotificationChannel
from app.models.channel_preset_model import ChannelPreset
from app.models.notification_group_model import NotificationGroup

logger = get_logger("dispatch_service")


def _extract_fingerprint(alert_data: Dict[str, Any]) -> str:
    raw = str(alert_data.get("fingerprint") or "").strip()
    if raw:
        return raw
    labels = alert_data.get("labels") or {}
    for key in ("dedup_fingerprint", "fingerprint"):
        value = str(labels.get(key) or "").strip()
        if value:
            return value
    return "none"


def _idempotency_key(alert_id: str, channel_id: str, fingerprint: str) -> str:
    return f"notifier:idempotency:{alert_id}:{channel_id}:{fingerprint}"


async def _acquire_idempotency(
    alert_id: str,
    channel_id: str,
    fingerprint: str,
) -> tuple[bool, Optional[str]]:
    if not settings.NOTIFIER_IDEMPOTENCY_ENABLED:
        return True, None

    key = _idempotency_key(alert_id, channel_id, fingerprint)
    try:
        redis = await get_redis()
        acquired = await redis.set(
            key,
            "1",
            ex=max(1, int(settings.NOTIFIER_IDEMPOTENCY_TTL_SECONDS)),
            nx=True,
        )
        return bool(acquired), key
    except Exception as exc:
        # Fail open: preserve delivery when Redis is unavailable.
        logger.warning("Idempotency check skipped due to Redis error: %s", exc)
        return True, None


async def _release_idempotency(key: Optional[str]) -> None:
    if not key:
        return
    try:
        redis = await get_redis()
        await redis.delete(key)
    except Exception as exc:
        logger.warning("Failed to release idempotency key %s: %s", key, exc)


async def dispatch_alert(
    db: AsyncSession,
    alert_id: str,
    alert_data: Dict[str, Any],
    channel_ids: Optional[List[str]] = None,
    group_ids: Optional[List[str]] = None,
    preset_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Dispatch alert notifications.

    Queues Celery tasks for each target channel.

    Args:
        db: Database session
        alert_id: Alert identifier
        alert_data: Alert data (title, message, severity, context)
        channel_ids: Specific channel IDs to notify
        group_ids: Notification group IDs to notify
        preset_ids: Specific preset IDs to notify

    Returns:
        Dict with queued task info
    """
    target_channel_ids: set[str] = set()

    def normalize_ids(values: Optional[Iterable[str]]) -> list[str]:
        if not values:
            return []
        return [
            str(value or "").strip()
            for value in values
            if str(value or "").strip()
        ]

    async def add_enabled_channels(ids: Iterable[str]) -> None:
        requested = normalize_ids(ids)
        if not requested:
            return
        result = await db.execute(
            select(NotificationChannel.id).where(
                NotificationChannel.id.in_(requested),
                NotificationChannel.enabled == True,
            )
        )
        target_channel_ids.update(str(row[0]) for row in result.fetchall())

    async def add_enabled_presets(ids: Iterable[str]) -> None:
        requested = normalize_ids(ids)
        if not requested:
            return
        result = await db.execute(
            select(ChannelPreset.id).where(
                ChannelPreset.id.in_(requested),
                ChannelPreset.enabled == True,
            )
        )
        target_channel_ids.update(str(row[0]) for row in result.fetchall())

    # Collect direct channel IDs
    await add_enabled_channels(channel_ids or [])
    await add_enabled_presets(preset_ids or [])

    # Resolve delivery bundles into their enabled direct channels and presets.
    requested_group_ids = normalize_ids(group_ids)
    if requested_group_ids:
        group_result = await db.execute(
            select(NotificationGroup).where(
                NotificationGroup.id.in_(requested_group_ids),
                NotificationGroup.enabled == True,
            )
        )
        group_channel_ids: list[str] = []
        group_preset_ids: list[str] = []
        for group in group_result.scalars().all():
            target_config = group.target_config or {}
            group_channel_ids.extend(normalize_ids(target_config.get("channel_ids")))
            group_preset_ids.extend(normalize_ids(target_config.get("preset_ids")))
        await add_enabled_channels(group_channel_ids)
        await add_enabled_presets(group_preset_ids)

    # Queue tasks (late import to avoid circular import)
    from app.tasks.notification_tasks import queue_notification

    fingerprint = _extract_fingerprint(alert_data)
    tasks_queued = []
    duplicate_suppressed = 0
    for channel_id in target_channel_ids:
        acquired, idempotency_key = await _acquire_idempotency(
            alert_id=alert_id,
            channel_id=channel_id,
            fingerprint=fingerprint,
        )
        if not acquired:
            duplicate_suppressed += 1
            logger.debug(
                "Suppressed duplicate notification task: alert=%s channel=%s fingerprint=%s",
                alert_id,
                channel_id,
                fingerprint,
            )
            continue

        try:
            task_id = queue_notification(channel_id, alert_id, alert_data)
        except Exception:
            await _release_idempotency(idempotency_key)
            raise

        tasks_queued.append({"channel_id": channel_id, "task_id": task_id})
        logger.info(f"Queued notification task {task_id} for channel {channel_id}")

    return {
        "alert_id": alert_id,
        "channels_targeted": len(target_channel_ids),
        "tasks_queued": tasks_queued,
        "duplicate_suppressed": duplicate_suppressed,
    }
