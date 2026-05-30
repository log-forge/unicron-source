from __future__ import annotations

from typing import Any

from app.socket.constants import (
    ALERT_FIRED_EVENT,
    ALERT_STACKED_EVENT,
    ALERT_STATE_CHANGED_EVENT,
    BROWSER_CONTAINER_EVENT,
    BROWSER_HOST_STATUS_EVENT,
    BROWSER_INITIAL_STATE_EVENT,
    BROWSER_LOGS_DATA,
    BROWSER_INVENTORY_EVENT,
    BROWSER_LOG_COLLECTION_EVENT,
    BROWSER_STATS_DATA_EVENT,
    BROWSER_TELEMETRY_HEALTH_EVENT,
    CONTAINER_FEED_ROOM,
    GLOBAL_ROOM,
    room_for_container_files,
    room_for_container_log_session,
    room_for_container_logs,
    room_for_container_stats,
    room_for_container_terminal,
)
from app.socket.socket_client import get_socket_server


class RealtimeEventBus:
    async def emit(self, event_name: str, payload: dict[str, Any], *, room: str | None = None) -> None:
        server = get_socket_server()
        if server is None:
            return
        await server.emit(event_name, payload, room=room)

    async def emit_initial_state(self, payload: dict[str, Any], *, room: str | None = None) -> None:
        await self.emit(BROWSER_INITIAL_STATE_EVENT, payload, room=room)

    async def emit_container_event(self, payload: dict[str, Any]) -> None:
        await self.emit(BROWSER_CONTAINER_EVENT, payload, room=CONTAINER_FEED_ROOM)

    async def emit_host_status(
        self,
        *,
        host_id: str,
        online: bool,
        removed: bool = False,
        reason: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"host_id": host_id, "online": online}
        if removed:
            payload["removed"] = True
        if reason:
            payload["reason"] = reason
        await self.emit(BROWSER_HOST_STATUS_EVENT, payload, room=CONTAINER_FEED_ROOM)

    async def emit_inventory_update(self, payload: dict[str, Any]) -> None:
        await self.emit(BROWSER_INVENTORY_EVENT, payload, room=CONTAINER_FEED_ROOM)

    async def emit_alert_fired(self, payload: dict[str, Any]) -> None:
        await self.emit(ALERT_FIRED_EVENT, payload, room=GLOBAL_ROOM)

    async def emit_alert_stacked(self, payload: dict[str, Any]) -> None:
        await self.emit(ALERT_STACKED_EVENT, payload, room=GLOBAL_ROOM)

    async def emit_alert_state_changed(self, payload: dict[str, Any]) -> None:
        await self.emit(ALERT_STATE_CHANGED_EVENT, payload, room=GLOBAL_ROOM)

    async def emit_monitoring_state_changed(
        self,
        *,
        container_key: str,
        host_id: str,
        monitoring_enabled: bool,
    ) -> None:
        await self.emit(
            "containers:monitoring_state_changed",
            {
                "container_key": container_key,
                "host_id": host_id,
                "monitoring_enabled": monitoring_enabled,
            },
            room=CONTAINER_FEED_ROOM,
        )

    async def emit_log_collection_state_changed(self, payload: dict[str, Any]) -> None:
        await self.emit(BROWSER_LOG_COLLECTION_EVENT, payload, room=CONTAINER_FEED_ROOM)

    async def emit_telemetry_health(self, *, host_id: str, healthy: bool, timestamp: int) -> None:
        await self.emit(
            BROWSER_TELEMETRY_HEALTH_EVENT,
            {"host_id": host_id, "healthy": healthy, "timestamp": timestamp},
            room=CONTAINER_FEED_ROOM,
        )

    async def emit_stats(self, container_key: str, payload: dict[str, Any]) -> None:
        await self.emit(BROWSER_STATS_DATA_EVENT, payload, room=room_for_container_stats(container_key))

    async def emit_live_logs(self, container_key: str, payload: dict[str, Any]) -> None:
        await self.emit(BROWSER_LOGS_DATA, payload, room=room_for_container_logs(container_key))

    async def emit_log_session(self, session_id: str, payload: dict[str, Any]) -> None:
        await self.emit(BROWSER_LOGS_DATA, payload, room=room_for_container_log_session(session_id))

    async def emit_files_response(self, request_id: str, payload: dict[str, Any]) -> None:
        await self.emit("containers:files:response", payload, room=room_for_container_files(request_id))

    async def emit_terminal(self, session_id: str, payload: dict[str, Any]) -> None:
        await self.emit("containers:terminal:data", payload, room=room_for_container_terminal(session_id))


_BUS = RealtimeEventBus()


def get_realtime_event_bus() -> RealtimeEventBus:
    return _BUS


__all__ = ["RealtimeEventBus", "get_realtime_event_bus"]
