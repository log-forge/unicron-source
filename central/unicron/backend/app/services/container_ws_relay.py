"""Redis pub/sub relay for container WebSocket updates.

Subscribes to the `unicron:container-ws-updates` Redis pub/sub channel
and relays incoming messages to browser WebSocket clients connected at
/api/containers/ws via the ConnectionManager.

This bridges alert-engine (which publishes container state changes to
Redis pub/sub) with browser clients (which connect via plain WebSocket).
"""

import asyncio
import json
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("services.container_ws_relay")

CONTAINER_WS_CHANNEL = "unicron:container-ws-updates"

_relay_task: Optional[asyncio.Task] = None


async def _relay_loop() -> None:
    """Subscribe to Redis pub/sub and relay messages to browser WebSocket clients."""
    from app.routes.containers.ws_broadcast import get_connection_manager

    redis_url = settings.REDIS_URL
    if not redis_url:
        logger.warning("REDIS_URL not configured; container WebSocket relay disabled")
        return

    manager = get_connection_manager()
    backoff = 1

    while True:
        try:
            redis = aioredis.from_url(redis_url, decode_responses=True)
            pubsub = redis.pubsub()
            await pubsub.subscribe(CONTAINER_WS_CHANNEL)
            logger.info("Container WebSocket relay subscribed to %s", CONTAINER_WS_CHANNEL)
            backoff = 1  # Reset on successful connect

            async for raw_message in pubsub.listen():
                if raw_message["type"] != "message":
                    continue

                try:
                    data = json.loads(raw_message["data"])
                    logger.debug(
                        "Relaying container event to browser clients: type=%s",
                        data.get("type", "unknown"),
                    )
                    await manager.broadcast(data)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON on %s channel", CONTAINER_WS_CHANNEL)
                except Exception:
                    logger.warning("Failed to relay container event", exc_info=True)

        except asyncio.CancelledError:
            logger.info("Container WebSocket relay shutting down")
            break
        except Exception:
            logger.warning(
                "Container WebSocket relay connection lost, reconnecting in %ds",
                backoff,
                exc_info=True,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
        finally:
            try:
                await pubsub.unsubscribe(CONTAINER_WS_CHANNEL)
                await pubsub.close()
                await redis.close()
            except Exception:
                pass


async def start_container_ws_relay() -> None:
    """Start the container WebSocket relay background task."""
    global _relay_task
    if _relay_task is not None and not _relay_task.done():
        logger.debug("Container WebSocket relay already running")
        return

    _relay_task = asyncio.create_task(_relay_loop())
    logger.info("Container WebSocket relay started")


async def stop_container_ws_relay() -> None:
    """Stop the container WebSocket relay background task."""
    global _relay_task
    if _relay_task is None or _relay_task.done():
        return

    _relay_task.cancel()
    try:
        await _relay_task
    except asyncio.CancelledError:
        pass
    _relay_task = None
    logger.info("Container WebSocket relay stopped")


__all__ = ["start_container_ws_relay", "stop_container_ws_relay"]
