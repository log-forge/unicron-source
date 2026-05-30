"""Container actions REST API endpoints.

Provides endpoints for triggering container actions (restart, stop, start, kill, run_script)
that are forwarded to Herald agents via Socket.IO.

Security:
- User endpoint: Session authentication + container:control permission
- Internal endpoint: X-Internal-Secret header for service-to-service calls
"""

import uuid
from typing import Any, Dict, Optional

import socketio
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import get_socketio_server, require_admin_user
from app.core.internal_secret import verify_internal_secret_header
from app.core.logging import get_logger
from app.models.container.crud.container_crud import get_container_by_key
from app.socket.emitters.edge.container_actions import (
    ContainerActionPayload,
    ContainerActionResult,
    emit_container_action,
)
from app.utils.central_auth_client import LocalAdminSession

logger = get_logger("routes.container.actions")

router = APIRouter()


# ---- Request/Response Schemas ----


class ContainerActionRequest(BaseModel):
    """Request schema for container action endpoint."""

    container_key: str = Field(
        ...,
        description="Canonical container key to perform action on",
    )
    action_type: str = Field(
        ...,
        description="Action type: restart, stop, start, kill, run_script",
    )
    action_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional configuration for the action",
    )
    initiated_by: str = Field(
        default="manual",
        description="Who initiated: alert-rule, manual",
    )
    rule_id: Optional[str] = Field(
        default=None,
        description="Alert rule ID if triggered by rule",
    )


class ContainerActionResponse(BaseModel):
    """Response schema for container action endpoint."""

    action_id: str = Field(
        ...,
        description="UUID for tracking this action",
    )
    success: bool = Field(
        ...,
        description="Whether the action completed successfully",
    )
    message: str = Field(
        ...,
        description="Human-readable result message",
    )
    container_state: Optional[str] = Field(
        default=None,
        description="Container state after action",
    )
    duration_ms: int = Field(
        default=0,
        description="Time taken to execute the action in milliseconds",
    )


# ---- Security Dependencies ----


async def verify_internal_secret(
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
) -> None:
    """Verify the internal API secret header.

    Fail-closed: rejects requests when no secret is configured in production.
    In development (ENVIRONMENT != 'production'), allows silently (warning was logged at startup).
    """
    verify_internal_secret_header(x_internal_secret)


# Allowed action types
ALLOWED_ACTIONS = {"restart", "stop", "start", "kill", "run_script"}


def validate_action_type(action_type: str) -> None:
    """Validate the action type is allowed."""
    if action_type not in ALLOWED_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action type '{action_type}'. Allowed: {', '.join(sorted(ALLOWED_ACTIONS))}",
        )


async def resolve_container_herald(
    session: AsyncSession,
    container_key: str,
) -> tuple[str, str]:
    """Resolve container and get herald_id.

    Args:
        session: Database session
        container_key: Canonical container key

    Returns:
        Tuple of (container_db_id, herald_id)

    Raises:
        HTTPException: 404 if container not found
    """
    container = await get_container_by_key(session, container_key)
    if container is None:
        raise HTTPException(
            status_code=404,
            detail=f"Container '{container_key}' not found",
        )

    if container.herald_id is None:
        raise HTTPException(
            status_code=400,
            detail=f"Container '{container_key}' is not associated with a Herald agent",
        )

    return (container.docker_container_id or container.name), container.herald_id


# ---- User Endpoint ----


