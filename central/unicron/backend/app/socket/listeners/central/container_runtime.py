from __future__ import annotations

import uuid
from typing import Any

import socketio

from app.core.access.herald_visibility import list_visible_herald_ids
from app.core.access.role_resolver import ActorContext, list_accessible_container_keys
from app.core.database import session_ctx
from app.core.deps.scope import enforce_container_access
from app.core.logging import get_logger
from app.models.container.crud.container_crud import get_container_by_key
from app.services.agent_registry import get_agent_registry
from app.services.browser_session_registry import get_browser_session_registry
from app.services.container_cache import get_container_cache
from app.services.realtime_event_bus import get_realtime_event_bus
from app.socket.constants import (
    BROWSER_FILES_REQUEST,
    BROWSER_INITIAL_STATE_EVENT,
    BROWSER_LOGS_DATA,
    BROWSER_LOGS_START,
    BROWSER_LOGS_STOP,
    BROWSER_STATS_SUBSCRIBE,
    BROWSER_STATS_UNSUBSCRIBE,
    BROWSER_TERMINAL_INPUT,
    BROWSER_TERMINAL_RESIZE,
    BROWSER_TERMINAL_START,
    BROWSER_TERMINAL_STOP,
    CONTAINER_FEED_ROOM,
    room_for_container_files,
    room_for_container_logs,
    room_for_container_stats,
    room_for_container_terminal,
)
from app.socket.auth import require_socket_auth, require_socket_permissions
from fastapi import HTTPException

logger = get_logger(__name__)


async def _require_browser_event(sio: socketio.AsyncServer, sid: str) -> dict[str, Any] | None:
    try:
        ctx = await require_socket_auth(sio, sid)
        await get_browser_session_registry().refresh_sid_lease(sid)
        return ctx
    except HTTPException:
        logger.debug("Socket event rejected: unauthorized", extra={"sid": sid})
        return None


async def _require_container_event_access(
    sio: socketio.AsyncServer,
    sid: str,
    *,
    container_key: str,
    min_role: str,
    permissions: dict[str, list[str]],
) -> dict[str, Any] | None:
    try:
        ctx = await require_socket_permissions(sio, sid, permissions)
        await get_browser_session_registry().refresh_sid_lease(sid)
        if ctx.get("rbac_enabled") and ctx.get("actor"):
            async with session_ctx() as session:
                await enforce_container_access(session, ActorContext(**ctx["actor"]), container_key, min_role=min_role)
        return ctx
    except HTTPException:
        logger.debug(
            "Socket container event rejected: unauthorized",
            extra={"sid": sid, "container_key": container_key, "permissions": permissions},
        )
        return None


async def cleanup_browser_sessions_for_sid(sio: socketio.AsyncServer, sid: str) -> None:
    registry = get_agent_registry()
    session_registry = get_browser_session_registry()
    cleanup = await session_registry.cleanup_sid(sid)

    for _session_id, record in cleanup.logs:
        await sio.leave_room(sid, room_for_container_logs(record.container_key))

    for host_id, container_key, source in cleanup.stopped_logs:
        await registry.send_command(host_id, "fast_tail_stop", {"container_key": container_key, "source": source})

    for session_id, record in cleanup.terms:
        await registry.send_command(record.host_id, "exec_stop", {"session_id": session_id})

    for _host_id, container_key in cleanup.stopped_stats:
        await sio.leave_room(sid, room_for_container_stats(container_key))
        async with session_ctx() as session:
            container = await get_container_by_key(session, container_key)
        if container is not None:
            await registry.send_command(
                container.herald_id or container_key.split(":", 1)[0],
                "command",
                {
                    "action": "stop_stats",
                    "container_id": container.docker_container_id or container.name,
                    "container_key": container.container_key,
                },
            )


async def start_container_log_view(
    sio: socketio.AsyncServer,
    sid: str,
    data: dict[str, Any],
) -> dict[str, str] | None:
    container_key = str((data or {}).get("container_key") or "").strip()
    host_id = str((data or {}).get("host_id") or "").strip()
    if not container_key or not host_id:
        return None
    if not await _require_container_event_access(
        sio,
        sid,
        container_key=container_key,
        min_role="read_only",
        permissions={"resource": ["logs"]},
    ):
        return None

    session_registry = get_browser_session_registry()

    async with session_ctx() as session:
        container = await get_container_by_key(session, container_key)
    if container is None:
        return None

    target_host_id = str(container.herald_id or host_id or container_key.split(":", 1)[0]).strip()
    monitoring_enabled = bool(getattr(container, "monitoring_enabled", False))
    if not monitoring_enabled:
        try:
            monitoring_enabled = await get_container_cache().get_monitoring_state(container_key)
        except Exception:
            logger.debug(
                "Failed to resolve canonical monitoring state for log view",
                exc_info=True,
                extra={"container_key": container_key},
            )
    source = "monitored" if monitoring_enabled else "live_only"
    history_tail = ""
    history_since = ""
    if source == "live_only":
        history_tail = str((data or {}).get("history_tail") or "").strip()
        history_since = str((data or {}).get("history_since") or "").strip()
    session_id = uuid.uuid4().hex
    first_viewer = await session_registry.register_log_session(
        sid=sid,
        session_id=session_id,
        host_id=target_host_id,
        container_key=container_key,
        source=source,
        history_tail=history_tail,
        history_since=history_since,
    )
    await sio.enter_room(sid, room_for_container_logs(container_key))
    if source == "live_only":
        recent_rows = await session_registry.get_recent_log_rows(container_key)
        for payload in recent_rows:
            await sio.emit(BROWSER_LOGS_DATA, payload, to=sid)
    if first_viewer:
        await get_agent_registry().send_command(
            target_host_id,
            "fast_tail_start",
            {
                "container_key": container_key,
                "source": source,
                "history_tail": history_tail,
                "history_since": history_since,
            },
        )
    return {"session_id": session_id}


