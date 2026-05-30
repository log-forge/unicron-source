"""
AISettings model for notifier service.

Stores org-scoped AI enrichment configuration overrides.
Fields that are None fall through to environment variable defaults
from app.core.config.Settings.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String, Boolean, Text
from sqlmodel import Field, SQLModel


class AISettings(SQLModel, table=True):
    """
    Organization-scoped AI enrichment settings.

    Singleton per organization -- only one row per org_id.
    Nullable fields mean "use env var default" (fall-through pattern).
    """

    __tablename__ = "ai_settings"
    __table_args__ = (
        {"schema": "notifications", "extend_existing": True},
    )

    # Primary key using uuid4 hex string (same pattern as NotificationChannel)
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, primary_key=True, index=True),
        description="Primary key; auto-generated uuid4 hex",
    )

    # Organization scoping -- one settings row per org (singleton pattern)
    organization_id: str = Field(
        sa_column=Column(String, nullable=False, unique=True, index=True),
        description="Organization ID; unique constraint enforces singleton per org",
    )

    # AI configuration overrides (None = use env var default)
    ai_enabled: Optional[bool] = Field(
        default=None,
        sa_column=Column(Boolean, nullable=True),
        description="Whether AI enrichment is enabled (None = use env var default)",
    )
    ollama_url: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="Ollama API URL (None = use env var default)",
    )
    ollama_model: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="Ollama model name (None = use env var default)",
    )
    ai_timeout: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
        description="AI request timeout in seconds (None = use env var default)",
    )
    ai_cache_ttl: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
        description="AI cache TTL in seconds (None = use env var default)",
    )
    ai_default_preprompt: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="Default AI preprompt text (None = use env var default)",
    )

    # Audit field
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when the settings were last updated",
    )


__all__ = ["AISettings"]
