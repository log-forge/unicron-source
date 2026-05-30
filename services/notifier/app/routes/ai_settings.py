"""REST API endpoints for AI enrichment settings."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import UserContext, get_current_user
from app.core.logging import get_logger
from app.schemas.ai_settings_schemas import AISettingsResponse, AISettingsUpdate
from app.services.ai_settings_service import ai_settings_service

logger = get_logger("notifier.routes.ai_settings")

router = APIRouter(tags=["ai-settings"])


@router.get(
    "/ai-settings",
    response_model=AISettingsResponse,
    summary="Get AI enrichment settings",
    description="Get current AI enrichment settings.",
)
async def get_ai_settings(
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AISettingsResponse:
    """Get effective AI enrichment settings for the user's organization.

    Returns merged values: DB overrides take precedence over env-var defaults.
    """
    result = await ai_settings_service.get_effective_settings(
        db, user.organization_id
    )
    logger.info("AI settings read by user %s (org %s)", user.user_id, user.organization_id)
    return result


@router.put(
    "/ai-settings",
    response_model=AISettingsResponse,
    summary="Update AI enrichment settings",
    description="Update AI enrichment settings.",
)
async def update_ai_settings(
    data: AISettingsUpdate,
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AISettingsResponse:
    """Update AI enrichment settings for the user's organization.

    Only non-null fields in the request body are persisted as overrides.
    Changes take effect for subsequent delivery worker AI enrichment.
    """
    result = await ai_settings_service.update_settings(
        db, user.organization_id, data
    )
    logger.info(
        "AI settings updated by user %s (org %s)",
        user.user_id,
        user.organization_id,
    )
    return result


__all__ = ["router"]
