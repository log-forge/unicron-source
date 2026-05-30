"""Redis pub/sub relay for alert WebSocket updates.

Subscribes to the `unicron:alert-updates` Redis pub/sub channel
and relays incoming alert events to browser WebSocket clients connected at
/api/containers/ws via the ConnectionManager.

Alert events are published by alert-engine when alerts fire, change state,
or are acknowledged/resolved. This relay bridges alert-engine (which publishes
to Redis pub/sub) with browser clients (which connect via plain WebSocket).
"""

import asyncio
import json
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("services.alert_ws_relay")

ALERT_WS_CHANNEL = "unicron:alert-updates"

_relay_task: Optional[asyncio.Task] = None


async def _alert_relay_loop() -> None:
    """Subscribe to Redis pub/sub and relay alert events to browser WebSocket clients."""
    from app.routes.containers.ws_broadcast import get_connection_manager

    redis_url = settings.REDIS_URL
    if not redis_url:
        logger.warning("REDIS_URL not configured; alert WebSocket relay disabled")
        return

    manager = get_connection_manager()
    backoff = 1

    while True:
        try:
            redis = aioredis.from_url(redis_url, decode_responses=True)
            pubsub = redis.pubsub()
            await pubsub.subscribe(ALERT_WS_CHANNEL)
            logger.info("Alert WebSocket relay subscribed to %s", ALERT_WS_CHANNEL)
            backoff = 1  # Reset on successful connect

            async for raw_message in pubsub.listen():
                if raw_message["type"] != "message":
                    continue

                try:
                    data = json.loads(raw_message["data"])
                    logger.debug(
                        "Relaying alert event to browser clients: type=%s",
                        data.get("type", "unknown"),
                    )
                    await manager.broadcast(data)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON on %s channel", ALERT_WS_CHANNEL)
                except Exception:
                    logger.warning("Failed to relay alert event", exc_info=True)

        except asyncio.CancelledError:
            logger.info("Alert WebSocket relay shutting down")
            break
        except Exception:
            logger.warning(
                "Alert WebSocket relay connection lost, reconnecting in %ds",
                backoff,
                exc_info=True,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
        finally:
            try:
                await pubsub.unsubscribe(ALERT_WS_CHANNEL)
                await pubsub.close()
                await redis.close()
            except Exception:
                pass


async def start_alert_ws_relay() -> None:
    """Start the alert WebSocket relay background task."""
    global _relay_task
    if _relay_task is not None and not _relay_task.done():
        logger.debug("Alert WebSocket relay already running")
        return

    _relay_task = asyncio.create_task(_alert_relay_loop())
    logger.info("Alert WebSocket relay started")


async def stop_alert_ws_relay() -> None:
    """Stop the alert WebSocket relay background task."""
    global _relay_task
    if _relay_task is None or _relay_task.done():
        return

    _relay_task.cancel()
    try:
        await _relay_task
    except asyncio.CancelledError:
        pass
    _relay_task = None
    logger.info("Alert WebSocket relay stopped")


__all__ = ["start_alert_ws_relay", "stop_alert_ws_relay"]
