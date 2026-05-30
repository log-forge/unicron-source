"""Notification preference API endpoints.

Provides GET and PATCH for global notification preferences including
quiet hours, severity filtering, and preferred channels.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import UserContext, get_current_user
from app.schemas import NotificationPreferenceUpdate, NotificationPreferenceResponse
from app.services import preference_service

router = APIRouter()


@router.get("/preferences", response_model=NotificationPreferenceResponse)
async def get_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
) -> NotificationPreferenceResponse:
    """
    Get global notification preferences.

    Creates default preferences if none exist.
    """
    preference = await preference_service.get_or_create_preference(db)

    # Map model to response (handle time to int conversion)
    return NotificationPreferenceResponse(
        quiet_hours_start=preference.quiet_hours_start.hour if preference.quiet_hours_start else None,
        quiet_hours_end=preference.quiet_hours_end.hour if preference.quiet_hours_end else None,
        quiet_hours_timezone=preference.quiet_hours_timezone,
        min_severity=preference.min_severity,
        preferred_channels=preference.preferred_channels or [],
        created_at=preference.created_at,
        updated_at=preference.updated_at,
    )


@router.patch("/preferences", response_model=NotificationPreferenceResponse)
async def update_preferences(
    data: NotificationPreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
) -> NotificationPreferenceResponse:
    """
    Update global notification preferences.

    Supports partial updates - only provided fields are updated.
    """
    preference = await preference_service.get_or_create_preference(db)
    preference = await preference_service.update_preference(db, preference, data)

    # Map model to response (handle time to int conversion)
    return NotificationPreferenceResponse(
        quiet_hours_start=preference.quiet_hours_start.hour if preference.quiet_hours_start else None,
        quiet_hours_end=preference.quiet_hours_end.hour if preference.quiet_hours_end else None,
        quiet_hours_timezone=preference.quiet_hours_timezone,
        min_severity=preference.min_severity,
        preferred_channels=preference.preferred_channels or [],
        created_at=preference.created_at,
        updated_at=preference.updated_at,
    )


__all__ = ["router"]
