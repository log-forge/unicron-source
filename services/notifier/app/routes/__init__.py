"""API route handlers for notifier service."""

from .channels import router as channels_router
from .preferences import router as preferences_router
from .groups import router as groups_router
from .templates import router as templates_router
from .dispatch import router as dispatch_router
from .logs import router as logs_router
from .ai_settings import router as ai_settings_router

__all__ = [
    "channels_router",
    "preferences_router",
    "groups_router",
    "templates_router",
    "dispatch_router",
    "logs_router",
    "ai_settings_router",
]
