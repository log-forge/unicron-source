import asyncio
import json
from typing import Optional

from app.core.config import settings
from app.core.database import session_ctx
from app.core.logging import get_logger
from app.core.origin_policy import refresh_origin_policy
from app.core.redis import get_redis

logger = get_logger("services.origin_policy_invalidation")

_listener_task: Optional[asyncio.Task] = None


async def publish_origin_policy_invalidation(reason: str = "updated") -> None:
    payload = json.dumps({"type": "origin_policy.invalidate", "reason": reason})
    try:
        redis = await get_redis()
        await redis.publish(settings.ORIGIN_POLICY_INVALIDATION_CHANNEL, payload)
    except Exception:
        logger.warning("Failed to publish origin policy invalidation", exc_info=True)


async def _refresh_from_invalidation() -> None:
    async with session_ctx() as session:
        await refresh_origin_policy(session)


async def _origin_policy_invalidation_loop() -> None:
    backoff_seconds = 1

    while True:
        pubsub = None
        try:
            redis = await get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe(settings.ORIGIN_POLICY_INVALIDATION_CHANNEL)
            logger.info("Origin policy invalidation subscribed to %s", settings.ORIGIN_POLICY_INVALIDATION_CHANNEL)
            backoff_seconds = 1

            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not message:
                    await asyncio.sleep(0)
                    continue

                raw = message.get("data")
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                if not raw:
                    continue

                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Invalid origin policy invalidation payload")
                    continue

                if not isinstance(payload, dict) or payload.get("type") != "origin_policy.invalidate":
                    logger.debug("Ignoring unsupported origin policy invalidation payload")
                    continue

                try:
                    await _refresh_from_invalidation()
                except Exception:
                    logger.warning("Failed to refresh origin policy after invalidation", exc_info=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "Origin policy invalidation listener failed; reconnecting in %ds",
                backoff_seconds,
                exc_info=True,
            )
            await asyncio.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, 30)
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(settings.ORIGIN_POLICY_INVALIDATION_CHANNEL)
                    await pubsub.close()
                except Exception:
                    logger.debug("Failed to close origin policy invalidation pubsub cleanly", exc_info=True)


async def start_origin_policy_invalidation_listener() -> None:
    global _listener_task
    if _listener_task is not None and not _listener_task.done():
        logger.debug("Origin policy invalidation listener already running")
        return
    _listener_task = asyncio.create_task(_origin_policy_invalidation_loop())
    logger.info("Origin policy invalidation listener started")


async def stop_origin_policy_invalidation_listener() -> None:
    global _listener_task
    if _listener_task is None or _listener_task.done():
        return

    _listener_task.cancel()
    try:
        await _listener_task
    except asyncio.CancelledError:
        pass
    _listener_task = None
    logger.info("Origin policy invalidation listener stopped")


__all__ = [
    "publish_origin_policy_invalidation",
    "start_origin_policy_invalidation_listener",
    "stop_origin_policy_invalidation_listener",
]
