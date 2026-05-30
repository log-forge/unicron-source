"""Container monitoring toggle endpoint."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.services.monitoring_policy import get_monitoring_policy_service

monitoring_router = APIRouter()


class MonitoringToggleRequest(BaseModel):
    enabled: bool


class MonitoringToggleResponse(BaseModel):
    container_key: str
    monitoring_enabled: bool


@monitoring_router.post("/{container_key}/monitoring", response_model=MonitoringToggleResponse)
async def toggle_monitoring(
    container_key: str,
    request: MonitoringToggleRequest,
    host_id: str = Query(..., description="Agent host identifier"),
) -> MonitoringToggleResponse:
    resolved_key, enabled = await get_monitoring_policy_service().toggle_monitoring(
        container_key=container_key,
        host_id=host_id,
        enabled=request.enabled,
    )
    return MonitoringToggleResponse(container_key=resolved_key, monitoring_enabled=enabled)


@monitoring_router.get("/monitoring-states")
async def get_monitoring_states(
) -> dict:
    from app.services.container_cache import get_container_cache

    states = await get_container_cache().get_all_monitoring_states()
    return {"states": states}


@monitoring_router.get("/monitoring-states/{host_id}")
async def get_host_monitoring_states(
    host_id: str,
) -> dict:
    from app.services.container_cache import get_container_cache

    states = await get_container_cache().get_monitoring_states_for_host(host_id)
    return {"states": states}
