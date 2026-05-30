from typing import Optional, Tuple

import socketio
from app.core.logging import get_logger
from app.socket.constants import REQUEST_INVENTORY_REFRESH_EVENT_NAME
from app.socket.validation import inspect_ack

from unicron_shared import InventoryTriggerAck

logger = get_logger("herald.socket.inventory")


async def request_inventory_refresh(
    sio: socketio.AsyncServer,
    herald_id: str,
    *,
    timeout: int = 10,
    room_override: Optional[str] = None,
) -> Tuple[bool, Optional[InventoryTriggerAck]]:
    """Emit an inventory_refresh call to a herald and validate the ACK.

    Returns (success, InventoryTriggerAck|None).
    """
    target_room = room_override or f"herald:{herald_id}"
    log_ctx = f"inventory:refresh:{herald_id}"

    try:
        raw_ack = await sio.call(REQUEST_INVENTORY_REFRESH_EVENT_NAME, {}, to=target_room, timeout=timeout)
    except Exception as exc:
        logger.error("%s emit failed: %s", log_ctx, exc, exc_info=True)
        return False, None

    ok, data = inspect_ack(raw_ack, ok_data_model=InventoryTriggerAck, log_context=log_ctx, _logger=logger)
    if not ok:
        return False, None

    if isinstance(data, InventoryTriggerAck):
        return True, data

    try:
        parsed = InventoryTriggerAck.model_validate(data or {})
        return True, parsed
    except Exception:
        logger.warning("%s ack payload could not be parsed into InventoryTriggerAck", log_ctx)
        return True, None


__all__ = ["REQUEST_INVENTORY_REFRESH_EVENT_NAME", "request_inventory_refresh"]
