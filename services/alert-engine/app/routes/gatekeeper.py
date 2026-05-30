"""REST API endpoints for gatekeeper settings."""

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.database import session_ctx
from app.core.deps import UserContext, require_authenticated_user
from app.core.logging import get_logger
from app.models.gatekeeper_state import GatekeeperConfig
from app.services.action_gatekeeper import gatekeeper

logger = get_logger("alert-engine.routes.gatekeeper")

router = APIRouter(prefix="/gatekeeper", tags=["gatekeeper"])


# ============================================================================
# Schemas
# ============================================================================


class GatekeeperSettingsResponse(BaseModel):
    """Response schema for gatekeeper settings."""

    cooldown_minutes: Dict[str, int] = Field(
        description="Cooldown period in minutes per action type"
    )
    backoff_delays: list[int] = Field(
        description="Backoff delays in minutes for consecutive failures"
    )
    max_backoff_minutes: int = Field(
        description="Maximum backoff duration in minutes"
    )
    disable_after_failures: int = Field(
        description="Number of failures before rule is auto-disabled"
    )
    disable_duration_minutes: int = Field(
        description="Duration to disable rule after repeated failures"
    )
    max_actions_per_rule_per_hour: int = Field(
        description="Maximum actions per rule per hour"
    )
    max_actions_per_container_per_hour: int = Field(
        description="Maximum actions per container per hour"
    )
    verification_delay_seconds: int = Field(
        description="Delay before verifying action result"
    )
    trigger_suppression_enabled: bool = Field(
        description="When enabled, successful remediation actions temporarily suppress matching triggers for the same container."
    )
    trigger_suppression_minutes: int = Field(
        description="Suppression window in minutes after a successful remediation action."
    )
    trigger_suppression_actions: list[str] = Field(
        description="Action types that activate trigger suppression when they succeed."
    )
    trigger_suppression_rule_types: list[str] = Field(
        description="Rule trigger types affected by suppression (or ['all'])."
    )
    dedup_enabled: bool = Field(
        description="When enabled, suppress duplicate alert triggers within the dedup window."
    )
    dedup_window_seconds: int = Field(
        description="Deduplication window in seconds."
    )


class GatekeeperSettingsUpdate(BaseModel):
    """Request schema for updating gatekeeper settings."""

    cooldown_minutes: Dict[str, int] | None = None
    backoff_delays: list[int] | None = None
    max_backoff_minutes: int | None = None
    disable_after_failures: int | None = None
    disable_duration_minutes: int | None = None
    max_actions_per_rule_per_hour: int | None = None
    max_actions_per_container_per_hour: int | None = None
    verification_delay_seconds: int | None = None
    trigger_suppression_enabled: bool | None = None
    trigger_suppression_minutes: int | None = None
    trigger_suppression_actions: list[str] | None = None
    trigger_suppression_rule_types: list[str] | None = None
    dedup_enabled: bool | None = None
    dedup_window_seconds: int | None = Field(default=None, ge=1)

    model_config = {"extra": "forbid"}


async def _persist_gatekeeper_settings(settings_blob: Dict[str, Any]) -> None:
    """Persist merged gatekeeper settings to the single-row config table."""
    async with session_ctx() as session:
        result = await session.execute(
            select(GatekeeperConfig).where(GatekeeperConfig.id == 1)
        )
        row = result.scalars().first()
        now = datetime.now(timezone.utc)

        if row is None:
            row = GatekeeperConfig(id=1, settings=settings_blob, updated_at=now)
            session.add(row)
        else:
            row.settings = settings_blob
            row.updated_at = now

        await session.commit()


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "/settings",
    response_model=GatekeeperSettingsResponse,
    summary="Get gatekeeper settings",
    description="Get current gatekeeper safety settings.",
)
async def get_settings(
    user: UserContext = Depends(require_authenticated_user),
) -> GatekeeperSettingsResponse:
    """Get current gatekeeper settings."""
    await gatekeeper.ensure_initialized()
    current = gatekeeper.get_settings()
    logger.debug("User %s fetched gatekeeper settings", user.user_id)
    return GatekeeperSettingsResponse(**current)


@router.put(
    "/settings",
    response_model=GatekeeperSettingsResponse,
    summary="Update gatekeeper settings",
    description="Update gatekeeper safety settings. Only provided fields are updated.",
)
async def update_settings(
    body: GatekeeperSettingsUpdate,
    user: UserContext = Depends(require_authenticated_user),
) -> GatekeeperSettingsResponse:
    """Update gatekeeper settings."""
    await gatekeeper.ensure_initialized()

    # Build updates dict from non-None fields
    updates: Dict[str, Any] = {}
    if body.cooldown_minutes is not None:
        updates["cooldown_minutes"] = body.cooldown_minutes
    if body.backoff_delays is not None:
        updates["backoff_delays"] = body.backoff_delays
    if body.max_backoff_minutes is not None:
        updates["max_backoff_minutes"] = body.max_backoff_minutes
    if body.disable_after_failures is not None:
        updates["disable_after_failures"] = body.disable_after_failures
    if body.disable_duration_minutes is not None:
        updates["disable_duration_minutes"] = body.disable_duration_minutes
    if body.max_actions_per_rule_per_hour is not None:
        updates["max_actions_per_rule_per_hour"] = body.max_actions_per_rule_per_hour
    if body.max_actions_per_container_per_hour is not None:
        updates["max_actions_per_container_per_hour"] = body.max_actions_per_container_per_hour
    if body.verification_delay_seconds is not None:
        updates["verification_delay_seconds"] = body.verification_delay_seconds
    if body.trigger_suppression_enabled is not None:
        updates["trigger_suppression_enabled"] = body.trigger_suppression_enabled
    if body.trigger_suppression_minutes is not None:
        updates["trigger_suppression_minutes"] = body.trigger_suppression_minutes
    if body.trigger_suppression_actions is not None:
        updates["trigger_suppression_actions"] = body.trigger_suppression_actions
    if body.trigger_suppression_rule_types is not None:
        updates["trigger_suppression_rule_types"] = body.trigger_suppression_rule_types
    if body.dedup_enabled is not None:
        updates["dedup_enabled"] = body.dedup_enabled
    if body.dedup_window_seconds is not None:
        updates["dedup_window_seconds"] = body.dedup_window_seconds

    if updates:
        await gatekeeper.apply_settings(updates)
        await _persist_gatekeeper_settings(gatekeeper.get_settings())
        logger.info(
            "User %s updated gatekeeper settings: %s",
            user.user_id,
            list(updates.keys()),
        )

    current = gatekeeper.get_settings()
    return GatekeeperSettingsResponse(**current)
