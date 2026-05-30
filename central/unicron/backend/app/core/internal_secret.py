"""Shared validation for service-to-service internal API secret headers."""

from __future__ import annotations

import hmac

from fastapi import HTTPException

from app.core.config import settings


def verify_internal_secret_header(provided_secret: str | None) -> None:
    """Validate X-Internal-Secret semantics.

    Production is fail-closed when no secret is configured. Development allows
    missing secret for local workflows.
    """
    configured_secret = (settings.INTERNAL_API_SECRET or "").strip()
    if not configured_secret:
        if settings.ENVIRONMENT == "production":
            raise HTTPException(
                status_code=403,
                detail="Internal API secret not configured",
            )
        return

    if not provided_secret or not hmac.compare_digest(provided_secret, configured_secret):
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing internal API secret",
        )


__all__ = ["verify_internal_secret_header"]
