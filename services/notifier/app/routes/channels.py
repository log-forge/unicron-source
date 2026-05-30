"""REST API endpoints for notification channel and preset CRUD operations."""

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import UserContext, get_current_user
from app.core.encryption import decrypt_config, mask_config
from app.core.logging import get_logger
from app.models.channel_model import NotificationChannel
from app.models.channel_preset_model import ChannelPreset
from app.schemas import (
    ChannelCreate,
    ChannelListResponse,
    ChannelResponse,
    ChannelUpdate,
    PresetCreate,
    PresetListResponse,
    PresetResponse,
    PresetUpdate,
)
from app.services import (
    ChannelNotFoundError,
    ChannelService,
    PresetNotFoundError,
    PresetService,
)
from app.services.delivery_service import delivery_service
from app.services import log_service

logger = get_logger("notifier.routes.channels")

router = APIRouter(tags=["channels"])


class TestNotificationResponse(BaseModel):
    """Response from test notification endpoint."""

    status: str  # "success" or "failed"
    message: str
    channel_type: Optional[str] = None


# ============================================================================
# Response Helpers (mask sensitive fields, inject has_credential)
# ============================================================================


def _build_channel_response(channel: NotificationChannel) -> ChannelResponse:
    """Build a ChannelResponse with masked config and has_credential flag."""
    masked_cfg, has_cred = mask_config(channel.config or {})
    return ChannelResponse(
        id=channel.id,
        name=channel.label,
        channel_type=channel.channel_type,
        enabled=channel.enabled,
        verified=channel.verified,
        config=masked_cfg,
        has_credential=has_cred,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )


def _build_preset_response(preset: ChannelPreset) -> PresetResponse:
    """Build a PresetResponse with masked config and has_credential flag."""
    masked_cfg, has_cred = mask_config(preset.config or {})
    return PresetResponse(
        id=preset.id,
        name=preset.label,
        channel_type=preset.channel_type,
        enabled=preset.enabled,
        config=masked_cfg,
        has_credential=has_cred,
        created_at=preset.created_at,
        updated_at=preset.updated_at,
    )


# ============================================================================
# Channel Endpoints
# ============================================================================


