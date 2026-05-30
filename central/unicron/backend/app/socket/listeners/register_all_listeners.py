import asyncio

import socketio
from app.core.access.role_resolver import ActorContext
from app.core.database import session_ctx
from app.core.deps import require_registered_herald, require_spiffe_pair_socket
from app.core.deps.deployment_org import resolve_deployment_organization_id
from app.core.logging import get_logger
from app.core.origin_policy import is_socket_origin_allowed
from app.models.herald.crud.herald_crud import set_socket_presence
from app.services.browser_session_registry import get_browser_session_registry
from app.socket.constants import GLOBAL_ROOM
from app.socket.listeners.central.container_runtime import (
    cleanup_browser_sessions_for_sid,
    register as register_container_runtime,
)
from app.socket.listeners.central.victoria_logs_tail import cancel_tails_for_sid
from app.socket.listeners.central.victoria_logs_tail import register as register_victoria_logs_tail
from app.socket.validation import inspect_ack
from app.utils.central_auth_client import fetch_local_admin_session_from_cookie
from app.utils.socket_io_utils import get_room_participants
from fastapi import HTTPException
from unicron_shared import AckErr, AckOk, PongData

from ..emitters.central.health import emit_herald_health_update

logger = get_logger(__name__)


def register_all_events(sio: socketio.AsyncServer):
    async def _resolve_browser_session(_auth: object | None, environ: dict[str, object]):
        cookie_header = str(environ.get("HTTP_COOKIE") or "")
        if cookie_header:
            session = await fetch_local_admin_session_from_cookie(cookie_header)
            if session and session.user:
                return session, cookie_header

        return None, cookie_header

    async def _mark_presence(herald_id: str, online: bool) -> None:
        async with session_ctx() as session:
            herald = await set_socket_presence(session, herald_id, online)

        if herald is not None:
            try:
                await emit_herald_health_update(herald, sio=sio)
            except Exception:
                logger.debug("presence: failed to emit health update for herald %s", herald_id, exc_info=True)

    async def _post_connect_ping(sid: str, herald_id: str) -> None:
        """Ping herald after connect without blocking handshake."""
        # Yield to the event loop to ensure the Socket.IO connect handshake completes.
        await asyncio.sleep(0)
        try:
            logger.info(f"connect: pinging herald {herald_id} (sid {sid}) to verify presence")
            res = await sio.call("ping", {}, to=sid, timeout=5)
            ack = inspect_ack(
                res, ok_data_model=PongData, log_context=f"herald {herald_id} control ping", _logger=logger
            )
            if ack[0]:
                await _mark_presence(herald_id, True)
        except Exception as e:
            logger.warning(f"connect: ping to herald {herald_id} failed: {e}")

    # Base Socket.IO events
    @sio.event
    async def connect(sid, environ, auth=None):
        origin = environ.get("HTTP_ORIGIN")
        if not is_socket_origin_allowed(origin, environ):
            logger.warning("socket.connect rejected for sid=%s due to disallowed origin=%s", sid, origin)
            return False

        logger.info(f"Client {sid} connected")
        await sio.enter_room(sid, f"room:{sid}")
        await get_browser_session_registry().refresh_sid_lease(sid)

        # attempt herald resolution from Traefik-forwarded client cert info (Socket.IO handshake environ)
        try:
            herald_id, herald_cn = require_spiffe_pair_socket(environ)
            logger.info(f"connect: resolved herald_id {herald_id} (cn={herald_cn}) for client {sid}")

            try:
                async with session_ctx() as session:
                    await require_registered_herald(herald_id=herald_id, session=session)
            except HTTPException:
                logger.error(f"connect: {herald_cn} {herald_id} failed registration check; disconnecting client {sid}")
                await sio.disconnect(sid)
                return

            # for verified heralds: persist identifying metadata and join herald room
            # save both herald id and common name for downstream handlers
            await sio.save_session(sid, {"herald_id": herald_id, "herald_cn": herald_cn})
            await sio.enter_room(sid, f"herald:{herald_id}")

            # Schedule the verification ping in the background so the handshake can finish quickly.
            sio.start_background_task(_post_connect_ping, sid, herald_id)
            return
        except (ValueError, HTTPException):
            # Expected SPIFFE/handshake issues: treat as non-herald and continue
            logger.debug(f"connect: failed to resolve herald identity for client {sid}")
            pass

        session, cookie_header = await _resolve_browser_session(auth, environ)
        if not session or not session.user:
            await sio.disconnect(sid)
            return

        try:
            deployment_org_id = resolve_deployment_organization_id(
                deployment_org_id="local",
            )
        except HTTPException:
            logger.error("connect: org mismatch for client %s", sid)
            await sio.disconnect(sid)
            return

        actor = ActorContext(
            user_id=session.user_id,
            team_ids=[],
            org_role="admin",
        )
        await sio.save_session(
            sid,
            {
                "actor": {"user_id": actor.user_id, "team_ids": actor.team_ids, "org_role": actor.org_role},
                "auth_cookie": cookie_header,
                "deployment_org_id": deployment_org_id,
                "rbac_enabled": False,
            },
        )
        await sio.enter_room(sid, GLOBAL_ROOM)

    @sio.event
    async def disconnect(sid):
        logger.info(f"Client {sid} disconnected")
        # stop any active Victoria tails for this SID
        try:
            await cancel_tails_for_sid(sid)
        except Exception:
            pass
        try:
            await cleanup_browser_sessions_for_sid(sio, sid)
        except Exception:
            pass
        try:
            await get_browser_session_registry().remove_sid_lease(sid)
        except Exception:
            pass

        # attempt to load herald_id from the socket session and mark offline
        try:
            sess = await sio.get_session(sid)
            herald_id = sess.get("herald_id") if isinstance(sess, dict) else None
            if herald_id:
                room = f"herald:{herald_id}"
                participants = await get_room_participants(sio, room)
                # On disconnect, sid is typically already gone from rooms; if any
                # participants remain, keep presence online.
                if len(participants) == 0:
                    await _mark_presence(herald_id, False)
                else:
                    logger.debug(
                        f"disconnect: herald {herald_id} has {len(participants)} remaining socket(s); skipping offline"
                    )
        except Exception:
            pass

    @sio.event
    async def beat(sid, data=None):
        """Client heartbeat: mark herald socket as seen now.

        Expects the socket session to contain 'herald_id'. Best-effort update.
        Returns a simple AckOk with a short message.
        """
        try:
            sess = await sio.get_session(sid)
            herald_id = sess.get("herald_id") if isinstance(sess, dict) else None
            if herald_id:
                try:
                    async with session_ctx() as session:
                        await require_registered_herald(herald_id=herald_id, session=session)
                except HTTPException:
                    logger.error(f"beat: {herald_id} failed registration check; disconnecting client {sid}")
                    await sio.disconnect(sid)
                    return AckErr[PongData](ok=False, error=[PongData(msg="not registered")]).model_dump()

                await _mark_presence(herald_id, True)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

        return AckOk[PongData](ok=True, data=PongData(msg="ok")).model_dump()

    @sio.event
    async def ping(sid, data=None):
        try:
            await get_browser_session_registry().refresh_sid_lease(sid)
        except Exception:
            logger.debug("ping: failed to refresh browser sid lease", exc_info=True, extra={"sid": sid})
        return AckOk[PongData](ok=True, data=PongData(msg="pong")).model_dump()

    # Register other event listeners
    register_victoria_logs_tail(sio)
    register_container_runtime(sio)


__all__ = ["register_all_events"]
