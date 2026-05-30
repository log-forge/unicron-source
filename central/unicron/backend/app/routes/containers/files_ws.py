"""Browser-facing WebSocket proxy for container file operations.

Proxies file browsing/reading between browser and go-streamer.
Browser sends list/read requests, receives responses.

Endpoint:
    /ws/files/{container_name} - File operations (auto-detect host)
    /ws/files/{host_id}/{container_name} - File operations on specific host
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

logger = get_logger("routes.containers.files_ws")

files_ws_router = APIRouter()

_file_requests: dict[str, asyncio.Future] = {}
_file_requests_lock = asyncio.Lock()


async def relay_files_to_browser(request_id: str, data: dict) -> None:
    """Called by ws_handler when files_list_response/file_read_response arrives."""
    async with _file_requests_lock:
        future = _file_requests.get(request_id)
    if future and not future.done():
        future.set_result(data)


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


@files_ws_router.websocket("/ws/files/{container_name}")
async def files_ws_no_host(websocket: WebSocket, container_name: str) -> None:
    """Files WebSocket without explicit host."""
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
    await _handle_files_session(websocket, container_name, host_id)


@files_ws_router.websocket("/ws/files/{host_id}/{container_name}")
async def files_ws_with_host(websocket: WebSocket, host_id: str, container_name: str) -> None:
    """Files WebSocket with explicit host."""
    await websocket.accept()

    user_id = await authenticate_browser_ws(websocket)
    if not user_id:
        await websocket.send_json({"type": "error", "code": "AUTH_REQUIRED", "message": "Authentication required"})
        await websocket.close(code=ws_status.WS_1008_POLICY_VIOLATION)
        return

    await _handle_files_session(websocket, container_name, host_id)


async def _handle_files_session(websocket: WebSocket, container_name: str, host_id: str) -> None:
    """Main files operation session handler. Assumes websocket is already accepted."""
    registry = get_agent_registry()
    conn = registry.get_connection(host_id)
    if conn is None or not conn.online:
        await websocket.send_json({"type": "error", "code": "AGENT_OFFLINE", "message": "Agent not connected"})
        await websocket.close(code=1011)
        return

    try:
        while True:
            try:
                msg = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            try:
                request = json.loads(msg)
            except (json.JSONDecodeError, ValueError):
                await websocket.send_text(json.dumps({"error": "Invalid JSON"}))
                continue

            action = request.get("action", "")
            request_id = str(uuid.uuid4())

            future: asyncio.Future = asyncio.get_event_loop().create_future()
            async with _file_requests_lock:
                _file_requests[request_id] = future

            try:
                if action == "list":
                    cmd = json.dumps({
                        "type": "files_list",
                        "host_id": host_id,
                        "data": {
                            "request_id": request_id,
                            "container": container_name,
                            "path": request.get("path", "/"),
                        },
                    })
                elif action == "read":
                    cmd = json.dumps({
                        "type": "file_read",
                        "host_id": host_id,
                        "data": {
                            "request_id": request_id,
                            "container": container_name,
                            "path": request.get("path", ""),
                        },
                    })
                else:
                    await websocket.send_text(json.dumps({"error": f"Unknown action: {action}"}))
                    async with _file_requests_lock:
                        _file_requests.pop(request_id, None)
                    continue

                conn_check = registry.get_connection(host_id)
                if conn_check and conn_check.online:
                    await conn_check.websocket.send_text(cmd)
                else:
                    await websocket.send_text(json.dumps({"error": "Agent disconnected"}))
                    async with _file_requests_lock:
                        _file_requests.pop(request_id, None)
                    continue

                try:
                    result = await asyncio.wait_for(future, timeout=10.0)
                    await websocket.send_text(json.dumps(result))
                except asyncio.TimeoutError:
                    await websocket.send_text(json.dumps({"error": "Request timed out"}))

            finally:
                async with _file_requests_lock:
                    _file_requests.pop(request_id, None)

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Error in files WebSocket", extra={"container": container_name})

    logger.debug("Files session ended", extra={"container": container_name})
