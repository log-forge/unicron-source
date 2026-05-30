from __future__ import annotations

from app.models.herald.crud.herald_crud import set_socket_presence
from app.services.container_cache import get_container_cache
from app.services.realtime_event_bus import get_realtime_event_bus
from sqlalchemy.ext.asyncio import AsyncSession


class HeraldRuntimeService:
    async def set_host_online(self, session: AsyncSession, *, host_id: str, online: bool) -> None:
        await set_socket_presence(session, host_id, online)
        await get_container_cache().set_host_online(host_id, online)
        await get_realtime_event_bus().emit_host_status(host_id=host_id, online=online)


_SERVICE = HeraldRuntimeService()


def get_herald_runtime_service() -> HeraldRuntimeService:
    return _SERVICE


__all__ = ["HeraldRuntimeService", "get_herald_runtime_service"]
