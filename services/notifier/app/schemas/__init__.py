"""Pydantic schemas for the Notifier service API."""

from .channel_schemas import (
    ChannelType,
    EmailChannelConfig,
    SlackChannelConfig,
    TeamsChannelConfig,
    WebhookChannelConfig,
    ChannelCreate,
    ChannelUpdate,
    ChannelResponse,
    ChannelListResponse,
    PresetCreate,
    PresetUpdate,
    PresetResponse,
    PresetListResponse,
)
from .preference_schemas import (
    SeverityLevel,
    QuietHours,
    NotificationPreferenceUpdate,
    NotificationPreferenceResponse,
)
from .group_schemas import (
    GroupTargets,
    NotificationGroupCreate,
    NotificationGroupUpdate,
    NotificationGroupResponse,
    NotificationGroupListResponse,
)
from .notification_schemas import (
    NotificationStatus,
    NotificationDispatch,
    NotificationLogResponse,
    NotificationLogQuery,
    NotificationLogListResponse,
)
from .template_schemas import (
    TemplatePreviewRequest,
    TemplatePreviewResponse,
    DefaultTemplateResponse,
)
from .ai_settings_schemas import (
    AISettingsResponse,
    AISettingsUpdate,
)

__all__ = [
    # Channel schemas
    "ChannelType",
    "EmailChannelConfig",
    "SlackChannelConfig",
    "TeamsChannelConfig",
    "WebhookChannelConfig",
    "ChannelCreate",
    "ChannelUpdate",
    "ChannelResponse",
    "ChannelListResponse",
    "PresetCreate",
    "PresetUpdate",
    "PresetResponse",
    "PresetListResponse",
    # Preference schemas
    "SeverityLevel",
    "QuietHours",
    "NotificationPreferenceUpdate",
    "NotificationPreferenceResponse",
    # Group schemas
    "GroupTargets",
    "NotificationGroupCreate",
    "NotificationGroupUpdate",
    "NotificationGroupResponse",
    "NotificationGroupListResponse",
    # Notification schemas
    "NotificationStatus",
    "NotificationDispatch",
    "NotificationLogResponse",
    "NotificationLogQuery",
    "NotificationLogListResponse",
    # Template schemas
    "TemplatePreviewRequest",
    "TemplatePreviewResponse",
    "DefaultTemplateResponse",
    # AI settings schemas
    "AISettingsResponse",
    "AISettingsUpdate",
]
