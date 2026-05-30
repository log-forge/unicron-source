"""Socket.IO emitter for container actions to Herald agents.

This module provides the emit_container_action function to send container
action commands (restart, stop, start, kill, run_script) to specific Herald
agents and await their response.

The Herald must be connected in room f"herald:{herald_id}" for the action
to be delivered.
"""

import uuid
from typing import Any, Dict, Optional

import socketio
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.socket.validation import inspect_ack

logger = get_logger("socket.emitters.container_actions")

# Socket.IO event name for container actions
CONTAINER_ACTION_EVENT_NAME = "container:action"


# ---- Payload and Result Schemas ----


class ContainerActionPayload(BaseModel):
    """Payload for container action requests to Herald."""

    action_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="UUID for tracking this action request",
    )
    action_type: str = Field(
        ...,
        description="Action type: restart, stop, start, kill, run_script",
    )
    container_id: str = Field(
        ...,
        description="Docker container ID to perform action on",
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


class ContainerActionResult(BaseModel):
    """Result returned from Herald after executing container action."""

    action_id: str = Field(
        ...,
        description="UUID matching the request action_id",
    )
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
        description="Container state after action (running, exited, etc.)",
    )


# ---- Emitter Function ----


async def emit_container_action(
    sio: socketio.AsyncServer,
    herald_id: str,
    action_payload: ContainerActionPayload,
    timeout: int = 30,
) -> ContainerActionResult:
    """Emit container action to specific Herald and wait for result.

    Uses Socket.IO call() for request-response pattern.
    Herald must be in room f"herald:{herald_id}".

    Args:
        sio: Socket.IO async server instance
        herald_id: ID of the Herald agent to send action to
        action_payload: The container action payload
        timeout: Timeout in seconds for Herald response (default 30)

    Returns:
        ContainerActionResult with success status and details

    Raises:
        No exceptions are raised; failures are returned in the result.
    """
    target_room = f"herald:{herald_id}"
    log_ctx = f"container:action:{action_payload.action_id}"

    logger.info(
        "%s dispatching %s to herald %s for container %s",
        log_ctx,
        action_payload.action_type,
        herald_id,
        action_payload.container_id,
    )

    try:
        # Send action and wait for response
        raw_ack = await sio.call(
            CONTAINER_ACTION_EVENT_NAME,
            action_payload.model_dump(),
            to=target_room,
            timeout=timeout,
        )
    except TimeoutError:
        logger.error("%s timeout waiting for Herald response", log_ctx)
        return ContainerActionResult(
            action_id=action_payload.action_id,
            success=False,
            error=f"Herald {herald_id} did not respond within {timeout}s",
            duration_ms=timeout * 1000,
            container_state=None,
        )
    except Exception as exc:
        logger.error("%s emit failed: %s", log_ctx, exc, exc_info=True)
        return ContainerActionResult(
            action_id=action_payload.action_id,
            success=False,
            error=f"Failed to send action to Herald: {str(exc)}",
            duration_ms=0,
            container_state=None,
        )

    # Validate and parse the acknowledgment
    ok, data = inspect_ack(
        raw_ack,
        ok_data_model=ContainerActionResult,
        log_context=log_ctx,
        _logger=logger,
    )

    if not ok:
        error_msg = data if isinstance(data, str) else ", ".join(data) if data else "Unknown error"
        logger.warning("%s Herald returned error: %s", log_ctx, error_msg)
        return ContainerActionResult(
            action_id=action_payload.action_id,
            success=False,
            error=f"Herald error: {error_msg}",
            duration_ms=0,
            container_state=None,
        )

    # Return parsed result
    if isinstance(data, ContainerActionResult):
        logger.info(
            "%s completed: success=%s, state=%s, duration=%dms",
            log_ctx,
            data.success,
            data.container_state,
            data.duration_ms,
        )
        return data

    # Fallback: try to parse raw data
    try:
        result = ContainerActionResult.model_validate(data or {})
        logger.info(
            "%s completed: success=%s, state=%s, duration=%dms",
            log_ctx,
            result.success,
            result.container_state,
            result.duration_ms,
        )
        return result
    except Exception as exc:
        logger.warning("%s ack payload could not be parsed: %s", log_ctx, exc)
        return ContainerActionResult(
            action_id=action_payload.action_id,
            success=False,
            error="Invalid response format from Herald",
            duration_ms=0,
            container_state=None,
        )


__all__ = [
    "CONTAINER_ACTION_EVENT_NAME",
    "ContainerActionPayload",
    "ContainerActionResult",
    "emit_container_action",
]
