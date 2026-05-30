"""Socket.IO client for receiving events from Central."""

import asyncio
from typing import Callable, Optional

import socketio

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("alert-engine.services.central_events")


class CentralEventsClient:
    """
    Async Socket.IO client to receive container events from Central.

    Connects to Central's internal namespace and subscribes to container
    lifecycle events (start, stop, die, create, destroy). These events can
    be used to:
    - Trigger absence rule evaluation on stop events
    - Invalidate rule scope caches on container changes
    - Update container state for real-time alerting
    """

    def __init__(
        self,
        url: Optional[str] = None,
        path: Optional[str] = None,
        namespace: Optional[str] = None,
    ):
        self.url = url or settings.CENTRAL_SOCKETIO_URL
        self.path = path or settings.CENTRAL_SOCKETIO_PATH
        self.namespace = namespace or settings.CENTRAL_INTERNAL_NAMESPACE

        self._client: Optional[socketio.AsyncClient] = None
        self._connected = False
        self._reconnect_task: Optional[asyncio.Task] = None
        self._should_reconnect = True

        # Exponential backoff settings
        self._initial_delay = 1.0
        self._max_delay = 60.0
        self._current_delay = self._initial_delay

        # Event handlers
        self._container_event_handlers: list[Callable] = []

    @property
    def is_connected(self) -> bool:
        """Check if the client is currently connected."""
        return self._connected and self._client is not None

    def on_container_event(self, handler: Callable) -> None:
        """
        Register a handler for container events.

        Handler signature: async def handler(data: dict) -> None
        Data contains: container_id, action, herald_id, organization_id, timestamp, metadata
        """
        self._container_event_handlers.append(handler)

    async def connect(self) -> bool:
        """
        Connect to Central's internal namespace.

        Returns:
            True if connection successful, False otherwise.
        """
        if self._connected:
            return True

        try:
            self._client = socketio.AsyncClient(
                reconnection=False,  # We handle reconnection ourselves
                logger=False,
                engineio_logger=False,
            )

            # Register event handlers
            self._setup_handlers()

            logger.info(
                "Connecting to Central Socket.IO",
                extra={
                    "url": self.url,
                    "path": self.path,
                    "namespace": self.namespace,
                },
            )

            await self._client.connect(
                self.url,
                socketio_path=self.path,
                namespaces=[self.namespace],
                wait_timeout=10,
            )

            self._connected = True
            self._current_delay = self._initial_delay  # Reset backoff on success
            logger.info("Connected to Central Socket.IO internal namespace")
            return True

        except Exception as e:
            logger.error(
                "Failed to connect to Central Socket.IO",
                exc_info=True,
                extra={"url": self.url, "error": str(e)},
            )
            self._connected = False
            return False

    def _setup_handlers(self) -> None:
        """Set up Socket.IO event handlers."""
        if self._client is None:
            return

        @self._client.on("connect", namespace=self.namespace)
        async def on_connect() -> None:
            logger.info("Socket.IO connected to namespace %s", self.namespace)

        @self._client.on("disconnect", namespace=self.namespace)
        async def on_disconnect() -> None:
            logger.warning("Socket.IO disconnected from namespace %s", self.namespace)
            self._connected = False
            if self._should_reconnect:
                self._schedule_reconnect()

        @self._client.on("container:event", namespace=self.namespace)
        async def on_container_event(data: dict) -> None:
            logger.debug(
                "Received container event",
                extra={
                    "container_id": data.get("container_id"),
                    "action": data.get("action"),
                    "herald_id": data.get("herald_id"),
                },
            )
            # Call registered handlers
            for handler in self._container_event_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(data)
                    else:
                        handler(data)
                except Exception:
                    logger.error(
                        "Error in container event handler",
                        exc_info=True,
                        extra={"container_id": data.get("container_id")},
                    )

        @self._client.on("connect_error", namespace=self.namespace)
        async def on_connect_error(data: dict) -> None:
            logger.error("Socket.IO connection error: %s", data)
            self._connected = False
            if self._should_reconnect:
                self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        """Schedule a reconnection attempt with exponential backoff."""
        if self._reconnect_task and not self._reconnect_task.done():
            return  # Already have a reconnect scheduled

        async def reconnect() -> None:
            while self._should_reconnect and not self._connected:
                logger.info(
                    "Attempting to reconnect in %.1f seconds",
                    self._current_delay,
                )
                await asyncio.sleep(self._current_delay)

                if not self._should_reconnect:
                    break

                success = await self.connect()
                if success:
                    break

                # Exponential backoff
                self._current_delay = min(
                    self._current_delay * 2,
                    self._max_delay,
                )

        self._reconnect_task = asyncio.create_task(reconnect())

    async def disconnect(self) -> None:
        """Disconnect from Central."""
        self._should_reconnect = False

        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                logger.warning("Error during disconnect", exc_info=True)

        self._connected = False
        self._client = None
        logger.info("Disconnected from Central Socket.IO")

    async def wait(self) -> None:
        """Wait for the client to disconnect (blocking)."""
        if self._client:
            await self._client.wait()


# Singleton instance for app-wide use
central_events_client = CentralEventsClient()


__all__ = ["CentralEventsClient", "central_events_client"]