@router.post(
    "/channels",
    response_model=ChannelResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create notification channel",
    description="Create a new notification channel for the authenticated user.",
)
async def create_channel(
    data: ChannelCreate,
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChannelResponse:
    """Create a new notification channel."""
    service = ChannelService(db)
    channel = await service.create_channel(
        data=data,
    )
    logger.info("Created channel %s for user %s", channel.id, user.user_id)
    return _build_channel_response(channel)


@router.get(
    "/channels",
    response_model=ChannelListResponse,
    summary="List notification channels",
    description="List all notification channels for the authenticated user.",
)
async def list_channels(
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    channel_type: Optional[str] = Query(None, description="Filter by channel type"),
    enabled_only: bool = Query(False, description="Filter to enabled channels only"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=500, description="Pagination limit"),
) -> ChannelListResponse:
    """List notification channels for the user."""
    service = ChannelService(db)
    channels, total = await service.list_channels(
        channel_type=channel_type,
        enabled_only=enabled_only,
        offset=offset,
        limit=limit,
    )
    return ChannelListResponse(
        items=[_build_channel_response(c) for c in channels],
        total=total,
    )


@router.get(
    "/channels/{channel_id}",
    response_model=ChannelResponse,
    summary="Get notification channel",
    description="Get a specific notification channel by ID.",
)
async def get_channel(
    channel_id: str,
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChannelResponse:
    """Get a notification channel by ID."""
    service = ChannelService(db)
    try:
        channel = await service.get_channel_or_raise(channel_id)
    except ChannelNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found",
        )
    return _build_channel_response(channel)


@router.patch(
    "/channels/{channel_id}",
    response_model=ChannelResponse,
    summary="Update notification channel",
    description="Update an existing notification channel.",
)
async def update_channel(
    channel_id: str,
    data: ChannelUpdate,
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChannelResponse:
    """Update a notification channel."""
    service = ChannelService(db)
    try:
        channel = await service.get_channel_or_raise(channel_id)
    except ChannelNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found",
        )
    channel = await service.update_channel(channel, data)
    logger.info("Updated channel %s by user %s", channel_id, user.user_id)
    return _build_channel_response(channel)


@router.delete(
    "/channels/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete notification channel",
    description="Delete a notification channel.",
)
async def delete_channel(
    channel_id: str,
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a notification channel."""
    service = ChannelService(db)
    try:
        channel = await service.get_channel_or_raise(channel_id)
    except ChannelNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found",
        )
    await service.delete_channel(channel)
    logger.info("Deleted channel %s by user %s", channel_id, user.user_id)


@router.post(
    "/channels/{channel_id}/verify",
    response_model=ChannelResponse,
    summary="Verify notification channel",
    description="Mark a notification channel as verified.",
)
async def verify_channel(
    channel_id: str,
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChannelResponse:
    """Verify a notification channel (e.g., after email confirmation)."""
    service = ChannelService(db)
    try:
        channel = await service.get_channel_or_raise(channel_id)
    except ChannelNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found",
        )
    channel = await service.verify_channel(channel)
    logger.info("Verified channel %s by user %s", channel_id, user.user_id)
    return _build_channel_response(channel)


@router.post(
    "/channels/{channel_id}/enable",
    response_model=ChannelResponse,
    summary="Enable notification channel",
    description="Enable a disabled notification channel.",
)
async def enable_channel(
    channel_id: str,
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChannelResponse:
    """Enable a notification channel."""
    service = ChannelService(db)
    try:
        channel = await service.get_channel_or_raise(channel_id)
    except ChannelNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found",
        )
    channel = await service.toggle_channel(channel, enabled=True)
    logger.info("Enabled channel %s by user %s", channel_id, user.user_id)
    return _build_channel_response(channel)


@router.post(
    "/channels/{channel_id}/disable",
    response_model=ChannelResponse,
    summary="Disable notification channel",
    description="Disable an enabled notification channel.",
)
async def disable_channel(
    channel_id: str,
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChannelResponse:
    """Disable a notification channel."""
    service = ChannelService(db)
    try:
        channel = await service.get_channel_or_raise(channel_id)
    except ChannelNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found",
        )
    channel = await service.toggle_channel(channel, enabled=False)
    logger.info("Disabled channel %s by user %s", channel_id, user.user_id)
    return _build_channel_response(channel)


# ============================================================================
# Preset Endpoints
# ============================================================================


@router.post(
    "/presets",
    response_model=PresetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create channel preset",
    description="Create a new deployment-local channel preset.",
)
async def create_preset(
    data: PresetCreate,
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PresetResponse:
    """Create a new channel preset."""
    service = PresetService(db)
    preset = await service.create_preset(
        data=data,
    )
    logger.info("Created preset %s by user %s", preset.id, user.user_id)
    return _build_preset_response(preset)


@router.get(
    "/presets",
    response_model=PresetListResponse,
    summary="List channel presets",
    description="List all channel presets for the organization.",
)
async def list_presets(
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    channel_type: Optional[str] = Query(None, description="Filter by channel type"),
    enabled_only: bool = Query(False, description="Filter to enabled presets only"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=500, description="Pagination limit"),
) -> PresetListResponse:
    """List channel presets for the organization."""
    service = PresetService(db)
    presets, total = await service.list_presets(
        channel_type=channel_type,
        enabled_only=enabled_only,
        offset=offset,
        limit=limit,
    )
    return PresetListResponse(
        items=[_build_preset_response(p) for p in presets],
        total=total,
    )


@router.get(
    "/presets/{preset_id}",
    response_model=PresetResponse,
    summary="Get channel preset",
    description="Get a specific channel preset by ID.",
)
async def get_preset(
    preset_id: str,
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PresetResponse:
    """Get a channel preset by ID."""
    service = PresetService(db)
    try:
        preset = await service.get_preset_or_raise(preset_id)
    except PresetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preset {preset_id} not found",
        )
    return _build_preset_response(preset)


@router.patch(
    "/presets/{preset_id}",
    response_model=PresetResponse,
    summary="Update channel preset",
    description="Update an existing channel preset.",
)
async def update_preset(
    preset_id: str,
    data: PresetUpdate,
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PresetResponse:
    """Update a channel preset."""
    service = PresetService(db)
    try:
        preset = await service.get_preset_or_raise(preset_id)
    except PresetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preset {preset_id} not found",
        )
    preset = await service.update_preset(preset, data)
    logger.info("Updated preset %s by user %s", preset_id, user.user_id)
    return _build_preset_response(preset)


@router.delete(
    "/presets/{preset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete channel preset",
    description="Delete a channel preset.",
)
async def delete_preset(
    preset_id: str,
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a channel preset."""
    service = PresetService(db)
    try:
        preset = await service.get_preset_or_raise(preset_id)
    except PresetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preset {preset_id} not found",
        )
    await service.delete_preset(preset)
    logger.info("Deleted preset %s by user %s", preset_id, user.user_id)


@router.post(
    "/presets/{preset_id}/enable",
    response_model=PresetResponse,
    summary="Enable channel preset",
    description="Enable a disabled channel preset.",
)
async def enable_preset(
    preset_id: str,
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PresetResponse:
    """Enable a channel preset."""
    service = PresetService(db)
    try:
        preset = await service.get_preset_or_raise(preset_id)
    except PresetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preset {preset_id} not found",
        )
    preset = await service.toggle_preset(preset, enabled=True)
    logger.info("Enabled preset %s by user %s", preset_id, user.user_id)
    return _build_preset_response(preset)


@router.post(
    "/presets/{preset_id}/disable",
    response_model=PresetResponse,
    summary="Disable channel preset",
    description="Disable an enabled channel preset.",
)
async def disable_preset(
    preset_id: str,
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PresetResponse:
    """Disable a channel preset."""
    service = PresetService(db)
    try:
        preset = await service.get_preset_or_raise(preset_id)
    except PresetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preset {preset_id} not found",
        )
    preset = await service.toggle_preset(preset, enabled=False)
    logger.info("Disabled preset %s by user %s", preset_id, user.user_id)
    return _build_preset_response(preset)


@router.post(
    "/presets/{preset_id}/test",
    response_model=TestNotificationResponse,
    summary="Test preset delivery",
)
async def test_preset(
    preset_id: str,
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TestNotificationResponse:
    """Send a test notification using a preset's configuration."""
    service = PresetService(db)
    try:
        preset = await service.get_preset_or_raise(preset_id)
    except PresetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preset {preset_id} not found",
        )

    # Build a temporary channel object from preset config for delivery.
    # Config is stored encrypted — decrypt before passing to Apprise URL builder.
    decrypted_cfg = decrypt_config(preset.config or {})
    temp_channel = NotificationChannel(
        id=f"preset_test_{preset_id}",
        channel_type=preset.channel_type,
        label=f"Test: {preset.label}",
        config=decrypted_cfg,
        enabled=True,
        verified=False,
    )
    alert_id = f"test_preset_{preset_id}_{int(time.time())}"
    success = await delivery_service.deliver(
        db, temp_channel, alert_id,
        title="Test Notification",
        body="Test notification from LogForge - this confirms your preset is configured correctly.",
    )
    if success:
        return TestNotificationResponse(
            status="success",
            message=f"Test notification sent successfully via {preset.channel_type}",
            channel_type=preset.channel_type,
        )

    # Query the delivery log for error details
    logs = await log_service.get_logs_by_alert(db, alert_id)
    error_detail = "Delivery failed - check preset configuration"
    if logs and logs[0].error_message:
        error_detail = f"Delivery failed: {logs[0].error_message}"
    return TestNotificationResponse(
        status="failed",
        message=error_detail,
        channel_type=preset.channel_type,
    )


__all__ = ["router"]
