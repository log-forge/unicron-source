"""Browser-facing WebSocket proxy for container log streaming.

Proxies log streaming between browser and go-streamer logs sessions.
Browser connects, receives real-time log lines.

Endpoints:
    /ws/logs/{container_name} - Logs for container (auto-detect host)
    /ws/logs/{host_id}/{container_name} - Logs for container on specific host
"""

import asyncio
import json
import uuid
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette import status as ws_status

from app.core.logging import get_logger
from app.core.ws_auth import authenticate_browser_ws
from app.services.agent_registry import get_agent_registry

logger = get_logger("routes.containers.logs_ws")

logs_ws_router = APIRouter()

_log_sessions: dict[str, WebSocket] = {}
_log_sessions_lock = asyncio.Lock()
_log_session_metadata: dict[str, dict[str, str]] = {}


def _parse_docker_log_line(line: str) -> tuple[str, str] | None:
    """Parse Docker log line with timestamp prefix.

    Docker logs with timestamps=true have format: "2024-01-27T10:30:45.123456789Z message"
    Returns (timestamp, message) tuple, or None if line should be skipped (empty).
    """
    if not line or not line.strip():
        return None

    # Docker timestamp format: ISO8601 with nanoseconds
    # Typical: "2024-01-27T10:30:45.123456789Z actual log message"
    parts = line.split(" ", 1)

    # Check if first part looks like a timestamp (has 'T' and is long enough)
    if len(parts[0]) > 20 and "T" in parts[0]:
        timestamp = parts[0]
        # Message is the second part, or empty if none
        message = parts[1].strip() if len(parts) > 1 else ""
        # Skip if message is empty (blank log line)
        if not message:
            return None
        return timestamp, message

    # No timestamp prefix found - use entire line as message
    message = line.strip()
    if not message:
        return None
    return "", message


def get_log_session_metadata(session_id: str) -> dict[str, str] | None:
    """Get container metadata for a log session. Used by ws_handler for Redis publishing."""
    return _log_session_metadata.get(session_id)


async def relay_logs_to_browser(session_id: str, data: dict) -> None:
    """Called by ws_handler when logs_output/logs_error arrives from agent."""
    async with _log_sessions_lock:
        ws = _log_sessions.get(session_id)
    if ws is None:
        return

    try:
        msg_type = data.get("_relay_type", "")
        if msg_type == "logs_output":
            raw_line = data.get("data", "")
            parsed = _parse_docker_log_line(raw_line)
            # Skip empty/blank lines
            if parsed is None:
                return
            timestamp, message = parsed
            # Send in format frontend expects: {timestamp, message}
            await ws.send_text(json.dumps({
                "timestamp": timestamp,
                "message": message,
            }))
        elif msg_type == "logs_error":
            await ws.send_text(json.dumps({"type": "error", "error": data.get("error", "")}))
    except Exception:
        pass


async def _find_host_for_container(container_name: str) -> Optional[str]:
    """Find which host owns a container by checking cache."""
    from app.services.container_cache import get_container_cache
    cache = get_container_cache()
    host_ids = await cache.get_all_hosts()
    for host_id in host_ids:
        hid = host_id.decode("utf-8") if isinstance(host_id, bytes) else str(host_id)
        containers = await cache.get_host_containers(hid)
        for c in containers:
            if c.get("name") == container_name or c.get("container_id", "").startswith(container_name):
                return hid
    return None


@logs_ws_router.websocket("/ws/logs/{container_name}")
async def logs_ws_no_host(websocket: WebSocket, container_name: str) -> None:
    """Logs WebSocket without explicit host."""
    await websocket.accept()

    user_id = await authenticate_browser_ws(websocket)
    if not user_id:
        await websocket.send_json({"type": "error", "code": "AUTH_REQUIRED", "message": "Authentication required"})
        await websocket.close(code=ws_status.WS_1008_POLICY_VIOLATION)
        return

    host_id = await _find_host_for_container(container_name)
    if not host_id:
        await websocket.send_json({"type": "error", "code": "HOST_NOT_FOUND", "message": "No host found for container"})
        await websocket.close(code=1011)
        return
    await _handle_logs_session(websocket, container_name, host_id)


@logs_ws_router.websocket("/ws/logs/{host_id}/{container_name}")
async def logs_ws_with_host(websocket: WebSocket, host_id: str, container_name: str) -> None:
    """Logs WebSocket with explicit host."""
    await websocket.accept()

    user_id = await authenticate_browser_ws(websocket)
    if not user_id:
        await websocket.send_json({"type": "error", "code": "AUTH_REQUIRED", "message": "Authentication required"})
        await websocket.close(code=ws_status.WS_1008_POLICY_VIOLATION)
        return

    await _handle_logs_session(websocket, container_name, host_id)


async def _handle_logs_session(websocket: WebSocket, container_name: str, host_id: str) -> None:
    """Main logs streaming session handler. Assumes websocket is already accepted."""
    registry = get_agent_registry()
    conn = registry.get_connection(host_id)
    if conn is None or not conn.online:
        await websocket.send_json({"type": "error", "code": "AGENT_OFFLINE", "message": "Agent not connected"})
        await websocket.close(code=1011)
        return

    session_id = str(uuid.uuid4())

    async with _log_sessions_lock:
        _log_sessions[session_id] = websocket
        _log_session_metadata[session_id] = {
            "container_name": container_name,
            "host_id": host_id,
        }

    try:
        start_cmd = json.dumps({
            "type": "logs_start",
            "host_id": host_id,
            "data": {
                "session_id": session_id,
                "container": container_name,
                "follow": True,
                "tail": "100",
                "since": "",
            },
        })
        await conn.websocket.send_text(start_cmd)

        while True:
            try:
                msg = await websocket.receive_text()
                try:
                    parsed = json.loads(msg)
                    if parsed.get("type") == "tail":
                        stop_cmd = json.dumps({
                            "type": "logs_stop",
                            "host_id": host_id,
                            "data": {"session_id": session_id},
                        })
                        conn_check = registry.get_connection(host_id)
                        if conn_check and conn_check.online:
                            await conn_check.websocket.send_text(stop_cmd)

                        restart_cmd = json.dumps({
                            "type": "logs_start",
                            "host_id": host_id,
                            "data": {
                                "session_id": session_id,
                                "container": container_name,
                                "follow": parsed.get("follow", True),
                                "tail": str(parsed.get("tail", "100")),
                                "since": parsed.get("since", ""),
                            },
                        })
                        conn_check = registry.get_connection(host_id)
                        if conn_check and conn_check.online:
                            await conn_check.websocket.send_text(restart_cmd)
                except (json.JSONDecodeError, ValueError):
                    pass
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Error in logs WebSocket", extra={"session_id": session_id})
    finally:
        async with _log_sessions_lock:
            _log_sessions.pop(session_id, None)
            _log_session_metadata.pop(session_id, None)

        try:
            stop_cmd = json.dumps({
                "type": "logs_stop",
                "host_id": host_id,
                "data": {"session_id": session_id},
            })
            conn = registry.get_connection(host_id)
            if conn and conn.online:
                await conn.websocket.send_text(stop_cmd)
        except Exception:
            pass

        logger.debug("Logs session ended", extra={"session_id": session_id, "container": container_name})
