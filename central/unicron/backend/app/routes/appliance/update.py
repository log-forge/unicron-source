from typing import Any

import httpx
from fastapi import APIRouter
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/appliance/update", tags=["appliance-update"])


class ApplianceUpdateSettings(BaseModel):
    auto_update_enabled: bool


def _degraded_payload(message: str) -> dict[str, Any]:
    return {
        "status": "degraded",
        "updater_health": "unavailable",
        "auto_update_enabled": True,
        "in_progress": False,
        "update_available": False,
        "rollback_available": False,
        "last_error": message,
    }


async def _proxy_updater(method: str, path: str, json_body: dict[str, Any] | None = None) -> ORJSONResponse:
    base_url = settings.APPLIANCE_UPDATER_URL.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=2.0)) as client:
            response = await client.request(method, f"{base_url}{path}", json=json_body)
    except httpx.RequestError as exc:
        return ORJSONResponse(_degraded_payload(f"Appliance updater is unavailable: {exc}"))

    try:
        payload = response.json()
    except ValueError:
        payload = _degraded_payload(f"Appliance updater returned non-JSON status {response.status_code}")
        return ORJSONResponse(payload)

    return ORJSONResponse(payload, status_code=response.status_code)


@router.get("/status")
async def get_update_status() -> ORJSONResponse:
    return await _proxy_updater("GET", "/status")


@router.post("/check")
async def check_for_update() -> ORJSONResponse:
    return await _proxy_updater("POST", "/check", {})


@router.post("/apply")
async def apply_update() -> ORJSONResponse:
    return await _proxy_updater("POST", "/apply", {})


@router.post("/rollback")
async def rollback_update() -> ORJSONResponse:
    return await _proxy_updater("POST", "/rollback", {})


@router.put("/settings")
async def update_settings(body: ApplianceUpdateSettings) -> ORJSONResponse:
    return await _proxy_updater("PUT", "/settings", body.model_dump())
