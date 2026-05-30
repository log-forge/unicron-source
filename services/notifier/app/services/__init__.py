"""Business logic services for notifier service."""

from .channel_service import (
    ChannelService,
    ChannelNotFoundError,
    PresetService,
    PresetNotFoundError,
)
from . import preference_service
from . import group_service
from . import log_service
from . import dispatch_service
from .template_service import TemplateService, template_service
from .apprise_urls import (
    build_apprise_url,
    build_email_url,
    build_slack_url,
    build_teams_url,
    build_webhook_url,
)
from .delivery_service import DeliveryService, delivery_service

__all__ = [
    "ChannelService",
    "ChannelNotFoundError",
    "PresetService",
    "PresetNotFoundError",
    "preference_service",
    "group_service",
    "log_service",
    "dispatch_service",
    "TemplateService",
    "template_service",
    "build_apprise_url",
    "build_email_url",
    "build_slack_url",
    "build_teams_url",
    "build_webhook_url",
    "DeliveryService",
    "delivery_service",
]
