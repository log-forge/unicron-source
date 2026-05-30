from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import HTTPException

from app.core.database import session_ctx
from app.core.redis import get_redis
from app.models.container.crud.container_crud import get_container_by_key
from app.services.agent_registry import get_agent_registry
from app.services.alerting.streams import publish_container_event
from app.services.container_cache import get_container_cache
from app.services.realtime_event_bus import get_realtime_event_bus

ACK_KEY_PREFIX = "monitoring:toggle_ack"
ACK_TTL_SECONDS = 60
ACK_POLL_INTERVAL_SECONDS = 0.1


def _ack_key(request_id: str) -> str:
    return f"{ACK_KEY_PREFIX}:{request_id}"


class MonitoringPolicyService:
    async def create_ack_slot(self, request_id: str) -> None:
        redis = await get_redis()
        await redis.set(
            _ack_key(request_id),
            json.dumps({"status": "pending"}),
            ex=ACK_TTL_SECONDS,
        )

    async def resolve_ack(self, request_id: str, success: bool, error: str) -> None:
        redis = await get_redis()
        await redis.set(
            _ack_key(request_id),
            json.dumps(
                {
                    "status": "done",
                    "success": bool(success),
                    "error": error or "",
                }
            ),
            ex=ACK_TTL_SECONDS,
        )

    async def wait_for_ack(self, request_id: str, timeout_seconds: float = 10.0) -> dict:
        redis = await get_redis()
        key = _ack_key(request_id)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds

        while loop.time() < deadline:
            raw = await redis.get(key)
            if raw:
                try:
                    payload = json.loads(raw)
                except Exception:
                    payload = {"status": "pending"}
                if payload.get("status") == "done":
                    await redis.delete(key)
                    return {
                        "success": bool(payload.get("success", False)),
                        "error": str(payload.get("error", "")),
                    }
            await asyncio.sleep(ACK_POLL_INTERVAL_SECONDS)

        raise asyncio.TimeoutError

    async def toggle_monitoring(
        self,
        *,
        container_key: str,
        host_id: str,
        enabled: bool,
    ) -> tuple[str, bool]:
        cache = get_container_cache()
        registry = get_agent_registry()
        if not registry.is_online(host_id):
            shared_online = await cache.get_host_status(host_id)
            if shared_online is False:
                raise HTTPException(status_code=503, detail="Agent offline")

        async with session_ctx() as session:
            container = await get_container_by_key(session, container_key)
            if container is None:
                raise HTTPException(status_code=404, detail="Container not found")

            request_id = uuid.uuid4().hex
            await self.create_ack_slot(request_id)
            sent = await registry.send_command(
                host_id,
                "monitoring_toggle",
                {
                    "request_id": request_id,
                    "container_key": container_key,
                    "container": container.name,
                    "name": container.name,
                    "image": container.image,
                    "enabled": enabled,
                },
            )
            if not sent:
                raise HTTPException(status_code=503, detail="Agent command relay unavailable")

            try:
                result = await self.wait_for_ack(request_id, timeout_seconds=10.0)
            except asyncio.TimeoutError as exc:
                raise HTTPException(status_code=504, detail="Agent ACK timeout") from exc

            if not result["success"]:
                raise HTTPException(status_code=502, detail=f"Agent error: {result['error']}")

            container.monitoring_enabled = enabled
            session.add(container)
            event_payload = {
                "type": "monitoring_state_changed",
                "herald_id": host_id,
                "host_id": host_id,
                "container_key": container_key,
                "name": container.name,
                "container_id": container.docker_container_id or "",
                "image": container.image or "",
                "status": container.status or "",
                "enabled": enabled,
            }
            await session.commit()

        await cache.set_monitoring_state(container_key, enabled)
        await publish_container_event(event_payload)
        await get_realtime_event_bus().emit_monitoring_state_changed(
            container_key=container_key,
            host_id=host_id,
            monitoring_enabled=enabled,
        )
        return container_key, enabled


_SERVICE = MonitoringPolicyService()


def get_monitoring_policy_service() -> MonitoringPolicyService:
    return _SERVICE


__all__ = ["MonitoringPolicyService", "get_monitoring_policy_service"]
