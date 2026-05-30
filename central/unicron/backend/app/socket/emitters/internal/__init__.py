"""Internal namespace emitters for service-to-service communication."""

from .alert_events import emit_container_event

__all__ = ["emit_container_event"]
