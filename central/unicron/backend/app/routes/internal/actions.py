"""Internal action relay API for alert-engine remediation actions.

Translates HTTP action requests from alert-engine into WebSocket commands
to go-streamer agents via AgentRegistry, with Redis-backed response tracking.

Endpoints:
    POST /internal/actions/execute  -- Execute container action via WebSocket relay
    GET  /internal/containers/{container_key}/state  -- Get container state from cache

Security: Protected by X-Internal-Secret header validation (no user auth).
"""

import asyncio
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.logging import get_logger
from app.routes.internal.context import verify_internal_secret
from app.services.agent_registry import get_agent_registry
from app.services.alerting.action_executor import (
    cleanup_pending_action,
    register_pending_action,
    wait_for_action_result,
)
from app.services.container_cache import get_container_cache

logger = get_logger("routes.internal.actions")

# ---- Routers ----

router = APIRouter(prefix="/internal/actions", tags=["internal"])
state_router = APIRouter(prefix="/internal/containers", tags=["internal"])

# Allowed action types
ALLOWED_ACTIONS = {"restart", "stop", "start", "kill", "run_script"}

# Timeout configuration (seconds)
CONTAINER_COMMAND_TIMEOUT = 30
RUN_SCRIPT_TIMEOUT = 45

# Shell error patterns indicating distroless/scratch images
SHELL_ERROR_PATTERNS = (
    "exec failed",
    "no such file",
    "executable file not found",
    "OCI runtime exec failed",
    "not found in",
    "exec format error",
)


# ---- Request/Response Schemas ----


class ActionExecuteRequest(BaseModel):
    """Request schema for internal action execution."""

    container_key: str = Field(
        ...,
        description="Canonical container key",
    )
    action_type: str = Field(
        ...,
        description="Action type: restart, stop, start, kill, run_script",
    )
    action_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional configuration (e.g., script, interpreter for run_script)",
    )
    rule_id: Optional[str] = Field(
        default=None,
        description="Alert rule ID if triggered by a rule",
    )
    initiated_by: str = Field(
        default="alert-rule",
        description="Who initiated: alert-rule, manual, system",
    )


class ActionExecuteResponse(BaseModel):
    """Response schema for internal action execution."""

    success: bool = Field(
        ...,
        description="Whether the action completed successfully",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if action failed",
    )
    duration_ms: int = Field(
        default=0,
        description="Time taken to execute the action in milliseconds",
    )
    container_state: Optional[str] = Field(
        default=None,
        description="Container state after action (if available)",
    )


class ContainerStateResponse(BaseModel):
    """Response schema for container state lookup."""

    state: str = Field(
        ...,
        description="Current container state (running, exited, unknown, etc.)",
    )


# ---- Helper Functions ----


async def _resolve_container_for_agent(
    session: AsyncSession,
    container_key: str,
) -> tuple[str, str]:
    """Resolve container_key to (host_id, docker_container_name)."""
    from app.models.container.crud.container_crud import get_container_by_key

    container = await get_container_by_key(session, container_key)
    if container is None:
        return "", ""

    # Use herald_id as host_id, and container name for the agent command
    host_id = container.herald_id or ""
    container_name = container.name or ""
    return host_id, container_name


# ---- Endpoints ----


