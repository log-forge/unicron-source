"""Internal API routes for service-to-service communication.

These endpoints are secured with a shared secret and are only
accessible from internal services (alert-engine, notifier).
"""

from .context import router as context_router
from .actions import router as actions_router
from .actions import state_router as actions_state_router
from .logs import router as logs_router
from .otlp_logs import router as otlp_logs_router

__all__ = ["context_router", "actions_router", "actions_state_router", "logs_router", "otlp_logs_router"]
