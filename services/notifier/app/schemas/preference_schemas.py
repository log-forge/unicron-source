"""Pydantic schemas for global notification preferences."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class SeverityLevel(str, Enum):
    """Minimum severity levels for notification filtering."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class QuietHours(BaseModel):
    """Configuration for quiet hours (do not disturb period)."""

    start_hour: int = Field(
        ..., ge=0, le=23, description="Start hour of quiet period (0-23)"
    )
    end_hour: int = Field(
        ..., ge=0, le=23, description="End hour of quiet period (0-23)"
    )
    timezone: str = Field(
        ..., description="User timezone (e.g., 'America/New_York')"
    )

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Basic timezone format validation."""
        if not v or "/" not in v:
            # Allow common formats like "UTC" or "America/New_York"
            if v not in ("UTC", "GMT"):
                if "/" not in v:
                    raise ValueError(
                        "Timezone must be in IANA format (e.g., 'America/New_York') or 'UTC'"
                    )
        return v

    model_config = {"extra": "forbid"}


class NotificationPreferenceUpdate(BaseModel):
    """Schema for updating global notification preferences."""

    quiet_hours: Optional[QuietHours] = Field(
        default=None, description="Quiet hours configuration"
    )
    min_severity: Optional[SeverityLevel] = Field(
        default=None, description="Minimum severity level for notifications"
    )
    preferred_channels: Optional[List[str]] = Field(
        default=None,
        description="Ordered list of preferred channel types (e.g., ['slack', 'email'])",
    )

    @field_validator("preferred_channels")
    @classmethod
    def validate_preferred_channels(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate channel types in preferred list."""
        if v is not None:
            valid_types = {
                "email",
                "slack",
                "teams",
                "discord",
                "telegram",
                "gotify",
                "pushover",
                "sms",
                "webhook",
            }
            for channel in v:
                if channel not in valid_types:
                    raise ValueError(
                        f"Invalid channel type '{channel}'. "
                        f"Must be one of: {', '.join(sorted(valid_types))}"
                    )
        return v

    model_config = {"extra": "forbid"}


class NotificationPreferenceResponse(BaseModel):
    """Schema for global notification preferences in API responses."""

    quiet_hours_start: Optional[int] = Field(
        default=None, description="Start hour of quiet period (0-23)"
    )
    quiet_hours_end: Optional[int] = Field(
        default=None, description="End hour of quiet period (0-23)"
    )
    quiet_hours_timezone: Optional[str] = Field(
        default=None, description="User timezone for quiet hours"
    )
    min_severity: SeverityLevel = Field(
        default=SeverityLevel.INFO, description="Minimum severity for notifications"
    )
    preferred_channels: List[str] = Field(
        default_factory=list, description="Ordered list of preferred channel types"
    )
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


__all__ = [
    "SeverityLevel",
    "QuietHours",
    "NotificationPreferenceUpdate",
    "NotificationPreferenceResponse",
]