@router.post("/{container_key}/action", response_model=ContainerActionResponse)
async def execute_container_action(
    container_key: str,
    request: ContainerActionRequest,
    session: AsyncSession = Depends(get_session),
    sio: socketio.AsyncServer = Depends(get_socketio_server),
    current_user: LocalAdminSession = Depends(require_admin_user),
) -> ContainerActionResponse:
    """Execute an action on a container via its Herald agent.

    Requires authentication and container:control permission.

    Args:
        container_key: Canonical container key
        request: Action request body
        session: Database session
        sio: Socket.IO server
        current_user: Authenticated user context

    Returns:
        ContainerActionResponse with result details

    Raises:
        HTTPException 400: Invalid action type
        HTTPException 403: Permission denied
        HTTPException 404: Container not found
        HTTPException 502: Herald returned error
        HTTPException 504: Herald timeout
    """
    # Validate action type
    validate_action_type(request.action_type)

    # Resolve container and herald
    docker_container_id, herald_id = await resolve_container_herald(session, container_key)

    # Build action payload
    action_id = uuid.uuid4().hex
    payload = ContainerActionPayload(
        action_id=action_id,
        action_type=request.action_type,
        container_id=docker_container_id,
        action_config=request.action_config,
        initiated_by=request.initiated_by,
        rule_id=request.rule_id,
    )

    # Log audit trail
    user_id = current_user.user_id or "unknown"
    logger.info(
        "container_action: user=%s action=%s container=%s herald=%s",
        user_id,
        request.action_type,
        docker_container_id,
        herald_id,
    )

    # Dispatch to Herald
    result = await emit_container_action(sio, herald_id, payload, timeout=30)

    # Convert result to response
    if result.success:
        return ContainerActionResponse(
            action_id=result.action_id,
            success=True,
            message=f"Action '{request.action_type}' executed successfully on container",
            container_state=result.container_state,
            duration_ms=result.duration_ms,
        )
    else:
        # Determine error type
        if "timeout" in (result.error or "").lower() or "did not respond" in (result.error or "").lower():
            raise HTTPException(
                status_code=504,
                detail=result.error or "Herald agent timeout",
            )
        else:
            raise HTTPException(
                status_code=502,
                detail=result.error or "Herald agent error",
            )


# ---- Internal Endpoint ----


@router.post("/internal/action", response_model=ContainerActionResponse)
async def execute_container_action_internal(
    request: ContainerActionRequest,
    session: AsyncSession = Depends(get_session),
    sio: socketio.AsyncServer = Depends(get_socketio_server),
    _: None = Depends(verify_internal_secret),
) -> ContainerActionResponse:
    """Execute a container action (internal service-to-service endpoint).

    This endpoint is for alert-engine to trigger remediation actions.
    Protected by X-Internal-Secret header.

    Args:
        request: Action request body with container_key
        session: Database session
        sio: Socket.IO server

    Returns:
        ContainerActionResponse with result details

    Raises:
        HTTPException 400: Invalid action type
        HTTPException 403: Invalid internal secret
        HTTPException 404: Container not found
        HTTPException 502: Herald returned error
        HTTPException 504: Herald timeout
    """
    # Validate action type
    validate_action_type(request.action_type)

    # Resolve container and herald
    docker_container_id, herald_id = await resolve_container_herald(session, request.container_key)

    # Build action payload
    action_id = uuid.uuid4().hex
    payload = ContainerActionPayload(
        action_id=action_id,
        action_type=request.action_type,
        container_id=docker_container_id,
        action_config=request.action_config,
        initiated_by=request.initiated_by,
        rule_id=request.rule_id,
    )

    # Log audit trail for internal action
    logger.info(
        "container_action_internal: initiated_by=%s rule_id=%s action=%s container=%s herald=%s",
        request.initiated_by,
        request.rule_id,
        request.action_type,
        docker_container_id,
        herald_id,
    )

    # Dispatch to Herald
    result = await emit_container_action(sio, herald_id, payload, timeout=30)

    # Convert result to response
    if result.success:
        return ContainerActionResponse(
            action_id=result.action_id,
            success=True,
            message=f"Action '{request.action_type}' executed successfully on container",
            container_state=result.container_state,
            duration_ms=result.duration_ms,
        )
    else:
        # Determine error type
        if "timeout" in (result.error or "").lower() or "did not respond" in (result.error or "").lower():
            raise HTTPException(
                status_code=504,
                detail=result.error or "Herald agent timeout",
            )
        else:
            raise HTTPException(
                status_code=502,
                detail=result.error or "Herald agent error",
            )


__all__ = ["router"]
