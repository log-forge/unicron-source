"""KeywordConfig model -- single-row settings table for global keyword rule settings."""

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class KeywordConfig(SQLModel, table=True):
    """
    Persistent configuration for global keyword rule settings (single-row table).

    Settings structure:
    {
        "case_sensitive": true,
        "multi_mode": "any",
        "ignore_patterns": []
    }

    Defaults: case_sensitive ON, multi_mode "any", no ignore patterns.
    """

    __tablename__ = "keywordconfig"
    __table_args__ = ({"schema": "alerting", "extend_existing": True},)

    id: int = Field(
        default=1,
        sa_column=Column(Integer, primary_key=True),
        description="Fixed ID=1 for single-row table",
    )
    settings: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description="Keyword configuration settings",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="When the config was last updated",
    )


# Default settings applied at application layer if DB row is empty or missing
DEFAULT_KEYWORD_SETTINGS = {
    "case_sensitive": True,
    "multi_mode": "any",        # "any" | "all"
    "ignore_patterns": [],      # list of strings to skip
}

__all__ = ["KeywordConfig", "DEFAULT_KEYWORD_SETTINGS"]
