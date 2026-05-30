"""REST API endpoints for keyword rule settings."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.deps import UserContext, require_authenticated_user
from app.core.logging import get_logger
from app.services.keyword_settings_service import keyword_settings_service

logger = get_logger("alert-engine.routes.keyword_settings")

router = APIRouter(prefix="/keyword-settings", tags=["settings"])


# ============================================================================
# Schemas
# ============================================================================


class KeywordSettingsResponse(BaseModel):
    """Response schema for keyword settings."""

    case_sensitive: bool = True
    multi_mode: str = Field(default="any", description="'any' or 'all'")
    ignore_patterns: List[str] = Field(default_factory=list)


class KeywordSettingsUpdate(BaseModel):
    """Request schema for updating keyword settings."""

    case_sensitive: Optional[bool] = None
    multi_mode: Optional[str] = None
    ignore_patterns: Optional[List[str]] = None

    model_config = {"extra": "forbid"}


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "",
    response_model=KeywordSettingsResponse,
    summary="Get keyword settings",
    description="Get current global keyword rule settings (case sensitivity, multi-mode, ignore patterns).",
)
async def get_keyword_settings(
    user: UserContext = Depends(require_authenticated_user),
) -> KeywordSettingsResponse:
    """Get current keyword settings."""
    config = await keyword_settings_service.get_config()
    logger.debug("User %s fetched keyword settings", user.user_id)
    return KeywordSettingsResponse(**config)


@router.patch(
    "",
    response_model=KeywordSettingsResponse,
    summary="Update keyword settings",
    description="Update global keyword rule settings. Only provided fields are updated.",
)
async def update_keyword_settings(
    body: KeywordSettingsUpdate,
    user: UserContext = Depends(require_authenticated_user),
) -> KeywordSettingsResponse:
    """Update keyword settings (partial merge)."""
    # Build updates dict from non-None fields
    updates: Dict[str, Any] = {}
    if body.case_sensitive is not None:
        updates["case_sensitive"] = body.case_sensitive
    if body.multi_mode is not None:
        updates["multi_mode"] = body.multi_mode
    if body.ignore_patterns is not None:
        updates["ignore_patterns"] = body.ignore_patterns

    if updates:
        await keyword_settings_service.save_config(updates)
        logger.info(
            "User %s updated keyword settings: %s",
            user.user_id,
            list(updates.keys()),
        )

    config = await keyword_settings_service.get_config()
    return KeywordSettingsResponse(**config)
