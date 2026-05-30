"""Inventory-related control channel events."""

import asyncio
from datetime import datetime, timezone
from typing import Any

import socketio
from app.core.logging import get_logger
from app.tasks.inventory import trigger_once

from unicron_shared import AckErr, AckOk, InventoryTriggerAck

__all__ = ["register_inventory_refresh_events"]

logger = get_logger(__name__)


def register_inventory_refresh_events(sio: socketio.AsyncClient) -> None:
    """Attach handlers that manage inventory refresh requests."""

    async def inventory_refresh(data: Any | None = None):
        logger.info("[herald] inventory:refresh signal received; scheduling inventory submit")

        try:
            asyncio.create_task(trigger_once())
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("[herald] failed to schedule inventory submit: %s", exc, exc_info=True)
            return AckErr(ok=False, error=[str(exc)]).model_dump()

        ack = InventoryTriggerAck(scheduled_at=datetime.now(timezone.utc))
        return AckOk[InventoryTriggerAck](ok=True, data=ack).model_dump()

    sio.on("inventory:refresh", handler=inventory_refresh)
