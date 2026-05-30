"""Legacy session validation endpoint.

Active browser and service auth validates Better Auth cookies directly against
central/auth. This endpoint remains only to return a stable deprecation error to
old callers during the Phase 2 cleanup.
"""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/session", tags=["session"])


@router.get("/validate")
async def validate_session() -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Session validation moved to Central Auth cookie sessions",
    )