async def stop_container_log_view(
    sio: socketio.AsyncServer,
    sid: str,
    data: dict[str, Any],
) -> None:
    session_id = str((data or {}).get("session_id") or "").strip()
    if not session_id:
        return

    session_registry = get_browser_session_registry()
    record = await session_registry.get_log_session(session_id)
    if record is None or record.sid != sid:
        return
    if not await _require_container_event_access(
        sio,
        sid,
        container_key=record.container_key,
        min_role="read_only",
        permissions={"resource": ["logs"]},
    ):
        return

    record, is_last = await session_registry.remove_log_session(session_id)
    if record is None:
        return
    if not await session_registry.sid_has_log_subscription(sid, record.container_key):
        await sio.leave_room(sid, room_for_container_logs(record.container_key))
    if is_last:
        await get_agent_registry().send_command(
            record.host_id,
            "fast_tail_stop",
            {"container_key": record.container_key, "source": record.source},
        )


def register(sio: socketio.AsyncServer) -> None:
    @sio.on(BROWSER_INITIAL_STATE_EVENT)
    async def container_initial_state(sid: str, data: dict[str, Any] | None = None):
        ctx = await _require_browser_event(sio, sid)
        if not ctx:
            return
        await sio.enter_room(sid, CONTAINER_FEED_ROOM)
        registry = get_agent_registry()
        hosts = registry.list_hosts()
        cache = get_container_cache()
        monitoring_states = await cache.get_all_monitoring_states()
        if ctx.get("rbac_enabled") and ctx.get("actor"):
            async with session_ctx() as session:
                actor = ActorContext(**ctx["actor"])
                visible_hosts = set(await list_visible_herald_ids(session, actor))
                visible_container_keys = set(await list_accessible_container_keys(session, actor, min_role="read_only"))
            hosts = {host_id: conn for host_id, conn in hosts.items() if host_id in visible_hosts}
            monitoring_states = {
                container_key: enabled
                for container_key, enabled in monitoring_states.items()
                if container_key in visible_container_keys
            }
        payload = {
            "hosts": [{"host_id": hid, "online": conn.online} for hid, conn in hosts.items()],
            "monitoring_states": monitoring_states,
        }
        await get_realtime_event_bus().emit_initial_state(payload, room=f"room:{sid}")

    @sio.on(BROWSER_STATS_SUBSCRIBE)
    async def container_stats_subscribe(sid: str, data: dict[str, Any]):
        container_key = str((data or {}).get("container_key") or "").strip()
        host_id = str((data or {}).get("host_id") or "").strip()
        if not container_key or not host_id:
            return
        if not await _require_container_event_access(
            sio,
            sid,
            container_key=container_key,
            min_role="read_only",
            permissions={"resource": ["read"]},
        ):
            return
        session_registry = get_browser_session_registry()
        await sio.enter_room(sid, room_for_container_stats(container_key))
        first_subscription = await session_registry.add_stats_subscription(sid=sid, container_key=container_key)
        if first_subscription:
            async with session_ctx() as session:
                container = await get_container_by_key(session, container_key)
            if container is not None:
                target_host_id = container.herald_id or host_id
                await get_agent_registry().send_command(
                    target_host_id,
                    "command",
                    {
                        "action": "start_stats",
                        "container_id": container.docker_container_id or container.name,
                        "container_key": container.container_key,
                    },
                )

    @sio.on(BROWSER_STATS_UNSUBSCRIBE)
    async def container_stats_unsubscribe(sid: str, data: dict[str, Any]):
        container_key = str((data or {}).get("container_key") or "").strip()
        if not container_key:
            return
        if not await _require_container_event_access(
            sio,
            sid,
            container_key=container_key,
            min_role="read_only",
            permissions={"resource": ["read"]},
        ):
            return
        session_registry = get_browser_session_registry()
        await sio.leave_room(sid, room_for_container_stats(container_key))
        is_last = await session_registry.remove_stats_subscription(sid=sid, container_key=container_key)
        if is_last:
            async with session_ctx() as session:
                container = await get_container_by_key(session, container_key)
            if container is not None:
                await get_agent_registry().send_command(
                    container.herald_id or container_key.split(":", 1)[0],
                    "command",
                    {
                        "action": "stop_stats",
                        "container_id": container.docker_container_id or container.name,
                        "container_key": container.container_key,
                    },
                )

    @sio.on(BROWSER_LOGS_START)
    async def container_logs_start(sid: str, data: dict[str, Any]):
        return await start_container_log_view(sio, sid, data)

    @sio.on(BROWSER_LOGS_STOP)
    async def container_logs_stop(sid: str, data: dict[str, Any]):
        await stop_container_log_view(sio, sid, data)

    @sio.on(BROWSER_FILES_REQUEST)
    async def container_files_request(sid: str, data: dict[str, Any]):
        container_key = str((data or {}).get("container_key") or "").strip()
        host_id = str((data or {}).get("host_id") or "").strip()
        action = str((data or {}).get("action") or "").strip()
        if not container_key or not host_id or action not in {"list", "read"}:
            return
        if not await _require_container_event_access(
            sio,
            sid,
            container_key=container_key,
            min_role="read_only",
            permissions={"resource": ["read"]},
        ):
            return
        async with session_ctx() as session:
            container = await get_container_by_key(session, container_key)
        if container is None:
            return
        target_host_id = container.herald_id or host_id
        request_id = uuid.uuid4().hex
        await sio.enter_room(sid, room_for_container_files(request_id))
        command = "files_list" if action == "list" else "file_read"
        payload = {
            "request_id": request_id,
            "container": container.name,
            "path": str((data or {}).get("path") or "/"),
        }
        await get_agent_registry().send_command(target_host_id, command, payload)
        return {"request_id": request_id}

    @sio.on(BROWSER_TERMINAL_START)
    async def container_terminal_start(sid: str, data: dict[str, Any]):
        container_key = str((data or {}).get("container_key") or "").strip()
        host_id = str((data or {}).get("host_id") or "").strip()
        if not container_key or not host_id:
            return
        if not await _require_container_event_access(
            sio,
            sid,
            container_key=container_key,
            min_role="admin",
            permissions={"resource": ["exec"]},
        ):
            return
        session_registry = get_browser_session_registry()
        async with session_ctx() as session:
            container = await get_container_by_key(session, container_key)
        if container is None:
            return
        target_host_id = container.herald_id or host_id
        session_id = uuid.uuid4().hex
        await session_registry.register_terminal_session(
            sid=sid,
            session_id=session_id,
            host_id=target_host_id,
            container_key=container_key,
        )
        await sio.enter_room(sid, room_for_container_terminal(session_id))
        await get_agent_registry().send_command(
            target_host_id,
            "exec_start",
            {
                "session_id": session_id,
                "container": container.name,
                "rows": int((data or {}).get("rows") or 24),
                "cols": int((data or {}).get("cols") or 80),
            },
        )
        return {"session_id": session_id}

    @sio.on(BROWSER_TERMINAL_INPUT)
    async def container_terminal_input(sid: str, data: dict[str, Any]):
        session_id = str((data or {}).get("session_id") or "").strip()
        payload = str((data or {}).get("data") or "")
        record = await get_browser_session_registry().get_terminal_session(session_id)
        if record is None or record.sid != sid or not payload:
            return
        if not await _require_container_event_access(
            sio,
            sid,
            container_key=record.container_key,
            min_role="admin",
            permissions={"resource": ["exec"]},
        ):
            return
        await get_browser_session_registry().refresh_sid_lease(sid)
        await get_agent_registry().send_command(
            record.host_id,
            "exec_input",
            {"session_id": session_id, "data": payload},
        )

    @sio.on(BROWSER_TERMINAL_RESIZE)
    async def container_terminal_resize(sid: str, data: dict[str, Any]):
        session_id = str((data or {}).get("session_id") or "").strip()
        record = await get_browser_session_registry().get_terminal_session(session_id)
        if record is None or record.sid != sid:
            return
        if not await _require_container_event_access(
            sio,
            sid,
            container_key=record.container_key,
            min_role="admin",
            permissions={"resource": ["exec"]},
        ):
            return
        await get_browser_session_registry().refresh_sid_lease(sid)
        await get_agent_registry().send_command(
            record.host_id,
            "exec_resize",
            {
                "session_id": session_id,
                "rows": int((data or {}).get("rows") or 24),
                "cols": int((data or {}).get("cols") or 80),
            },
        )

    @sio.on(BROWSER_TERMINAL_STOP)
    async def container_terminal_stop(sid: str, data: dict[str, Any]):
        session_id = str((data or {}).get("session_id") or "").strip()
        record = await get_browser_session_registry().get_terminal_session(session_id)
        if record is None or record.sid != sid:
            return
        if not await _require_container_event_access(
            sio,
            sid,
            container_key=record.container_key,
            min_role="admin",
            permissions={"resource": ["exec"]},
        ):
            return
        await get_browser_session_registry().remove_terminal_session(session_id)
        await sio.leave_room(sid, room_for_container_terminal(session_id))
        await get_agent_registry().send_command(record.host_id, "exec_stop", {"session_id": session_id})


__all__ = [
    "start_container_log_view",
    "stop_container_log_view",
    "cleanup_browser_sessions_for_sid",
    "register",
]