@router.post("/execute", response_model=ActionExecuteResponse)
async def execute_action(
    request: ActionExecuteRequest,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_internal_secret),
) -> ActionExecuteResponse:
    """Execute a container action via WebSocket relay to go-streamer agent.

    Translates an HTTP action request into a WebSocket command sent to the
    appropriate go-streamer agent via AgentRegistry.send_command(). Uses
    asyncio.Future for synchronous response tracking with timeout.

    Args:
        request: Action execution request with container_key, action_type, etc.
        session: Database session for container lookups
        _: Internal secret verification dependency

    Returns:
        ActionExecuteResponse with success/error and timing information
    """
    start_time = time.monotonic()

    # Validate action type
    if request.action_type not in ALLOWED_ACTIONS:
        return ActionExecuteResponse(
            success=False,
            error=f"Invalid action type '{request.action_type}'. Allowed: {', '.join(sorted(ALLOWED_ACTIONS))}",
        )

    # Resolve container to host_id and container name
    host_id, container_name = await _resolve_container_for_agent(session, request.container_key)

    if not host_id or not container_name:
        return ActionExecuteResponse(
            success=False,
            error=f"Container not found: {request.container_key}",
        )

    # Check agent connectivity. For multi-replica deployments, local connection
    # may be absent while host is online on another replica.
    registry = get_agent_registry()
    conn = registry.get_connection(host_id)
    if conn is None or not conn.online:
        cache = get_container_cache()
        host_online = await cache.get_host_status(host_id)
        if host_online is False:
            return ActionExecuteResponse(
                success=False,
                error=f"Agent offline for host {host_id}",
            )

    # Generate unique request ID for tracking
    request_id = uuid.uuid4().hex

    # Log audit trail
    logger.info(
        "Internal action: initiated_by=%s rule_id=%s action=%s container=%s host=%s",
        request.initiated_by,
        request.rule_id,
        request.action_type,
        request.container_key,
        host_id,
    )

    try:
        # Register pending slot for response tracking (Redis-backed for
        # cross-replica completion).
        await register_pending_action(request_id)

        if request.action_type == "run_script":
            # run_script uses container_id field (not container) per go-streamer protocol
            payload = {
                "request_id": request_id,
                "container_id": container_name,
                "script": request.action_config.get("script", ""),
            }
            sent = await registry.send_command(host_id, "run_script", payload)
            timeout = RUN_SCRIPT_TIMEOUT
        else:
            # container_command_request uses container field per go-streamer protocol
            payload = {
                "request_id": request_id,
                "container": container_name,
                "action": request.action_type,
                "params": request.action_config,
            }
            sent = await registry.send_command(
                host_id, "container_command_request", payload
            )
            timeout = CONTAINER_COMMAND_TIMEOUT

        if not sent:
            return ActionExecuteResponse(
                success=False,
                error=f"Failed to send command to agent for host {host_id}",
            )

        # Await response with timeout (local Future + Redis fallback)
        try:
            result = await wait_for_action_result(
                request_id,
                timeout_seconds=float(timeout),
            )
        except asyncio.TimeoutError:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            return ActionExecuteResponse(
                success=False,
                error=f"Agent timeout (no response within {timeout}s)",
                duration_ms=elapsed_ms,
            )

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # Check for shell-related errors on run_script (distroless/scratch images)
        if request.action_type == "run_script":
            result_error = result.get("error", "")
            if result_error and any(
                pattern in result_error.lower()
                for pattern in SHELL_ERROR_PATTERNS
            ):
                return ActionExecuteResponse(
                    success=False,
                    error=f"Container has no usable shell or entrypoint: {result_error}",
                    duration_ms=elapsed_ms,
                )

        return ActionExecuteResponse(
            success=result.get("success", False),
            error=result.get("error") or None,
            duration_ms=elapsed_ms,
            container_state=result.get("container_state"),
        )

    except Exception:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.exception(
            "Error executing action",
            extra={
                "request_id": request_id,
                "container_key": request.container_key,
                "action_type": request.action_type,
            },
        )
        return ActionExecuteResponse(
            success=False,
            error="Internal error executing action",
            duration_ms=elapsed_ms,
        )
    finally:
        await cleanup_pending_action(request_id)


@state_router.get("/{container_key}/state", response_model=ContainerStateResponse)
async def get_container_state(
    container_key: str,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_internal_secret),
) -> ContainerStateResponse:
    """Get the current state of a container from Redis cache or database.

    Looks up container state in Redis cache first (fast path),
    falls back to PostgreSQL container table.

    Args:
        container_key: Canonical container identifier
        session: Database session for fallback lookup
        _: Internal secret verification dependency

    Returns:
        ContainerStateResponse with current container state
    """
    cache = get_container_cache()

    # Try Redis cache first
    if ":" in container_key:
        host_id, container_name = container_key.split(":", 1)
        # Look up all containers for this host and find by name
        containers = await cache.get_host_containers(host_id)
        for c in containers:
            if c.get("container_key") == container_key or c.get("name") == container_name:
                return ContainerStateResponse(
                    state=c.get("status", "unknown"),
                )

    # Fallback to PostgreSQL
    from app.models.container.crud.container_crud import get_container_by_key

    container = await get_container_by_key(session, container_key)

    if container is not None:
        return ContainerStateResponse(
            state=container.status or "unknown",
        )

    return ContainerStateResponse(state="unknown")


__all__ = ["router", "state_router"]
