"""Keyword settings service for global keyword rule configuration.

Provides config CRUD for the single-row KeywordConfig table,
following the same pattern as DataQualityService config methods.
"""

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import select

from app.core.database import session_ctx
from app.core.logging import get_logger
from app.models.keyword_config import (
    KeywordConfig,
    DEFAULT_KEYWORD_SETTINGS,
)

logger = get_logger("alert-engine.services.keyword_settings")


class KeywordSettingsService:
    """Config CRUD service for global keyword rule settings."""

    async def get_config(self) -> Dict[str, Any]:
        """Load the current keyword settings, merging defaults."""
        async with session_ctx() as session:
            result = await session.execute(
                select(KeywordConfig).where(KeywordConfig.id == 1)
            )
            row = result.scalars().first()
            if row is None:
                return dict(DEFAULT_KEYWORD_SETTINGS)
            return {**DEFAULT_KEYWORD_SETTINGS, **row.settings}

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
                select(KeywordConfig).where(KeywordConfig.id == 1)
            )
            row = result.scalars().first()

            if row is None:
                # Create initial row
                current_settings = {**DEFAULT_KEYWORD_SETTINGS, **updates}
                row = KeywordConfig(
                    id=1,
                    settings=current_settings,
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(row)
            else:
                current_settings = {
                    **DEFAULT_KEYWORD_SETTINGS,
                    **row.settings,
                    **updates,
                }
                row.settings = current_settings
                row.updated_at = datetime.now(timezone.utc)

            await session.commit()
            return current_settings


# Singleton instance
keyword_settings_service = KeywordSettingsService()

__all__ = ["KeywordSettingsService", "keyword_settings_service"]
