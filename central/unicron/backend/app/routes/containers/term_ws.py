"""Browser-facing WebSocket proxy for container terminal sessions.

Proxies terminal I/O between browser (xterm.js) and go-streamer exec sessions.
Browser sends raw keystrokes + resize messages.
go-streamer sends exec_output back via agent WebSocket.

Endpoints:
    /ws/term/{container_id} - Terminal for container (auto-detect host)
    /ws/term/{host_id}/{container_id} - Terminal for container on specific host
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

logger = get_logger("routes.containers.term_ws")

term_ws_router = APIRouter()

# Active terminal sessions: session_id -> browser WebSocket
_term_sessions: dict[str, WebSocket] = {}
_term_sessions_lock = asyncio.Lock()


async def relay_exec_to_browser(session_id: str, data: dict) -> None:
    """Called by ws_handler when exec_output/exec_started/exec_exit arrives from agent."""
    async with _term_sessions_lock:
        ws = _term_sessions.get(session_id)
    if ws is None:
        return

    msg_type = data.get("_relay_type", "")
    try:
        if msg_type == "exec_output":
            await ws.send_text(data.get("data", ""))
        elif msg_type == "exec_started":
            if not data.get("success"):
                await ws.send_text(f"\r\nFailed to start terminal: {data.get('message', 'unknown error')}\r\n")
                await ws.close()
        elif msg_type == "exec_exit":
            await ws.send_text(f"\r\nSession ended (exit code: {data.get('code', 0)})\r\n")
            await ws.close()
    except Exception:
        pass


async def _find_host_for_container(container_id: str) -> Optional[str]:
    """Find which host owns a container by checking cache."""
    from app.services.container_cache import get_container_cache
    cache = get_container_cache()
    host_ids = await cache.get_all_hosts()
    for host_id in host_ids:
        hid = host_id.decode("utf-8") if isinstance(host_id, bytes) else str(host_id)
        containers = await cache.get_host_containers(hid)
        for c in containers:
            if c.get("container_id", "").startswith(container_id) or c.get("name") == container_id:
                return hid
    return None


@term_ws_router.websocket("/ws/term/{container_id}")
async def terminal_ws_no_host(websocket: WebSocket, container_id: str) -> None:
    """Terminal WebSocket without explicit host (auto-detect)."""
    await websocket.accept()

    user_id = await authenticate_browser_ws(websocket)
    if not user_id:
        await websocket.send_json({"type": "error", "code": "AUTH_REQUIRED", "message": "Authentication required"})
        await websocket.close(code=ws_status.WS_1008_POLICY_VIOLATION)
        return

    host_id = await _find_host_for_container(container_id)
    if not host_id:
        await websocket.send_json({"type": "error", "code": "HOST_NOT_FOUND", "message": "No host found for container"})
        await websocket.close(code=1011)
        return
    await _handle_terminal_session(websocket, container_id, host_id)


@term_ws_router.websocket("/ws/term/{host_id}/{container_id}")
async def terminal_ws_with_host(websocket: WebSocket, host_id: str, container_id: str) -> None:
    """Terminal WebSocket with explicit host."""
    await websocket.accept()

    user_id = await authenticate_browser_ws(websocket)
    if not user_id:
        await websocket.send_json({"type": "error", "code": "AUTH_REQUIRED", "message": "Authentication required"})
        await websocket.close(code=ws_status.WS_1008_POLICY_VIOLATION)
        return

    await _handle_terminal_session(websocket, container_id, host_id)


async def _handle_terminal_session(websocket: WebSocket, container_id: str, host_id: str) -> None:
    """Main terminal session handler. Assumes websocket is already accepted."""
    registry = get_agent_registry()
    conn = registry.get_connection(host_id)
    if conn is None or not conn.online:
        await websocket.send_json({"type": "error", "code": "AGENT_OFFLINE", "message": "Agent not connected"})
        await websocket.close(code=1011)
        return

    session_id = str(uuid.uuid4())

    async with _term_sessions_lock:
        _term_sessions[session_id] = websocket

    try:
        start_cmd = json.dumps({
            "type": "exec_start",
            "host_id": host_id,
            "data": {
                "session_id": session_id,
                "container": container_id,
                "rows": 24,
                "cols": 80,
            },
        })
        await conn.websocket.send_text(start_cmd)

        while True:
            try:
                message = await websocket.receive()
            except WebSocketDisconnect:
                break

            if "text" in message:
                text = message["text"]
                try:
                    parsed = json.loads(text)
                    if parsed.get("type") == "resize":
                        resize_cmd = json.dumps({
                            "type": "exec_resize",
                            "host_id": host_id,
                            "data": {
                                "session_id": session_id,
                                "rows": parsed.get("rows", 24),
                                "cols": parsed.get("cols", 80),
                            },
                        })
                        await conn.websocket.send_text(resize_cmd)
                        continue
                except (json.JSONDecodeError, ValueError):
                    pass

                input_cmd = json.dumps({
                    "type": "exec_input",
                    "host_id": host_id,
                    "data": {
                        "session_id": session_id,
                        "data": text,
                    },
                })
                await conn.websocket.send_text(input_cmd)

            elif "bytes" in message:
                input_cmd = json.dumps({
                    "type": "exec_input",
                    "host_id": host_id,
                    "data": {
                        "session_id": session_id,
                        "data": message["bytes"].decode("utf-8", errors="replace"),
                    },
                })
                await conn.websocket.send_text(input_cmd)

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Error in terminal WebSocket", extra={"session_id": session_id})
    finally:
        async with _term_sessions_lock:
            _term_sessions.pop(session_id, None)

        try:
            stop_cmd = json.dumps({
                "type": "exec_stop",
                "host_id": host_id,
                "data": {"session_id": session_id},
            })
            conn = registry.get_connection(host_id)
            if conn and conn.online:
                await conn.websocket.send_text(stop_cmd)
        except Exception:
            pass

        logger.debug("Terminal session ended", extra={"session_id": session_id, "container_id": container_id})
