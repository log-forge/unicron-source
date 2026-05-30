"""AlertDataQualityConfig model -- single-row settings table for data quality features."""

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class AlertDataQualityConfig(SQLModel, table=True):
    """
    Persistent configuration for alert data quality features (single-row table).

    Settings structure:
    {
        "auto_ack_enabled": false,
        "auto_ack_minutes": 240,
        "retention_mode": "forever",
        "retention_time_days": 30,
        "retention_count": 10000
    }

    Defaults: auto-ack OFF, retention forever. No configuration required for basic operation.
    """

    __tablename__ = "alertdataqualityconfig"
    __table_args__ = ({"schema": "alerting", "extend_existing": True},)

    id: int = Field(
        default=1,
        sa_column=Column(Integer, primary_key=True),
        description="Fixed ID=1 for single-row table",
    )
    settings: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description="Data quality configuration settings",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="When the config was last updated",
    )


# Default settings applied at application layer if DB row is empty or missing
DEFAULT_DATA_QUALITY_SETTINGS = {
    "auto_ack_enabled": False,
    "auto_ack_minutes": 240,
    "retention_mode": "forever",      # "forever" | "time" | "count"
    "retention_time_days": 30,
    "retention_count": 10000,
}

__all__ = ["AlertDataQualityConfig", "DEFAULT_DATA_QUALITY_SETTINGS"]
