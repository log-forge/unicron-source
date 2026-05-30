"""Data quality service for alert lifecycle management.

Provides:
- Auto-ack sweep: Firing alerts older than a configurable timer automatically
  transition to acknowledged status.
- Retention cleanup: Acknowledged alerts beyond the retention policy are purged.
- Alert-history partition maintenance: keeps monthly partitions pre-created and
  drops expired partitions by retention window.
- Config CRUD: Single-row JSONB config with sensible defaults.

Background loop runs every 60 seconds for auto-ack and once daily for
retention/partition maintenance.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import delete, func, select, text

from app.core.config import settings
from app.core.database import session_ctx
from app.core.logging import get_logger
from app.models.alert_state import AlertState
from app.models.data_quality_config import (
    AlertDataQualityConfig,
    DEFAULT_DATA_QUALITY_SETTINGS,
)
from app.services.alert_websocket import broadcast_alert_state_change
from app.services.state_service import clear_dedup_fingerprint, retire_alert_fingerprint

logger = get_logger("alert-engine.services.data_quality")


class DataQualityService:
    """
    Background service for alert data quality management.

    Runs a periodic sweep loop that:
    1. Auto-acknowledges firing alerts past the configured timer (every 60s).
    2. Cleans up old acknowledged alerts per retention policy (once daily).
    """

    def __init__(self) -> None:
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._partition_maintenance_supported: bool = True

    # ------------------------------------------------------------------
    # Config CRUD
    # ------------------------------------------------------------------

    async def get_config(self) -> Dict[str, Any]:
        """Load the current data quality config, merging defaults."""
        return await self._load_config()

    async def _load_config(self) -> Dict[str, Any]:
        """Load config from DB, falling back to defaults for missing keys."""
        async with session_ctx() as session:
            result = await session.execute(
                select(AlertDataQualityConfig).where(
                    AlertDataQualityConfig.id == 1
                )
            )
            row = result.scalars().first()
            if row is None:
                return dict(DEFAULT_DATA_QUALITY_SETTINGS)
            return {**DEFAULT_DATA_QUALITY_SETTINGS, **row.settings}

    async def save_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Save config updates, merging with existing settings.

        Args:
            updates: Partial settings dict to merge.

        Returns:
            The full merged settings after save.
        """
        async with session_ctx() as session:
            result = await session.execute(
                select(AlertDataQualityConfig).where(
                    AlertDataQualityConfig.id == 1
                )
            )
            row = result.scalars().first()

            if row is None:
                # Create initial row
                current_settings = {**DEFAULT_DATA_QUALITY_SETTINGS, **updates}
                row = AlertDataQualityConfig(
                    id=1,
                    settings=current_settings,
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(row)
            else:
                current_settings = {
                    **DEFAULT_DATA_QUALITY_SETTINGS,
                    **row.settings,
                    **updates,
                }
                row.settings = current_settings
                row.updated_at = datetime.now(timezone.utc)

            await session.commit()
            return current_settings

    # ------------------------------------------------------------------
    # Auto-ack sweep
    # ------------------------------------------------------------------

    async def _auto_ack_sweep(self) -> int:
        """
        Auto-acknowledge firing alerts past the configured timer.

        Queries firing alerts where last_seen < (now - auto_ack_minutes),
        marks them acknowledged, and broadcasts each change via WebSocket.

        Returns:
            Number of alerts auto-acknowledged.
        """
        config = await self._load_config()

        if not config.get("auto_ack_enabled", False):
            return 0

        auto_ack_minutes = config.get("auto_ack_minutes", 240)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=auto_ack_minutes)
        now = datetime.now(timezone.utc)

        async with session_ctx() as session:
            # Find firing alerts past the cutoff
            result = await session.execute(
                select(AlertState).where(
                    AlertState.status == "firing",
                    AlertState.last_seen < cutoff,
                )
            )
            stale_alerts = list(result.scalars().all())

            if not stale_alerts:
                return 0

            # Retire each active fingerprint so the same condition can fire again.
            for alert in stale_alerts:
                alert.status = "acknowledged"
                alert.updated_at = now
                retire_alert_fingerprint(alert)

            await session.commit()

        # Clear dedup keys and broadcast state changes outside the DB session
        for alert in stale_alerts:
            await clear_dedup_fingerprint(
                (alert.annotations or {}).get("dedup_fingerprint", "")
            )
            try:
                await broadcast_alert_state_change(
                    alert_id=alert.id,
                    status="acknowledged",
                    action="auto_acknowledged",
                    updated_at=now,
                    organization_id=alert.organization_id,
                )
            except Exception as e:
                logger.warning(
                    "Failed to broadcast auto-ack for alert %s: %s",
                    alert.id,
                    str(e),
                )

        return len(stale_alerts)

    # ------------------------------------------------------------------
    # Retention cleanup
    # ------------------------------------------------------------------

    async def _retention_cleanup(self) -> int:
        """
        Delete old acknowledged alerts per the retention policy.

        Modes:
        - "forever": No cleanup (return 0).
        - "time": Delete acknowledged alerts older than retention_time_days.
        - "count": Keep at most retention_count acknowledged alerts.

        IMPORTANT: Only acknowledged alerts are ever purged. Firing alerts
        are NEVER deleted by retention cleanup.

        Returns:
            Number of alerts deleted.
        """
        config = await self._load_config()
        retention_mode = config.get("retention_mode", "forever")

        if retention_mode == "forever":
            return 0

        deleted = 0

        if retention_mode == "time":
            days = config.get("retention_time_days", 30)
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            async with session_ctx() as session:
                result = await session.execute(
                    delete(AlertState).where(
                        AlertState.status == "acknowledged",
                        AlertState.updated_at < cutoff,
                    )
                )
                deleted = result.rowcount
                await session.commit()

        elif retention_mode == "count":
            max_count = config.get("retention_count", 10000)

            async with session_ctx() as session:
                # Count total acknowledged alerts
                count_result = await session.execute(
                    select(func.count()).select_from(AlertState).where(
                        AlertState.status == "acknowledged"
                    )
                )
                total = count_result.scalar() or 0

                if total <= max_count:
                    return 0

                to_delete = total - max_count

                # Get IDs of oldest acknowledged alerts
                oldest_result = await session.execute(
                    select(AlertState.id)
                    .where(AlertState.status == "acknowledged")
                    .order_by(AlertState.updated_at.asc())
                    .limit(to_delete)
                )
                ids_to_delete = [row[0] for row in oldest_result.all()]

                if ids_to_delete:
                    await session.execute(
                        delete(AlertState).where(
                            AlertState.id.in_(ids_to_delete)
                        )
                    )
                    deleted = len(ids_to_delete)
                    await session.commit()

        if deleted > 0:
            logger.info(
                "Retention cleanup (%s): purged %d acknowledged alerts",
                retention_mode,
                deleted,
            )

        return deleted

    @staticmethod
    def _month_start_with_offset(base: datetime, month_offset: int) -> datetime:
        """Return UTC month start for ``base`` shifted by ``month_offset`` months."""
        month_index = (base.month - 1) + month_offset
        year = base.year + (month_index // 12)
        month = (month_index % 12) + 1
        return datetime(year, month, 1, tzinfo=timezone.utc)

    async def _partition_maintenance(self) -> None:
        """Ensure future alert-history partitions exist and drop expired ones."""
        if not settings.ALERT_HISTORY_PARTITION_MAINTENANCE_ENABLED:
            return
        if not self._partition_maintenance_supported:
            return

        lookahead_months = max(0, int(settings.ALERT_HISTORY_PARTITION_LOOKAHEAD_MONTHS))
        retention_months = max(1, int(settings.ALERT_HISTORY_PARTITION_RETENTION_MONTHS))
        base_month = datetime.now(timezone.utc).replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        try:
            async with session_ctx() as session:
                for offset in range(lookahead_months + 1):
                    partition_month = self._month_start_with_offset(base_month, offset)
                    await session.execute(
                        text("SELECT alerting.create_alerthistory_partition(:partition_date)"),
                        {"partition_date": partition_month.date()},
                    )

                await session.execute(
                    text(
                        "SELECT alerting.drop_old_alerthistory_partitions(:retention_months)"
                    ),
                    {"retention_months": retention_months},
                )
                await session.commit()
        except Exception as exc:
            err = str(exc).lower()
            if "does not exist" in err or "undefined function" in err:
                self._partition_maintenance_supported = False
                logger.warning(
                    "Disabling alert-history partition maintenance; migration functions are missing: %s",
                    str(exc),
                )
            else:
                logger.warning("Alert-history partition maintenance failed: %s", str(exc))

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background data quality sweep loop."""
        if self._running:
            logger.warning("Data quality service already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._data_quality_loop())
        logger.info("Data quality service started (60s sweep interval)")

    async def stop(self) -> None:
        """Stop the background data quality sweep loop gracefully."""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("Data quality service stopped")

    async def _data_quality_loop(self) -> None:
        """
        Main sweep loop.

        - Auto-ack sweep runs every iteration (60s).
        - Retention cleanup runs once every 1440 iterations (~24 hours).
        """
        iteration = 0
        while self._running:
            try:
                acked = await self._auto_ack_sweep()
                if acked > 0:
                    logger.info("Auto-ack sweep: %d alerts acknowledged", acked)

                # Ensure partition runway immediately at startup and then daily.
                if iteration == 0 or iteration % 1440 == 0:
                    await self._partition_maintenance()

                # Run retention cleanup daily (every 1440 iterations at 60s each)
                if iteration > 0 and iteration % 1440 == 0:
                    deleted = await self._retention_cleanup()
                    if deleted > 0:
                        logger.info("Retention cleanup: %d alerts purged", deleted)

                iteration += 1
            except Exception as e:
                logger.exception("Data quality sweep failed: %s", e)

            await asyncio.sleep(60)


# Singleton instance
data_quality_service = DataQualityService()

__all__ = ["DataQualityService", "data_quality_service"]
