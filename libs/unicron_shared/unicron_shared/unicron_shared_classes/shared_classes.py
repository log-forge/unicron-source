from enum import Enum


class HeraldStatus(str, Enum):
    unknown = "unknown"
    healthy = "healthy"
    unhealthy = "unhealthy"
    degraded = "degraded"
    failed = "failed"
