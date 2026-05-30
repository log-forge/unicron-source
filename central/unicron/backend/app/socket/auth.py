# central/unicron/backend/app/socket/auth.py
import logging
from typing import Mapping, Optional, Sequence, TypedDict

from app.core.deps.deployment_org import resolve_deployment_organization_id
from app.utils.central_auth_client import fetch_local_admin_session_from_cookie
from fastapi import HTTPException

log = logging.getLogger(__name__)


class SocketAuthContext(TypedDict, total=False):
    deployment_org_id: Optional[str]
    actor: Optional[dict]
    cookie: Optional[str]
    rbac_enabled: bool
    admin_session: Optional[object]


async def get_socket_context(sio, sid) -> SocketAuthContext:
    sess = await sio.get_session(sid)
    return {
        "deployment_org_id": sess.get("deployment_org_id") if isinstance(sess, dict) else None,
        "actor": sess.get("actor") if isinstance(sess, dict) else None,
        "cookie": sess.get("auth_cookie") if isinstance(sess, dict) else None,
        "rbac_enabled": bool(sess.get("rbac_enabled")) if isinstance(sess, dict) else False,
    }


async def require_socket_auth(
    sio,
    sid,
    *,
    organization_required: bool = True,
) -> SocketAuthContext:
    ctx = await get_socket_context(sio, sid)
    cookie = ctx.get("cookie")
    if not cookie:
        log.debug("socket auth missing cookie", extra={"sid": sid})
        raise HTTPException(status_code=401, detail="Unauthorized")

    session = await fetch_local_admin_session_from_cookie(cookie or "")
    if not session or not getattr(session, "user", None):
        log.debug("socket auth invalid session", extra={"sid": sid})
        raise HTTPException(status_code=401, detail="Unauthorized")

    ctx["admin_session"] = session

    if organization_required:
        deployment_org_id = ctx.get("deployment_org_id")
        try:
            ctx["deployment_org_id"] = resolve_deployment_organization_id(
                deployment_org_id=deployment_org_id,
            )
        except HTTPException:
            log.debug("socket auth org mismatch", extra={"sid": sid})
            raise

    return ctx


async def require_socket_permissions(
    sio,
    sid,
    _permissions: Mapping[str, Sequence[str]] | Sequence[str],
    *,
    organization_required: bool = True,
) -> SocketAuthContext:
    return await require_socket_auth(sio, sid, organization_required=organization_required)
