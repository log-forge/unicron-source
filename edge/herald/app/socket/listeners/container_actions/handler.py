"""Container action event handlers for Herald Socket.IO client.

Handles container:action events from Central to execute Docker operations.
"""

import time
from typing import Any, Dict

import socketio
from app.core.logging import get_logger
from app.services.container_executor import executor

logger = get_logger("herald.socket.listeners.container_actions")

__all__ = ["register_container_action_events"]


def register_container_action_events(sio: socketio.AsyncClient) -> None:
    """Register container action event handlers on Herald client.

    Args:
        sio: Socket.IO AsyncClient instance
    """

    async def handle_container_action(data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle container action request from Central.

        Expected data:
            - action_id: str - unique action identifier
            - action_type: str - type of action (restart, stop, start, kill, run_script)
            - container_id: str - Docker container ID
            - action_config: dict - action-specific configuration
            - initiated_by: str - user who initiated the action (optional)
            - rule_id: str - alert rule ID if triggered by rule (optional)

        Returns:
            - action_id: str
            - success: bool
            - error: str | None
            - duration_ms: int
            - container_state: str | None
            - output: str | None (for run_script)
        """
        action_id = data.get("action_id", "unknown")
        action_type = data.get("action_type", "unknown")
        container_id = data.get("container_id", "")

        logger.info(
            f"Received container action: {action_type} for {container_id[:12] if container_id else 'unknown'} "
            f"(action_id={action_id})"
        )

        start_time = time.time()

        # Validate required fields
        if not container_id:
            logger.warning(f"Container action {action_id} missing container_id")
            return {
                "action_id": action_id,
                "success": False,
                "error": "container_id is required",
                "duration_ms": 0,
                "container_state": None,
                "output": None,
            }

        if not action_type or action_type == "unknown":
            logger.warning(f"Container action {action_id} missing action_type")
            return {
                "action_id": action_id,
                "success": False,
                "error": "action_type is required",
                "duration_ms": 0,
                "container_state": None,
                "output": None,
            }

        try:
            result = await executor.execute_action(
                container_id=container_id,
                action_type=action_type,
                action_config=data.get("action_config", {}),
            )

            duration_ms = int((time.time() - start_time) * 1000)

            response = {
                "action_id": action_id,
                "success": result.success,
                "error": result.error,
                "duration_ms": duration_ms,
                "container_state": result.container_state,
                "output": result.output,
            }

            if result.success:
                logger.info(
                    f"Container action {action_type} completed successfully on {container_id[:12]} "
                    f"(duration={duration_ms}ms, state={result.container_state})"
                )
            else:
                logger.warning(
                    f"Container action {action_type} failed on {container_id[:12]}: {result.error}"
                )

            return response

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"Container action {action_type} raised exception on {container_id[:12]}: {e}",
                exc_info=True,
            )
            return {
                "action_id": action_id,
                "success": False,
                "error": str(e),
                "duration_ms": duration_ms,
                "container_state": None,
                "output": None,
            }

    # Register the event handler
    sio.on("container:action", handler=handle_container_action)
    logger.debug("Registered container:action event handler")
