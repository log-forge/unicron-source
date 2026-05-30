"""Notification target introspection for rule action builder.

Queries the shared PostgreSQL database's notifications schema to return
available channels, delivery bundle groups, and presets. The frontend
RuleBuilder calls GET /notification/targets to populate the notify selector.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import UserContext, require_authenticated_user
from app.core.logging import get_logger

logger = get_logger("alert-engine.routes.notification_targets")

router = APIRouter(prefix="/notification", tags=["notifications"])


# --- Response models matching frontend interfaces (api.ts lines 5-35) ---


class NotificationTargetChannelResponse(BaseModel):
    """Matches frontend NotificationTargetChannel interface."""

    id: str
    label: Optional[str] = None
    type: Optional[str] = None
    enabled: bool


class NotificationTargetGroupResponse(BaseModel):
    """Matches frontend NotificationTargetGroup interface."""

    id: str
    name: str
    enabled: bool
    targets: Optional[Dict[str, Any]] = None


class NotificationTargetPresetResponse(BaseModel):
    """Matches frontend NotificationTargetPreset interface."""

    id: str
    label: Optional[str] = None
    type: Optional[str] = None
    enabled: bool


class NotificationTargetsResponse(BaseModel):
    """Top-level response matching frontend NotificationTargets interface."""

    channels: List[NotificationTargetChannelResponse]
    groups: List[NotificationTargetGroupResponse]
    presets: List[NotificationTargetPresetResponse]


@router.get("/targets", response_model=NotificationTargetsResponse)
async def get_notification_targets(
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> NotificationTargetsResponse:
    """Return available notification targets for the rule action builder.

    Queries the notifications schema tables (shared database) to discover
    notification channels, delivery bundles, and channel presets.
    """
    # --- Direct channels ---
    channels: List[NotificationTargetChannelResponse] = []
    try:
        channels_query = text("""
            SELECT nc.id, nc.label, nc.channel_type AS type, nc.enabled
            FROM notifications.notificationchannel nc
            ORDER BY nc.label ASC
        """)
        result = await session.execute(channels_query)
        for row in result.fetchall():
            channels.append(
                NotificationTargetChannelResponse(
                    id=str(row.id),
                    label=row.label,
                    type=row.type,
                    enabled=row.enabled,
                )
            )
    except Exception as exc:
        logger.warning("Failed to query notification channels: %s", exc)
        await session.rollback()

    # --- Notification groups ---
    groups: List[NotificationTargetGroupResponse] = []
    try:
        groups_query = text("""
            SELECT ng.id, ng.name, ng.enabled, ng.target_config AS targets
            FROM notifications.notificationgroup ng
            ORDER BY ng.name ASC
        """)
        result = await session.execute(groups_query)
        for row in result.fetchall():
            groups.append(
                NotificationTargetGroupResponse(
                    id=str(row.id),
                    name=row.name,
                    enabled=row.enabled,
                    targets=row.targets,
                )
            )
    except Exception as exc:
        logger.warning("Failed to query notification groups: %s", exc)
        await session.rollback()

    # --- Channel presets ---
    presets: List[NotificationTargetPresetResponse] = []
    try:
        presets_query = text("""
            SELECT cp.id, cp.label, cp.channel_type AS type, cp.enabled
            FROM notifications.channelpreset cp
            ORDER BY cp.label ASC
        """)
        result = await session.execute(presets_query)
        for row in result.fetchall():
            presets.append(
                NotificationTargetPresetResponse(
                    id=str(row.id),
                    label=row.label,
                    type=row.type,
                    enabled=row.enabled,
                )
            )
    except Exception as exc:
        logger.warning("Failed to query channel presets: %s", exc)
        await session.rollback()

    return NotificationTargetsResponse(
        channels=channels,
        groups=groups,
        presets=presets,
    )
