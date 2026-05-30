"""AI settings service -- merges DB overrides with env-var defaults.

Provides org-scoped AI enrichment configuration. Runtime delivery workers
load effective settings from the database when they enrich alerts.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.ai_settings_model import AISettings
from app.schemas.ai_settings_schemas import AISettingsResponse, AISettingsUpdate

logger = get_logger("notifier.services.ai_settings")


class AISettingsService:
    """Service for reading and updating org-scoped AI enrichment settings."""

    async def get_effective_settings(
        self, db: AsyncSession, org_id: str
    ) -> AISettingsResponse:
        """Return effective AI settings (DB override > env-var default).

        For each field: if the DB value is not None, use it;
        otherwise fall through to the env-var default from ``settings``.

        Args:
            db: Async database session.
            org_id: Organization ID to scope settings lookup.

        Returns:
            AISettingsResponse with all fields populated (effective values).
        """
        db_record = await self._get_by_org(db, org_id)

        return AISettingsResponse(
            ai_enabled=(
                db_record.ai_enabled
                if db_record and db_record.ai_enabled is not None
                else settings.AI_ENABLED
            ),
            ollama_url=(
                db_record.ollama_url
                if db_record and db_record.ollama_url is not None
                else settings.OLLAMA_URL
            ),
            ollama_model=(
                db_record.ollama_model
                if db_record and db_record.ollama_model is not None
                else settings.OLLAMA_MODEL
            ),
            ai_timeout=(
                db_record.ai_timeout
                if db_record and db_record.ai_timeout is not None
                else settings.AI_TIMEOUT
            ),
            ai_cache_ttl=(
                db_record.ai_cache_ttl
                if db_record and db_record.ai_cache_ttl is not None
                else settings.AI_CACHE_TTL
            ),
            ai_default_preprompt=(
                db_record.ai_default_preprompt
                if db_record and db_record.ai_default_preprompt is not None
                else settings.AI_DEFAULT_PREPROMPT
            ),
            has_overrides=db_record is not None,
        )

    async def update_settings(
        self, db: AsyncSession, org_id: str, data: AISettingsUpdate
    ) -> AISettingsResponse:
        """Upsert AI settings overrides for the organization.

        Creates a new DB record if none exists, or updates the existing one.
        Only non-None fields from ``data`` are persisted as overrides.
        Delivery workers load the saved values by organization when alerts are
        enriched, so the settings singleton remains the environment default.

        Args:
            db: Async database session.
            org_id: Organization ID to scope settings.
            data: Update payload with optional override fields.

        Returns:
            AISettingsResponse with effective values after the update.
        """
        db_record = await self._get_by_org(db, org_id)

        if db_record is None:
            # Create new record
            db_record = AISettings(organization_id=org_id)
            db.add(db_record)

        # Apply non-None fields from the update payload
        update_fields = data.model_dump(exclude_none=True)
        for field_name, value in update_fields.items():
            setattr(db_record, field_name, value)

        db_record.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(db_record)

        effective = await self.get_effective_settings(db, org_id)

        logger.info(
            "Updated AI settings for org %s: %s",
            org_id,
            list(update_fields.keys()),
        )

        return effective

    async def _get_by_org(
        self, db: AsyncSession, org_id: str
    ) -> AISettings | None:
        """Fetch the AI settings record for an organization.

        Returns None if no override record exists (org uses env-var defaults).
        """
        stmt = select(AISettings).where(
            AISettings.organization_id == org_id
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


# Module-level singleton
ai_settings_service = AISettingsService()
