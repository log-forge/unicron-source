"""Notification delivery service using Apprise."""

from typing import Dict, List, Optional

import apprise
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_config
from app.core.logging import get_scrubbed_logger, scrub_text
from app.models.channel_model import NotificationChannel
from app.services.apprise_urls import build_apprise_url, build_pushover_url
from app.services import log_service

logger = get_scrubbed_logger("delivery_service")


class DeliveryService:
    """Handles notification delivery to configured channels."""

    def _build_apprise(
        self, channel: NotificationChannel, severity: Optional[str] = None
    ) -> apprise.Apprise:
        """Build a fresh Apprise instance for channel.

        CRITICAL: Decrypts channel config before building the Apprise URL.
        No caching -- always rebuilds to avoid stale credentials after
        channel config updates. The URL-build cost is negligible.

        For Pushover channels, severity is used to inject priority params
        into the Apprise URL (emergency/high/normal).
        """
        ap = apprise.Apprise()
        try:
            decrypted_config = decrypt_config(channel.config)
            if channel.channel_type == "pushover" and severity:
                url = build_pushover_url(decrypted_config, severity=severity)
            else:
                url = build_apprise_url(channel.channel_type, decrypted_config)
            ap.add(url)
        except ValueError as e:
            logger.error(f"Failed to build URL for channel {channel.id}: {e}")
            raise
        return ap

    async def deliver(
        self,
        db: AsyncSession,
        channel: NotificationChannel,
        alert_id: str,
        title: str,
        body: str,
        severity: Optional[str] = None,
    ) -> bool:
        """
        Deliver notification to a single channel.

        Creates a log entry to track the delivery attempt.

        Args:
            db: Database session
            channel: Channel to deliver to
            alert_id: ID of the triggering alert
            title: Notification title
            body: Notification body
            severity: Alert severity for priority mapping (used by Pushover)

        Returns:
            True on success, False on failure.
        """
        # Create pending log entry
        log = await log_service.create_log(
            db,
            alert_id,
            channel.id,
            channel.channel_type,
            "pending",
        )

        try:
            ap = self._build_apprise(channel, severity=severity)
            success = ap.notify(title=title, body=body)

            if success:
                await log_service.update_log_status(db, log, "sent")
                logger.info(
                    f"Notification sent to channel {channel.label} ({channel.channel_type})"
                )
                return True
            else:
                await log_service.update_log_status(
                    db,
                    log,
                    "failed",
                    error_message="Apprise notify returned False",
                )
                logger.warning(f"Notification failed for channel {channel.label}")
                return False

        except Exception as e:
            await log_service.update_log_status(
                db,
                log,
                "failed",
                error_message=scrub_text(str(e)[:1000]),
            )
            logger.error(f"Notification error for channel {channel.label}: {e}")
            return False

    async def deliver_to_channels(
        self,
        db: AsyncSession,
        channels: List[NotificationChannel],
        alert_id: str,
        title: str,
        body: str,
        severity: Optional[str] = None,
    ) -> Dict[str, bool]:
        """
        Deliver notification to multiple channels.

        Skips disabled channels automatically.

        Args:
            db: Database session
            channels: List of channels to deliver to
            alert_id: ID of the triggering alert
            title: Notification title
            body: Notification body
            severity: Alert severity for priority mapping (used by Pushover)

        Returns:
            Dict of channel_id -> success boolean.
        """
        results = {}
        for channel in channels:
            if not channel.enabled:
                logger.debug(f"Skipping disabled channel {channel.label}")
                continue
            results[channel.id] = await self.deliver(
                db, channel, alert_id, title, body, severity=severity
            )
        return results


# Singleton instance for app-wide use
delivery_service = DeliveryService()


__all__ = ["DeliveryService", "delivery_service"]
