import asyncio
import json

import socketio
from app.core.access.role_resolver import ActorContext
from app.core.config import settings
from app.core.database import session_ctx
from app.core.deps.scope import enforce_container_access
from app.socket.auth import require_socket_permissions
from app.socket.constants import LOGS_TAIL_DATA, LOGS_TAIL_ERROR, LOGS_TAIL_START, LOGS_TAIL_STOP
from app.socket.listeners.schemas import LogsTailPayload, TailDataEvent, TailErrorEvent
from app.telemetry.victoria.schemas import LogRow
from app.utils.container_selector_resolver import resolve_container_selector_to_key
from app.utils.httpx_client import build_async_client
from app.utils.victoria_helpers import build_logs_filter_for_tail
from fastapi import HTTPException

VLOGS = settings.VLOGS_BASE.rstrip("/")
_active_tasks: dict[str, asyncio.Task] = {}
_active_tail_container: dict[str, str] = {}


async def cancel_tails_for_sid(sid: str) -> None:
    """Called by your global disconnect handler to stop any active tails for this SID."""
    task = _active_tasks.pop(sid, None)
    _active_tail_container.pop(sid, None)
    if task:
        task.cancel()
        # give the task a tick to cancel cleanly
        try:
            await asyncio.sleep(0)
        except Exception:
            pass


def register(sio: socketio.AsyncServer):
    """
    Registers:
        - logs:tail:start  (payload=LogsTailPayload)
        - logs:tail:stop
    Emits:
        - logs:tail:data   (TailDataEvent)
        - logs:tail:error  (TailErrorEvent)
    """

    async def _start(sid, payload):
        try:
            ctx = await require_socket_permissions(sio, sid, {"telemetry": ["tail"]})
        except HTTPException:
            await sio.emit(LOGS_TAIL_ERROR, TailErrorEvent(error="Unauthorized").model_dump(mode="json"), to=sid)
            return

        actor = ctx.get("actor")
        try:
            body = LogsTailPayload(**payload)
            async with session_ctx() as session:
                await resolve_container_selector_to_key(session, body)
                container_key = body.container_key
                if not container_key:
                    raise ValueError("Container ID not resolved")
                if actor and ctx.get("rbac_enabled"):
                    await enforce_container_access(session, ActorContext(**actor), container_key, min_role="read_only")
            expr = build_logs_filter_for_tail(body, body.filter)  # NO pipes allowed
        except Exception as e:
            await sio.emit(LOGS_TAIL_ERROR, TailErrorEvent(error=str(e)).model_dump(mode="json"), to=sid)
            return

        _active_tail_container[sid] = container_key

        form = {"query": expr}
        if body.start_offset:
            form["start_offset"] = body.start_offset
        if body.offset:
            form["offset"] = body.offset
        if body.refresh_interval:
            form["refresh_interval"] = body.refresh_interval

        headers = {}
        if body.account_id is not None:
            headers["AccountID"] = str(body.account_id)
        if body.project_id is not None:
            headers["ProjectID"] = str(body.project_id)

        async def _run():
            try:
                async with build_async_client(timeout=None) as c:
                    async with c.stream("POST", f"{VLOGS}/select/logsql/tail", data=form, headers=headers) as r:
                        async for line in r.aiter_lines():
                            if not line:
                                continue
                            try:
                                row = LogRow.model_validate(json.loads(line))
                            except Exception:
                                row = LogRow.model_validate({"msg": line})
                            await sio.emit(LOGS_TAIL_DATA, TailDataEvent(row=row).model_dump(mode="json"), to=sid)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                await sio.emit(LOGS_TAIL_ERROR, TailErrorEvent(error=str(e)).model_dump(mode="json"), to=sid)

        # Ensure at most 1 tail per SID
        old = _active_tasks.get(sid)
        if old:
            old.cancel()
        _active_tasks[sid] = asyncio.create_task(_run())

    sio.on(LOGS_TAIL_START, handler=_start)

    async def _stop(sid, _payload=None):
        try:
            ctx = await require_socket_permissions(sio, sid, {"telemetry": ["tail"]})
        except HTTPException:
            return

        actor = ctx.get("actor")
        container_key = _active_tail_container.get(sid)
        if container_key and actor and ctx.get("rbac_enabled"):
            async with session_ctx() as session:
                await enforce_container_access(session, ActorContext(**actor), container_key, min_role="read_only")

        task = _active_tasks.pop(sid, None)
        _active_tail_container.pop(sid, None)
        if task:
            task.cancel()

    sio.on(LOGS_TAIL_STOP, handler=_stop)
