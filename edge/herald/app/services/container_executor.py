"""Container executor service for Docker operations.

Provides async-safe container operations using the Docker SDK.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.core.docker_client import get_docker_client, reset_docker_client
from app.core.logging import get_logger
from docker.errors import APIError, NotFound

logger = get_logger("herald.services.container_executor")


@dataclass
class ContainerActionResult:
    """Result of a container action execution."""

    success: bool
    error: Optional[str] = None
    duration_ms: int = 0
    container_state: Optional[str] = None
    output: Optional[str] = None  # For run_script actions


class ContainerExecutor:
    """Executor for Docker container operations.

    All methods are async-safe by running blocking Docker SDK calls
    in a thread pool via asyncio.to_thread().
    """

    # Map action types to handler methods
    ACTION_HANDLERS = {
        "restart": "_restart_container",
        "stop": "_stop_container",
        "start": "_start_container",
        "kill": "_kill_container",
        "run_script": "_run_script",
    }

    async def execute_action(
        self,
        container_id: str,
        action_type: str,
        action_config: Dict[str, Any],
    ) -> ContainerActionResult:
        """Execute a container action by routing to the appropriate handler.

        Args:
            container_id: Docker container ID
            action_type: Type of action (restart, stop, start, kill, run_script)
            action_config: Configuration dict for the action

        Returns:
            ContainerActionResult with success status and details
        """
        handler_name = self.ACTION_HANDLERS.get(action_type)
        if not handler_name:
            return ContainerActionResult(
                success=False,
                error=f"Unknown action type: {action_type}",
            )

        handler = getattr(self, handler_name)
        start_time = time.time()

        try:
            result = await handler(container_id, action_config)
            result.duration_ms = int((time.time() - start_time) * 1000)
            return result
        except NotFound as e:
            logger.warning(f"Container not found: {container_id}")
            return ContainerActionResult(
                success=False,
                error=f"Container not found: {container_id}",
                duration_ms=int((time.time() - start_time) * 1000),
            )
        except APIError as e:
            logger.error(f"Docker API error for {action_type} on {container_id}: {e}")
            return ContainerActionResult(
                success=False,
                error=f"Docker API error: {str(e)}",
                duration_ms=int((time.time() - start_time) * 1000),
            )
        except Exception as e:
            logger.error(
                f"Unexpected error during {action_type} on {container_id}: {e}",
                exc_info=True,
            )
            return ContainerActionResult(
                success=False,
                error=str(e),
                duration_ms=int((time.time() - start_time) * 1000),
            )

    async def _restart_container(
        self, container_id: str, config: Dict[str, Any]
    ) -> ContainerActionResult:
        """Restart a container.

        Args:
            container_id: Docker container ID
            config: {"timeout_seconds": int} - restart timeout (default 30)
        """
        timeout = config.get("timeout_seconds", 30)

        def _sync_restart():
            client = get_docker_client()
            if client is None:
                raise RuntimeError("Docker client unavailable")
            container = client.containers.get(container_id)
            container.restart(timeout=timeout)
            container.reload()
            return container.status

        new_state = await asyncio.to_thread(_sync_restart)
        logger.info(f"Restarted container {container_id[:12]}, new state: {new_state}")

        return ContainerActionResult(
            success=True,
            container_state=new_state,
        )

    async def _stop_container(
        self, container_id: str, config: Dict[str, Any]
    ) -> ContainerActionResult:
        """Stop a container.

        Args:
            container_id: Docker container ID
            config: {"timeout_seconds": int} - stop timeout (default 30)
        """
        timeout = config.get("timeout_seconds", 30)

        def _sync_stop():
            client = get_docker_client()
            if client is None:
                raise RuntimeError("Docker client unavailable")
            container = client.containers.get(container_id)
            container.stop(timeout=timeout)
            container.reload()
            return container.status

        new_state = await asyncio.to_thread(_sync_stop)
        logger.info(f"Stopped container {container_id[:12]}, new state: {new_state}")

        return ContainerActionResult(
            success=True,
            container_state=new_state,
        )

    async def _start_container(
        self, container_id: str, config: Dict[str, Any]
    ) -> ContainerActionResult:
        """Start a container.

        Args:
            container_id: Docker container ID
            config: Currently unused
        """

        def _sync_start():
            client = get_docker_client()
            if client is None:
                raise RuntimeError("Docker client unavailable")
            container = client.containers.get(container_id)
            container.start()
            container.reload()
            return container.status

        new_state = await asyncio.to_thread(_sync_start)
        logger.info(f"Started container {container_id[:12]}, new state: {new_state}")

        return ContainerActionResult(
            success=True,
            container_state=new_state,
        )

    async def _kill_container(
        self, container_id: str, config: Dict[str, Any]
    ) -> ContainerActionResult:
        """Kill a container.

        Args:
            container_id: Docker container ID
            config: {"force": bool} - use SIGKILL if True (default), SIGTERM otherwise
        """
        force = config.get("force", True)
        signal = "SIGKILL" if force else "SIGTERM"

        def _sync_kill():
            client = get_docker_client()
            if client is None:
                raise RuntimeError("Docker client unavailable")
            container = client.containers.get(container_id)
            container.kill(signal=signal)
            container.reload()
            return container.status

        new_state = await asyncio.to_thread(_sync_kill)
        logger.info(
            f"Killed container {container_id[:12]} with {signal}, new state: {new_state}"
        )

        return ContainerActionResult(
            success=True,
            container_state=new_state,
        )

    async def _run_script(
        self, container_id: str, config: Dict[str, Any]
    ) -> ContainerActionResult:
        """Execute a script inside a container.

        Args:
            container_id: Docker container ID
            config: {
                "script": str - script content (required)
                "interpreter": str - shell interpreter (default /bin/sh)
                "working_dir": str - working directory (optional)
                "environment": dict - environment variables (optional)
                "timeout_seconds": int - execution timeout (default 60)
            }
        """
        script = config.get("script")
        if not script:
            return ContainerActionResult(
                success=False,
                error="Script content is required",
            )

        interpreter = config.get("interpreter", "/bin/sh")
        working_dir = config.get("working_dir")
        environment = config.get("environment", {})
        timeout = config.get("timeout_seconds", 60)

        def _sync_exec():
            client = get_docker_client()
            if client is None:
                raise RuntimeError("Docker client unavailable")
            container = client.containers.get(container_id)

            # Build exec command
            cmd = [interpreter, "-c", script]

            # Execute in container
            exec_result = container.exec_run(
                cmd=cmd,
                workdir=working_dir,
                environment=environment,
                demux=True,
            )

            # Get output (demux=True returns (stdout, stderr) tuple)
            stdout, stderr = exec_result.output
            stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

            # Combine output
            output = stdout_str
            if stderr_str:
                output += f"\n[stderr]: {stderr_str}" if stdout_str else f"[stderr]: {stderr_str}"

            return exec_result.exit_code, output.strip(), container.status

        try:
            # Run with timeout
            exit_code, output, state = await asyncio.wait_for(
                asyncio.to_thread(_sync_exec),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Script execution timed out after {timeout}s on {container_id[:12]}"
            )
            return ContainerActionResult(
                success=False,
                error=f"Script execution timed out after {timeout} seconds",
            )

        success = exit_code == 0
        logger.info(
            f"Script executed on {container_id[:12]}: exit_code={exit_code}, success={success}"
        )

        return ContainerActionResult(
            success=success,
            error=None if success else f"Script exited with code {exit_code}",
            container_state=state,
            output=output,
        )

    async def get_container_state(self, container_id: str) -> Optional[str]:
        """Get the current state of a container.

        Args:
            container_id: Docker container ID

        Returns:
            Container status string or None if not found
        """

        def _sync_get_state():
            client = get_docker_client()
            if client is None:
                return None
            try:
                container = client.containers.get(container_id)
                return container.status
            except NotFound:
                return None

        return await asyncio.to_thread(_sync_get_state)


# Singleton instance for app-wide use
executor = ContainerExecutor()

__all__ = ["ContainerExecutor", "ContainerActionResult", "executor"]
