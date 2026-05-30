from app.core.access.herald_visibility import list_visible_herald_ids
from app.core.access.role_resolver import ActorContext
from app.core.database import get_session
from app.core.deps import get_actor_context, require_permission
from app.models.herald.crud.herald_crud import list_heralds_by_ids, summarize_heralds_by_ids
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import HeraldsListSchema, HeraldsSummarySchema

router = APIRouter(tags=["queries", "heralds"])


@router.get(
    "/list-heralds",
    response_model=HeraldsListSchema,
    dependencies=[Depends(require_permission({"herald": ["read"]}))],
)
async def get_heralds(
    session: AsyncSession = Depends(get_session),
    actor: ActorContext = Depends(get_actor_context),
):
    herald_ids = await list_visible_herald_ids(session, actor)
    if not herald_ids:
        return []
    records = await list_heralds_by_ids(session, herald_ids)
    response = []
    for h in records:
        socket_last_seen = getattr(h, "socket_last_seen", None)
        response.append(
            {
                "herald_id": h.id,
                "herald_name": h.herald_name,
                "central_url": h.central_url,
                "registered_at": h.registered_at.isoformat() if h.registered_at else None,
                "health_status": h.health_status,
                "last_ping": h.last_ping.isoformat() if h.last_ping else None,
                "health_message": h.health_message,
                "check_in_interval": getattr(h, "check_in_interval", None),
                "region": getattr(h, "region", None),
                "tags": list(getattr(h, "tags", []) or []),
                "socket_online": bool(getattr(h, "socket_online", False)),
                "socket_last_seen": socket_last_seen.isoformat() if socket_last_seen else None,
                "herald_version": getattr(h, "herald_version", None),
                "hostname": getattr(h, "hostname", None),
                "herald_os": getattr(h, "herald_os", None),
                "os_version": getattr(h, "os_version", None),
                "architecture": getattr(h, "architecture", None),
                "cpu_count": getattr(h, "cpu_count", None),
                "host_total_memory_bytes": getattr(h, "host_total_memory_bytes", None),
            }
        )

    return response


# Same dual-decorator pattern for summary to avoid 307 redirect on /summary/
@router.get(
    "/heralds-summary",
    response_model=HeraldsSummarySchema,
    dependencies=[Depends(require_permission({"herald": ["read"]}))],
)
async def get_heralds_summary(
    session: AsyncSession = Depends(get_session),
    actor: ActorContext = Depends(get_actor_context),
):
    herald_ids = await list_visible_herald_ids(session, actor)
    return await summarize_heralds_by_ids(session, herald_ids)
