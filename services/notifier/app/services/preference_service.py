"""Service layer for global notification preferences.

Handles get/create and update operations for the singleton preference row.
"""

from datetime import time, timezone, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification_preference_model import NotificationPreference
from app.schemas import NotificationPreferenceUpdate

GLOBAL_PREFERENCE_ID = "global"


async def get_or_create_preference(
    db: AsyncSession,
) -> NotificationPreference:
    """
    Get existing global preference or create defaults.

    If no preference exists, creates a new singleton row with
    default values (min_severity='info', empty preferred_channels).
    """
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.id == GLOBAL_PREFERENCE_ID
        )
    )
    preference = result.scalar_one_or_none()

    if not preference:
        preference = NotificationPreference(
            id=GLOBAL_PREFERENCE_ID,
            min_severity="info",
            preferred_channels=[],
        )
        db.add(preference)
        await db.commit()
        await db.refresh(preference)

    return preference


async def update_preference(
    db: AsyncSession,
    preference: NotificationPreference,
    data: NotificationPreferenceUpdate,
) -> NotificationPreference:
    """
    Update global notification preferences with provided data.

    Handles nested quiet_hours object by mapping to flat model fields.
    Only updates fields that are explicitly set in the update data.
    """
    update_data = data.model_dump(exclude_unset=True)

    # Handle nested quiet_hours object
    if "quiet_hours" in update_data and update_data["quiet_hours"]:
        qh = update_data.pop("quiet_hours")
        # Convert hour integers to time objects
        if qh.get("start_hour") is not None:
            preference.quiet_hours_start = time(hour=qh["start_hour"])
        if qh.get("end_hour") is not None:
            preference.quiet_hours_end = time(hour=qh["end_hour"])
        if qh.get("timezone"):
            preference.quiet_hours_timezone = qh["timezone"]
    elif "quiet_hours" in update_data and update_data["quiet_hours"] is None:
        # Clear quiet hours if explicitly set to null
        update_data.pop("quiet_hours")
        preference.quiet_hours_start = None
        preference.quiet_hours_end = None
        preference.quiet_hours_timezone = None

    # Handle min_severity enum
    if "min_severity" in update_data:
        severity_value = update_data.pop("min_severity")
        if severity_value is not None:
            # Handle both enum and string values
            preference.min_severity = severity_value.value if hasattr(severity_value, 'value') else severity_value

    # Apply remaining updates
    for field, value in update_data.items():
        setattr(preference, field, value)

    # Update timestamp
    preference.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(preference)
    return preference


__all__ = ["get_or_create_preference", "update_preference"]
