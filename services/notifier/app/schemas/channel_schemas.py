"""Pydantic schemas for notification channel CRUD operations."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ChannelType(str, Enum):
    """Types of notification channels."""

    EMAIL = "email"
    SLACK = "slack"
    TEAMS = "teams"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    GOTIFY = "gotify"
    WEBHOOK = "webhook"
    SMS = "sms"
    PUSHOVER = "pushover"


# Channel-specific configuration schemas for JSONB validation
class EmailChannelConfig(BaseModel):
    """Configuration for email channel."""

    smtp_host: str = Field(..., description="SMTP server hostname")
    smtp_port: int = Field(..., ge=1, le=65535, description="SMTP server port")
    username: str = Field(..., description="SMTP authentication username")
    password: str = Field(..., description="SMTP authentication password")
    to_email: str = Field(..., description="Recipient email address")
    from_email: Optional[str] = Field(
        default=None, description="Sender email address (optional)"
    )
    mode: Literal["ssl", "starttls"] = Field(
        default="starttls", description="SMTP encryption mode"
    )

    model_config = {"extra": "forbid"}


class SlackChannelConfig(BaseModel):
    """Configuration for Slack channel."""

    webhook_url: str = Field(..., description="Slack incoming webhook URL")

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook_url(cls, v: str) -> str:
        """Validate webhook URL format."""
        if not v.startswith("https://hooks.slack.com/"):
            raise ValueError("Slack webhook URL must start with https://hooks.slack.com/")
        return v

    model_config = {"extra": "forbid"}


class TeamsChannelConfig(BaseModel):
    """Configuration for Microsoft Teams channel."""

    webhook_url: str = Field(..., description="Teams incoming webhook URL")

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook_url(cls, v: str) -> str:
        """Validate webhook URL format."""
        if not v.startswith("https://"):
            raise ValueError("Teams webhook URL must use HTTPS")
        return v

    model_config = {"extra": "forbid"}


class DiscordChannelConfig(BaseModel):
    """Configuration for Discord channel."""

    webhook_url: str = Field(..., description="Discord incoming webhook URL")

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook_url(cls, v: str) -> str:
        """Validate webhook URL format."""
        if not (v.startswith("https://discord.com/api/webhooks/") or
                v.startswith("https://discordapp.com/api/webhooks/")):
            raise ValueError("Discord webhook URL must start with https://discord.com/api/webhooks/ or https://discordapp.com/api/webhooks/")
        return v

    model_config = {"extra": "forbid"}


class TelegramChannelConfig(BaseModel):
    """Configuration for Telegram channel."""

    bot_token: str = Field(..., description="Telegram bot token")
    chat_id: str = Field(..., description="Telegram chat ID")

    model_config = {"extra": "forbid"}


class GotifyChannelConfig(BaseModel):
    """Configuration for Gotify channel."""

    host: str = Field(..., description="Gotify server hostname")
    token: str = Field(..., description="Gotify application token")
    secure: bool = Field(default=True, description="Use HTTPS")
    port: Optional[int] = Field(
        default=None, ge=1, le=65535, description="Port number (optional)"
    )
    path: Optional[str] = Field(default=None, description="URL path (optional)")

    model_config = {"extra": "forbid"}


class WebhookChannelConfig(BaseModel):
    """Configuration for generic webhook channel."""

    kind: Literal["json", "form"] = Field(
        default="json", description="Payload format (json or form-encoded)"
    )
    host: str = Field(..., description="Webhook host")
    secure: bool = Field(default=True, description="Use HTTPS")
    port: Optional[int] = Field(
        default=None, ge=1, le=65535, description="Port number (optional)"
    )
    path: Optional[str] = Field(default=None, description="URL path (optional)")
    user: Optional[str] = Field(
        default=None, description="Basic auth username (optional)"
    )
    password: Optional[str] = Field(
        default=None, description="Basic auth password (optional)"
    )

    model_config = {"extra": "forbid"}


class SmsChannelConfig(BaseModel):
    """Configuration for SMS channel (Twilio)."""

    sid: str = Field(..., description="Twilio Account SID")
    token: str = Field(..., description="Twilio Auth Token")
    from_number: str = Field(..., description="Twilio source phone number")
    to_number: str = Field(..., description="Destination phone number")

    model_config = {"extra": "forbid"}


class PushoverChannelConfig(BaseModel):
    """Configuration for Pushover channel."""

    user_key: str = Field(..., description="Pushover user key")
    api_token: str = Field(..., description="Pushover application API token")

    model_config = {"extra": "forbid"}


# Channel CRUD schemas
class ChannelBase(BaseModel):
    """Base schema for notification channels."""

    name: str = Field(
        ..., min_length=1, max_length=255, description="Channel display name"
    )
    channel_type: ChannelType = Field(..., description="Type of notification channel")
    enabled: bool = Field(default=True, description="Whether the channel is active")


class ChannelCreate(ChannelBase):
    """Schema for creating a notification channel."""

    config: Dict[str, Any] = Field(
        ..., description="Channel-specific configuration"
    )
    from_preset_id: Optional[str] = Field(
        default=None, description="Optional preset ID to inherit config from"
    )

    model_config = {"extra": "forbid"}


class ChannelUpdate(BaseModel):
    """Schema for updating a notification channel. All fields optional."""

    name: Optional[str] = Field(
        default=None, min_length=1, max_length=255, description="Channel display name"
    )
    enabled: Optional[bool] = Field(
        default=None, description="Whether the channel is active"
    )
    config: Optional[Dict[str, Any]] = Field(
        default=None, description="Channel-specific configuration"
    )

    model_config = {"extra": "forbid"}


class ChannelResponse(ChannelBase):
    """Schema for channel in API responses."""

    id: str
    verified: bool
    config: Dict[str, Any] = Field(description="Channel config (sensitive fields redacted)")
    has_credential: bool = Field(
        default=False, description="Whether channel has stored credentials"
    )
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChannelListResponse(BaseModel):
    """Paginated list of channels."""

    items: List[ChannelResponse]
    total: int


# Preset CRUD schemas
class PresetBase(BaseModel):
    """Base schema for channel presets."""

    name: str = Field(
        ..., min_length=1, max_length=255, description="Preset display name"
    )
    channel_type: ChannelType = Field(..., description="Type of notification channel")
    enabled: bool = Field(default=True, description="Whether the preset is available")


class PresetCreate(PresetBase):
    """Schema for creating a channel preset."""

    config: Dict[str, Any] = Field(
        ..., description="Channel-specific configuration"
    )

    model_config = {"extra": "forbid"}


class PresetUpdate(BaseModel):
    """Schema for updating a channel preset. All fields optional."""

    name: Optional[str] = Field(
        default=None, min_length=1, max_length=255, description="Preset display name"
    )
    enabled: Optional[bool] = Field(
        default=None, description="Whether the preset is available"
    )
    config: Optional[Dict[str, Any]] = Field(
        default=None, description="Channel-specific configuration"
    )

    model_config = {"extra": "forbid"}


class PresetResponse(PresetBase):
    """Schema for preset in API responses."""

    id: str
    config: Dict[str, Any] = Field(
        description="Preset config (sensitive fields redacted)"
    )
    has_credential: bool = Field(
        default=False, description="Whether preset has stored credentials"
    )
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PresetListResponse(BaseModel):
    """Paginated list of presets."""

    items: List[PresetResponse]
    total: int


__all__ = [
    "ChannelType",
    "EmailChannelConfig",
    "SlackChannelConfig",
    "TeamsChannelConfig",
    "DiscordChannelConfig",
    "TelegramChannelConfig",
    "GotifyChannelConfig",
    "WebhookChannelConfig",
    "SmsChannelConfig",
    "PushoverChannelConfig",
    "ChannelBase",
    "ChannelCreate",
    "ChannelUpdate",
    "ChannelResponse",
    "ChannelListResponse",
    "PresetBase",
    "PresetCreate",
    "PresetUpdate",
    "PresetResponse",
    "PresetListResponse",
]
