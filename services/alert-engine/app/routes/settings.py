"""REST API endpoints for data quality settings."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.core.deps import UserContext, require_authenticated_user
from app.core.logging import get_logger
from app.services.data_quality_service import data_quality_service

logger = get_logger("alert-engine.routes.settings")

router = APIRouter(prefix="/settings", tags=["settings"])


# ============================================================================
# Schemas
# ============================================================================


class DataQualitySettingsResponse(BaseModel):
    """Response schema for data quality settings."""

    auto_ack_enabled: bool = False
    auto_ack_minutes: int = 240
    retention_mode: str = Field(
        default="forever",
        description="Retention policy mode: 'forever' (no cleanup), 'time' (by age), 'count' (by count)",
    )
    retention_time_days: int = 30
    retention_count: int = 10000


class DataQualitySettingsUpdate(BaseModel):
    """Request schema for updating data quality settings."""

    auto_ack_enabled: Optional[bool] = None
    auto_ack_minutes: Optional[int] = None
    retention_mode: Optional[str] = Field(
        default=None,
        description="Retention policy mode: 'forever' | 'time' | 'count'",
    )
    retention_time_days: Optional[int] = None
    retention_count: Optional[int] = None

    model_config = {"extra": "forbid"}


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "/data-quality",
    response_model=DataQualitySettingsResponse,
    summary="Get data quality settings",
    description="Get current alert data quality settings (auto-ack, retention).",
)
async def get_data_quality_settings(
    user: UserContext = Depends(require_authenticated_user),
) -> DataQualitySettingsResponse:
    """Get current data quality settings."""
    config = await data_quality_service.get_config()
    logger.debug("User %s fetched data quality settings", user.user_id)
    return DataQualitySettingsResponse(**config)


@router.put(
    "/data-quality",
    response_model=DataQualitySettingsResponse,
    summary="Update data quality settings",
    description="Update alert data quality settings. Only provided fields are updated.",
)
async def update_data_quality_settings(
    body: DataQualitySettingsUpdate,
    user: UserContext = Depends(require_authenticated_user),
) -> DataQualitySettingsResponse:
    """Update data quality settings."""
    # Build updates dict from non-None fields
    updates: Dict[str, Any] = {}
    if body.auto_ack_enabled is not None:
        updates["auto_ack_enabled"] = body.auto_ack_enabled
    if body.auto_ack_minutes is not None:
        updates["auto_ack_minutes"] = body.auto_ack_minutes
    if body.retention_mode is not None:
        updates["retention_mode"] = body.retention_mode
    if body.retention_time_days is not None:
        updates["retention_time_days"] = body.retention_time_days
    if body.retention_count is not None:
        updates["retention_count"] = body.retention_count

    if updates:
        await data_quality_service.save_config(updates)
        logger.info(
            "User %s updated data quality settings: %s",
            user.user_id,
            list(updates.keys()),
        )

    config = await data_quality_service.get_config()
    return DataQualitySettingsResponse(**config)
