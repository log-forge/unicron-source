"""REST API endpoints for silence CRUD operations."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import UserContext, require_authenticated_user
from app.core.logging import get_logger
from app.schemas.silence_schemas import (
    MatcherSchema,
    SilenceCreateRequest,
    SilenceListResponse,
    SilenceResponse,
    SilenceUpdateRequest,
)
from app.services.alert_audit_service import AlertAuditService
from app.services.silence_service import SilenceNotFoundError, SilenceService

logger = get_logger("alert-engine.routes.silences")

router = APIRouter(prefix="/silences", tags=["silences"])


def extract_container_ids_from_matchers(matchers: List[MatcherSchema]) -> List[str]:
    """Extract container_id values from silence matchers.

    Args:
        matchers: List of matcher schemas from silence create request

    Returns:
        List of container IDs found in matchers
    """
    container_ids = []
    for m in matchers:
        if m.name == "container_id":
            container_ids.append(m.value)
    return container_ids


def extract_container_ids_from_matcher_dicts(matchers: List[dict]) -> List[str]:
    """Extract container_id values from silence matchers (dict format).

    Args:
        matchers: List of matcher dicts from existing silence

    Returns:
        List of container IDs found in matchers
    """
    container_ids = []
    for m in matchers:
        if m.get("name") == "container_id":
            container_ids.append(m.get("value", ""))
    return container_ids


async def can_manage_silence(user: UserContext, silence) -> bool:
    """The authenticated local admin can manage any silence."""
    return True


async def filter_silences_by_access(user: UserContext, silences: List) -> List:
    """Return all silences visible to the local deployment query."""
    return list(silences)


@router.post(
    "",
    response_model=SilenceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create silence",
    description="Create a new silence for maintenance window.",
)
async def create_silence(
    body: SilenceCreateRequest,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> SilenceResponse:
    """Create a new silence."""
    service = SilenceService(session)
    silence = await service.create_silence(
        data=body,
        org_id=user.organization_id,
        user_id=user.user_id,
    )

    # Log the silence creation to audit trail
    audit_service = AlertAuditService(session)
    await audit_service.log_silence_created(
        silence_id=silence.id,
        user_id=user.user_id,
        user_email=user.email,
        organization_id=user.organization_id,
        matchers=silence.matchers,
        starts_at=silence.starts_at,
        ends_at=silence.ends_at,
        comment=body.comment,
    )

    logger.info("Created silence %s by user %s", silence.id, user.user_id)
    return SilenceResponse.model_validate(silence)


@router.get(
    "",
    response_model=SilenceListResponse,
    summary="List silences",
    description="List all silences for the authenticated user's organization.",
)
async def list_silences(
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
    active_only: bool = Query(False, description="Filter to active silences only"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=500, description="Pagination limit"),
) -> SilenceListResponse:
    """List silences for the user's organization."""
    service = SilenceService(session)
    silences, total = await service.list_silences(
        user.organization_id,
        active_only=active_only,
        offset=offset,
        limit=limit,
    )
    # Filter silences to only those the user can access
    filtered_silences = await filter_silences_by_access(user, list(silences))
    return SilenceListResponse(
        items=[SilenceResponse.model_validate(s) for s in filtered_silences],
        total=len(filtered_silences),
    )


@router.get(
    "/{silence_id}",
    response_model=SilenceResponse,
    summary="Get silence",
    description="Get a specific silence by ID.",
)
async def get_silence(
    silence_id: str,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> SilenceResponse:
    """Get a single silence by ID."""
    service = SilenceService(session)
    try:
        silence = await service.get_silence_or_raise(silence_id, user.organization_id)
    except SilenceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Silence {silence_id} not found",
        )
    return SilenceResponse.model_validate(silence)


@router.patch(
    "/{silence_id}",
    response_model=SilenceResponse,
    summary="Update silence",
    description="Update an existing silence (extend time, update comment).",
)
async def update_silence(
    silence_id: str,
    body: SilenceUpdateRequest,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> SilenceResponse:
    """Update an existing silence."""
    service = SilenceService(session)
    try:
        silence = await service.get_silence_or_raise(silence_id, user.organization_id)
    except SilenceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Silence {silence_id} not found",
        )

    # Capture current state for audit log
    old_ends_at = silence.ends_at
    old_comment = silence.comment

    # Verify user can manage this silence
    if not await can_manage_silence(user, silence):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this silence",
        )

    try:
        silence = await service.update_silence(
            silence_id,
            user.organization_id,
            body,
        )
    except SilenceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Silence {silence_id} not found",
        )

    # Log the silence update to audit trail
    changes: Dict[str, Any] = {}
    if body.ends_at is not None and body.ends_at != old_ends_at:
        changes["ends_at"] = {
            "old": old_ends_at.isoformat() if old_ends_at else None,
            "new": body.ends_at.isoformat(),
        }
    if body.comment is not None and body.comment != old_comment:
        changes["comment"] = {"old": old_comment, "new": body.comment}

    if changes:
        audit_service = AlertAuditService(session)
        await audit_service.log_silence_updated(
            silence_id=silence.id,
            user_id=user.user_id,
            user_email=user.email,
            organization_id=user.organization_id,
            changes=changes,
        )

    logger.info("Updated silence %s by user %s", silence_id, user.user_id)
    return SilenceResponse.model_validate(silence)


@router.post(
    "/{silence_id}/expire",
    response_model=SilenceResponse,
    summary="Expire silence",
    description="Expire a silence early.",
)
async def expire_silence(
    silence_id: str,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> SilenceResponse:
    """Expire a silence early."""
    service = SilenceService(session)
    try:
        silence = await service.get_silence_or_raise(silence_id, user.organization_id)
    except SilenceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Silence {silence_id} not found",
        )

    # Verify user can manage this silence
    if not await can_manage_silence(user, silence):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to expire this silence",
        )

    try:
        silence = await service.expire_silence(silence_id, user.organization_id)
    except SilenceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Silence {silence_id} not found",
        )

    # Log the silence expiration to audit trail
    audit_service = AlertAuditService(session)
    await audit_service.log_silence_expired(
        silence_id=silence.id,
        user_id=user.user_id,
        user_email=user.email,
        organization_id=user.organization_id,
    )

    logger.info("Expired silence %s by user %s", silence_id, user.user_id)
    return SilenceResponse.model_validate(silence)


@router.delete(
    "/{silence_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete silence",
    description="Delete a silence.",
)
async def delete_silence(
    silence_id: str,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a silence."""
    service = SilenceService(session)
    try:
        silence = await service.get_silence_or_raise(silence_id, user.organization_id)
    except SilenceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Silence {silence_id} not found",
        )

    # Capture silence snapshot for audit before deletion
    silence_snapshot: Dict[str, Any] = {
        "matchers": silence.matchers,
        "starts_at": silence.starts_at.isoformat() if silence.starts_at else None,
        "ends_at": silence.ends_at.isoformat() if silence.ends_at else None,
        "comment": silence.comment,
        "created_by": silence.created_by,
    }

    # Verify user can manage this silence
    if not await can_manage_silence(user, silence):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this silence",
        )

    # Log the silence deletion to audit trail before actual deletion
    audit_service = AlertAuditService(session)
    await audit_service.log_silence_deleted(
        silence_id=silence.id,
        user_id=user.user_id,
        user_email=user.email,
        organization_id=user.organization_id,
        silence_snapshot=silence_snapshot,
    )

    try:
        await service.delete_silence(silence_id, user.organization_id)
    except SilenceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Silence {silence_id} not found",
        )
    logger.info("Deleted silence %s by user %s", silence_id, user.user_id)


__all__ = ["router"]
