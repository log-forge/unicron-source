"""
AISettings model for notifier AI enrichment configuration.

Stores organization-scoped overrides in the shared notifications schema.
Nullable override fields fall back to notifier environment defaults.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlmodel import Field, SQLModel


class AISettings(SQLModel, table=True):
    """Organization-scoped AI enrichment settings."""

    __tablename__ = "ai_settings"
    __table_args__ = {"schema": "notifications"}

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, primary_key=True, index=True),
        description="Primary key; auto-generated uuid4 hex",
    )

    organization_id: str = Field(
        sa_column=Column(String, nullable=False, unique=True, index=True),
        description="Organization ID; unique constraint enforces one settings row per org",
    )

    ai_enabled: Optional[bool] = Field(
        default=None,
        sa_column=Column(Boolean, nullable=True),
        description="Whether AI enrichment is enabled",
    )
    ollama_url: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="Ollama API URL",
    )
    ollama_model: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="Ollama model name",
    )
    ai_timeout: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
        description="AI request timeout in seconds",
    )
    ai_cache_ttl: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
        description="AI cache TTL in seconds",
    )
    ai_default_preprompt: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="Default AI preprompt text",
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when the settings were last updated",
    )


__all__ = ["AISettings"]
