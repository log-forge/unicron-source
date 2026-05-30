"""Cross-replica action response correlation for agent commands.

Action requests are tracked in two places:
1) local asyncio.Future map for fast same-replica completion
2) Redis pending/result slots for cross-replica completion

This keeps internal action execution resilient when command send and response
handling occur on different backend replicas.
"""

import asyncio
import json
from typing import Any, Dict, Optional

from app.core.logging import get_logger
from app.core.redis import get_redis

logger = get_logger("services.alerting.action_executor")

ACTION_RESULT_KEY_PREFIX = "actions:execute_result"
ACTION_RESULT_TTL_SECONDS = 120
ACTION_RESULT_POLL_INTERVAL_SECONDS = 0.1

# Fast-path in-process Futures (request_id -> Future). Redis remains source of
# truth for cross-replica result visibility.
_pending_actions: Dict[str, asyncio.Future] = {}


def _result_key(request_id: str) -> str:
    return f"{ACTION_RESULT_KEY_PREFIX}:{request_id}"


async def _set_result_slot(request_id: str, payload: Dict[str, Any]) -> bool:
    try:
        redis = await get_redis()
        await redis.set(
            _result_key(request_id),
            json.dumps(payload),
            ex=ACTION_RESULT_TTL_SECONDS,
        )
        return True
    except Exception:
        return False


async def _get_result_slot(request_id: str) -> Optional[Dict[str, Any]]:
    try:
        redis = await get_redis()
        raw = await redis.get(_result_key(request_id))
    except Exception:
        return None

    if not raw:
        return None

    try:
        return json.loads(raw)
    except Exception:
        return None


async def _delete_result_slot(request_id: str) -> None:
    try:
        redis = await get_redis()
        await redis.delete(_result_key(request_id))
    except Exception:
        # Cleanup is best-effort.
        return


async def register_pending_action(request_id: str) -> asyncio.Future:
    """Create local Future + Redis pending slot for an action request."""
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    _pending_actions[request_id] = future

    ok = await _set_result_slot(
        request_id,
        {"status": "pending", "request_id": request_id},
    )
    if not ok:
        logger.warning(
            "Failed to create Redis pending slot for action",
            extra={"request_id": request_id},
        )

    logger.debug("Registered pending action", extra={"request_id": request_id})
    return future


async def resolve_action_result(
    request_id: str,
    success: bool,
    message: str = "",
    error: str = "",
    **extra_fields: Any,
) -> None:
    """Resolve action result for local and cross-replica waiters."""
    result: Dict[str, Any] = {
        "status": "done",
        "request_id": request_id,
        "success": bool(success),
        "message": message,
        "error": error,
    }
    for key, value in extra_fields.items():
        if value is not None:
            result[key] = value

    future = _pending_actions.get(request_id)
    if future is not None and not future.done():
        future.set_result(result)

    persisted = await _set_result_slot(request_id, result)
    if not persisted and future is None:
        logger.warning(
            "Action result could not be persisted and no local future exists",
            extra={"request_id": request_id},
        )

    logger.info(
        "Action result resolved",
        extra={"request_id": request_id, "success": bool(success)},
    )


async def relay_script_result(
    request_id: str,
    success: bool,
    output: str,
    exit_code: int,
    error: str = "",
) -> None:
    """Store run_script result for local and cross-replica waiters."""
    await resolve_action_result(
        request_id=request_id,
        success=success,
        error=error,
        output=output,
        exit_code=exit_code,
    )


async def wait_for_action_result(
    request_id: str,
    timeout_seconds: float,
) -> Dict[str, Any]:
    """Wait until action result is available (local future or Redis slot)."""
    future = _pending_actions.get(request_id)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds

    while loop.time() < deadline:
        if future is not None and future.done():
            result = future.result()
            await _delete_result_slot(request_id)
            return result

        payload = await _get_result_slot(request_id)
        if payload and payload.get("status") == "done":
            if future is not None and not future.done():
                future.set_result(payload)
            await _delete_result_slot(request_id)
            return payload

        await asyncio.sleep(ACTION_RESULT_POLL_INTERVAL_SECONDS)

    if future is not None and future.done():
        result = future.result()
        await _delete_result_slot(request_id)
        return result

    raise asyncio.TimeoutError


async def cleanup_pending_action(request_id: str) -> None:
    """Remove in-process and Redis pending state for a request."""
    _pending_actions.pop(request_id, None)
    await _delete_result_slot(request_id)


async def get_script_result(request_id: str) -> Optional[Dict[str, Any]]:
    """Legacy getter for poll-based retrieval (Redis-backed)."""
    payload = await _get_result_slot(request_id)
    if payload and payload.get("status") == "done":
        await _delete_result_slot(request_id)
        return payload
    return None
