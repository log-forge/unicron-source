"""Relay alert-engine pub/sub events into browser Socket.IO events.

alert-engine publishes real-time alert updates on Redis pub/sub channel
`unicron:alert-updates` as plain JSON envelopes:

    {"type": "alert:fired|alert:stacked|alert:state_changed", "data": {...}}

Central subscribes to that channel and forwards supported events through the
shared Socket.IO browser layer. This keeps alert realtime on the same transport
as the rest of browser session coordination.
"""

import asyncio
import json
from typing import Any, Optional

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger
from app.services.realtime_event_bus import get_realtime_event_bus

logger = get_logger("services.alert_event_relay")

ALERT_WS_CHANNEL = "unicron:alert-updates"
_ALLOWED_ALERT_EVENTS = {"alert:fired", "alert:stacked", "alert:state_changed"}

_relay_task: Optional[asyncio.Task] = None


async def _relay_event(payload: dict[str, Any]) -> None:
    event_type = str(payload.get("type") or "").strip()
    if event_type not in _ALLOWED_ALERT_EVENTS:
        logger.debug("Ignoring unsupported alert relay event", extra={"event_type": event_type})
        return

    data = payload.get("data")
    if not isinstance(data, dict):
        logger.warning("Ignoring malformed alert relay payload (missing dict data)")
        return

    bus = get_realtime_event_bus()
    if event_type == "alert:fired":
        await bus.emit_alert_fired(data)
    elif event_type == "alert:stacked":
        await bus.emit_alert_stacked(data)
    elif event_type == "alert:state_changed":
        await bus.emit_alert_state_changed(data)


async def _alert_event_relay_loop() -> None:
    redis_url = settings.REDIS_URL
    if not redis_url:
        logger.warning("REDIS_URL not configured; alert event relay disabled")
        return

    backoff_seconds = 1

    while True:
        redis = None
        pubsub = None
        try:
            redis = aioredis.from_url(redis_url, decode_responses=True)
            pubsub = redis.pubsub()
            await pubsub.subscribe(ALERT_WS_CHANNEL)
            logger.info("Alert event relay subscribed to %s", ALERT_WS_CHANNEL)
            backoff_seconds = 1

            while True:
                raw_message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if not raw_message:
                    await asyncio.sleep(0)
                    continue

                raw_data = raw_message.get("data")
                if isinstance(raw_data, bytes):
                    raw_data = raw_data.decode("utf-8", errors="replace")
                if not raw_data:
                    continue

                try:
                    payload = json.loads(raw_data)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON on alert relay channel")
                    continue

                if not isinstance(payload, dict):
                    logger.warning("Invalid alert relay payload shape: expected object")
                    continue

                try:
                    await _relay_event(payload)
                except Exception:
                    logger.warning("Failed to fan out alert event via Socket.IO", exc_info=True)
        except asyncio.CancelledError:
            logger.info("Alert event relay shutting down")
            break
        except Exception:
            logger.warning(
                "Alert event relay connection lost; reconnecting in %ds",
                backoff_seconds,
                exc_info=True,
            )
            await asyncio.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, 30)
        finally:
            try:
                if pubsub is not None:
                    await pubsub.unsubscribe(ALERT_WS_CHANNEL)
                    await pubsub.close()
            except Exception:
                pass
            try:
                if redis is not None:
                    await redis.close()
            except Exception:
                pass


async def start_alert_event_relay() -> None:
    """Start background relay for alert pub/sub -> Socket.IO fanout."""
    global _relay_task
    if _relay_task is not None and not _relay_task.done():
        logger.debug("Alert event relay already running")
        return

    _relay_task = asyncio.create_task(_alert_event_relay_loop())
    logger.info("Alert event relay started")


async def stop_alert_event_relay() -> None:
    """Stop background relay for alert pub/sub -> Socket.IO fanout."""
    global _relay_task
    if _relay_task is None or _relay_task.done():
        return

    _relay_task.cancel()
    try:
        await _relay_task
    except asyncio.CancelledError:
        pass
    _relay_task = None
    logger.info("Alert event relay stopped")


__all__ = ["start_alert_event_relay", "stop_alert_event_relay"]
