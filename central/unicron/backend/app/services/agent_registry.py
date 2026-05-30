"""Agent WebSocket connection registry with heartbeat timeout detection.

Tracks connected go-streamer agents, monitors heartbeat freshness,
and marks hosts offline after 60s of silence.
Also relays agent commands across backend replicas via Redis pub/sub.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from uuid import uuid4

from fastapi import WebSocket

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis

logger = get_logger("services.agent_registry")

# Timeout configuration
HEARTBEAT_TIMEOUT_SECONDS = settings.AGENT_HEARTBEAT_TIMEOUT_SECONDS
MONITOR_INTERVAL_SECONDS = settings.AGENT_HEARTBEAT_MONITOR_INTERVAL_SECONDS


@dataclass
class AgentConnection:
    """Represents a connected go-streamer agent."""

    host_id: str
    connection_id: str
    websocket: WebSocket
    last_seen: float = field(default_factory=time.time)
    online: bool = True
    cert_fingerprint_sha256: Optional[str] = None
    cert_serial_hex: Optional[str] = None


class AgentRegistry:
    """Singleton registry managing connected go-streamer agents.

    Provides:
    - Connection registration/unregistration
    - Heartbeat tracking with timeout detection
    - Background monitor task for stale connection cleanup
    """

    _instance: Optional["AgentRegistry"] = None
    _lock: asyncio.Lock

    def __new__(cls) -> "AgentRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._lock = asyncio.Lock()
        self._connections: Dict[str, AgentConnection] = {}
        self._revoked_ids: set[str] = set()
        self._monitor_task: Optional[asyncio.Task] = None
        self._command_relay_task: Optional[asyncio.Task] = None
        self._revocation_relay_task: Optional[asyncio.Task] = None

    async def start_monitor(self) -> None:
        """Start background heartbeat monitor and cross-replica command relay."""
        if self._monitor_task is not None and not self._monitor_task.done():
            return
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self._command_relay_task = asyncio.create_task(self._command_relay_loop())
        self._revocation_relay_task = asyncio.create_task(self._revocation_relay_loop())
        logger.info("Agent registry monitor started")

    async def stop_monitor(self) -> None:
        """Stop background heartbeat monitor and command relay task."""
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        if self._command_relay_task is not None:
            self._command_relay_task.cancel()
            try:
                await self._command_relay_task
            except asyncio.CancelledError:
                pass
            self._command_relay_task = None
        if self._revocation_relay_task is not None:
            self._revocation_relay_task.cancel()
            try:
                await self._revocation_relay_task
            except asyncio.CancelledError:
                pass
            self._revocation_relay_task = None
        logger.info("Agent registry monitor stopped")

    async def register(
        self,
        host_id: str,
        websocket: WebSocket,
        *,
        cert_fingerprint_sha256: str | None = None,
        cert_serial_hex: str | None = None,
    ) -> Optional[str]:
        """Register a new agent connection.

        Returns:
            connection_id when registration succeeds, None when host is revoked.
        """
        if await self.is_revoked(host_id):
            logger.info("Rejecting registration for revoked host", extra={"host_id": host_id})
            return None

        connection_id = uuid4().hex
        to_close: Optional[WebSocket] = None
        async with self._lock:
            existing = self._connections.get(host_id)
            if existing is not None:
                logger.warning(
                    "Replacing existing connection for host",
                    extra={"host_id": host_id},
                )
                to_close = existing.websocket
            self._connections[host_id] = AgentConnection(
                host_id=host_id,
                connection_id=connection_id,
                websocket=websocket,
                last_seen=time.time(),
                online=True,
                cert_fingerprint_sha256=cert_fingerprint_sha256,
                cert_serial_hex=cert_serial_hex,
            )
        if cert_fingerprint_sha256 or cert_serial_hex:
            await self._persist_cert_metadata(
                host_id,
                cert_fingerprint_sha256=cert_fingerprint_sha256,
                cert_serial_hex=cert_serial_hex,
            )
        if to_close is not None and to_close is not websocket:
            try:
                await to_close.close(code=1008, reason="Superseded by newer connection")
            except Exception:
                logger.debug(
                    "Failed to close superseded websocket",
                    exc_info=True,
                    extra={"host_id": host_id},
                )
        logger.info("Agent registered", extra={"host_id": host_id})
        return connection_id

    async def _persist_cert_metadata(
        self,
        host_id: str,
        *,
        cert_fingerprint_sha256: str | None,
        cert_serial_hex: str | None,
    ) -> None:
        """Persist last-seen agent cert metadata for future decommission revocation."""
        if not cert_fingerprint_sha256 and not cert_serial_hex:
            return
        payload = {
            "fingerprint_sha256": (cert_fingerprint_sha256 or "").strip().lower(),
            "serial_hex": (cert_serial_hex or "").strip().lower(),
            "updated_at": int(time.time()),
        }
        try:
            redis = await get_redis()
            await redis.set(f"{settings.AGENT_CERT_METADATA_KEY_PREFIX}{host_id}", json.dumps(payload))
        except Exception:
            logger.debug(
                "Failed to persist agent cert metadata",
                exc_info=True,
                extra={"host_id": host_id},
            )

    async def get_last_cert_metadata(self, host_id: str) -> tuple[Optional[str], Optional[str]]:
        """Return last known (fingerprint_sha256, serial_hex) for a host."""
        conn = self._connections.get(host_id)
        if conn and (conn.cert_fingerprint_sha256 or conn.cert_serial_hex):
            return conn.cert_fingerprint_sha256, conn.cert_serial_hex

        try:
            redis = await get_redis()
            raw = await redis.get(f"{settings.AGENT_CERT_METADATA_KEY_PREFIX}{host_id}")
            if not raw:
                return None, None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            payload = json.loads(raw)
            return (
                (payload.get("fingerprint_sha256") or "").strip().lower() or None,
                (payload.get("serial_hex") or "").strip().lower() or None,
            )
        except Exception:
            logger.debug(
                "Failed to read agent cert metadata",
                exc_info=True,
                extra={"host_id": host_id},
            )
            return None, None

    async def is_cert_revoked(
        self,
        *,
        cert_fingerprint_sha256: str | None = None,
        cert_serial_hex: str | None = None,
    ) -> bool:
        """Check certificate-level denylist for incoming mTLS identities."""
        fingerprint = (cert_fingerprint_sha256 or "").strip().lower()
        serial_hex = (cert_serial_hex or "").strip().lower()
        if not fingerprint and not serial_hex:
            return False
        try:
            redis = await get_redis()
            if fingerprint:
                if await redis.sismember(settings.AGENT_REVOKED_CERT_FINGERPRINT_SET_KEY, fingerprint):
                    return True
            if serial_hex:
                if await redis.sismember(settings.AGENT_REVOKED_CERT_SERIAL_SET_KEY, serial_hex):
                    return True
            return False
        except Exception:
            logger.warning(
                "Failed certificate revocation lookup",
                exc_info=True,
                extra={"fingerprint": bool(fingerprint), "serial": bool(serial_hex)},
            )
            return False

    async def revoke_cert_identity(
        self,
        host_id: str,
        *,
        cert_fingerprint_sha256: str | None = None,
        cert_serial_hex: str | None = None,
        reason: str = "decommissioned",
    ) -> tuple[Optional[str], Optional[str]]:
        """Denylist the host's current/last-known certificate identity."""
        fingerprint = (cert_fingerprint_sha256 or "").strip().lower() or None
        serial_hex = (cert_serial_hex or "").strip().lower() or None
        if not fingerprint and not serial_hex:
            fingerprint, serial_hex = await self.get_last_cert_metadata(host_id)

        if not fingerprint and not serial_hex:
            return None, None

        try:
            redis = await get_redis()
            if fingerprint:
                await redis.sadd(settings.AGENT_REVOKED_CERT_FINGERPRINT_SET_KEY, fingerprint)
            if serial_hex:
                await redis.sadd(settings.AGENT_REVOKED_CERT_SERIAL_SET_KEY, serial_hex)
            logger.info(
                "Revoked agent certificate identity",
                extra={
                    "host_id": host_id,
                    "reason": reason,
                    "fingerprint": bool(fingerprint),
                    "serial": bool(serial_hex),
                },
            )
        except Exception:
            logger.warning(
                "Failed to persist certificate revocation",
                exc_info=True,
                extra={"host_id": host_id},
            )
        return fingerprint, serial_hex

    async def unregister(self, host_id: str, connection_id: str | None = None) -> None:
        """Remove an agent connection and propagate offline when truly disconnected."""
        removed = False
        async with self._lock:
            current = self._connections.get(host_id)
            if current is None:
                return
            if connection_id and current.connection_id != connection_id:
                logger.debug(
                    "Skipping unregister for stale connection",
                    extra={
                        "host_id": host_id,
                        "stale_connection_id": connection_id,
                        "active_connection_id": current.connection_id,
                    },
                )
                return
            self._connections.pop(host_id, None)
            removed = True
        if not removed:
            return
        await self._mark_host_offline_if_disconnected(host_id, log_context="ws_disconnect")
        logger.info(
            "Agent unregistered",
            extra={"host_id": host_id},
        )

    async def is_revoked(self, host_id: str) -> bool:
        """Check whether a host has been revoked (local cache + Redis set)."""
        if host_id in self._revoked_ids:
            return True
        try:
            redis = await get_redis()
            revoked = await redis.sismember(settings.AGENT_REVOKED_SET_KEY, host_id)
            if revoked:
                self._revoked_ids.add(host_id)
            return bool(revoked)
        except Exception:
            logger.warning("Failed revoked-set lookup", exc_info=True, extra={"host_id": host_id})
            return False

    async def revoke(self, host_id: str, reason: str = "revoked") -> None:
        """Persist and broadcast host revocation across replicas."""
        self._revoked_ids.add(host_id)
        payload = {
            "host_id": host_id,
            "reason": reason,
            "revoked": True,
            "ts": int(time.time()),
        }
        try:
            redis = await get_redis()
            await redis.sadd(settings.AGENT_REVOKED_SET_KEY, host_id)
            await redis.publish(settings.AGENT_REVOCATION_CHANNEL, json.dumps(payload))
        except Exception:
            logger.warning(
                "Failed to persist/publish agent revocation",
                exc_info=True,
                extra={"host_id": host_id},
            )
        await self._disconnect_local(host_id, reason=reason, mark_offline=False)

    async def unrevoke(self, host_id: str, reason: str = "re-enrolled") -> None:
        """Clear host revocation state across replicas."""
        self._revoked_ids.discard(host_id)
        payload = {
            "host_id": host_id,
            "reason": reason,
            "revoked": False,
            "ts": int(time.time()),
        }
        try:
            redis = await get_redis()
            await redis.srem(settings.AGENT_REVOKED_SET_KEY, host_id)
            await redis.publish(settings.AGENT_REVOCATION_CHANNEL, json.dumps(payload))
        except Exception:
            logger.warning(
                "Failed to clear/publish agent revocation state",
                exc_info=True,
                extra={"host_id": host_id},
            )

    async def _disconnect_local(self, host_id: str, reason: str, *, mark_offline: bool = True) -> None:
        """Close and remove a local websocket for a revoked host, if present."""
        conn: Optional[AgentConnection] = None
        async with self._lock:
            conn = self._connections.pop(host_id, None)
        if conn is not None:
            try:
                await conn.websocket.close(code=1008, reason=reason)
            except Exception:
                logger.debug(
                    "Failed to close revoked websocket",
                    exc_info=True,
                    extra={"host_id": host_id},
                )
        if mark_offline and conn is not None:
            await self._mark_host_offline(host_id, log_context="revoked_disconnect")

    async def heartbeat(self, host_id: str) -> None:
        """Update last_seen timestamp for an agent."""
        async with self._lock:
            conn = self._connections.get(host_id)
            if conn is not None:
                conn.last_seen = time.time()
                conn.online = True

    def get_connection(self, host_id: str) -> Optional[AgentConnection]:
        """Get the connection for a host (non-async, read-only)."""
        return self._connections.get(host_id)

    def list_hosts(self) -> Dict[str, AgentConnection]:
        """Return a snapshot of all registered connections."""
        return dict(self._connections)

    def is_online(self, host_id: str) -> bool:
        """Check if a host is currently online."""
        conn = self._connections.get(host_id)
        if conn is None:
            return False
        return conn.online

    async def send_command(self, host_id: str, command_type: str, data: dict = None) -> bool:
        """Send a command to a connected agent.

        Args:
            host_id: The agent host identifier
            command_type: The command type (e.g., "request_inventory")
            data: Optional command payload data

        Returns:
            True if command was sent, False if agent not connected
        """
        conn = self._connections.get(host_id)
        if conn is None or not conn.online:
            # Not connected on this replica. Relay through Redis pub/sub so the
            # owning replica (if any) can forward to its local WebSocket.
            try:
                redis = await get_redis()
                # Shared host status is maintained in Redis. If explicitly marked
                # offline, fail fast instead of accepting and timing out later.
                shared_status = await redis.get(f"host:{host_id}:online")
                if shared_status == "0":
                    logger.debug(
                        "Skipping command relay for offline host",
                        extra={"host_id": host_id, "command_type": command_type},
                    )
                    return False
                payload = json.dumps(
                    {
                        "host_id": host_id,
                        "command_type": command_type,
                        "data": data or {},
                    }
                )
                await redis.publish(settings.AGENT_COMMAND_CHANNEL, payload)
                logger.debug(
                    "Relayed command via pubsub",
                    extra={"host_id": host_id, "command_type": command_type},
                )
                return True
            except Exception:
                logger.exception(
                    "Failed to relay command via pubsub",
                    extra={"host_id": host_id, "command_type": command_type},
                )
                return False

        try:
            command = json.dumps({
                "type": command_type,
                "data": data or {},
            })
            await conn.websocket.send_text(command)
            logger.debug(
                "Sent command to agent",
                extra={"host_id": host_id, "command_type": command_type},
            )
            return True
        except Exception:
            logger.warning(
                "Failed to send command to agent",
                extra={"host_id": host_id, "command_type": command_type},
            )
            return False

    async def _monitor_loop(self) -> None:
        """Background loop checking heartbeat freshness."""
        while True:
            try:
                await asyncio.sleep(MONITOR_INTERVAL_SECONDS)
                await self._check_timeouts()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error in agent monitor loop")

    async def _command_relay_loop(self) -> None:
        """Receive relayed commands and forward to locally connected agents."""
        pubsub = None
        try:
            redis = await get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe(settings.AGENT_COMMAND_CHANNEL)

            while True:
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,
                    )
                    if not message:
                        continue

                    raw = message.get("data")
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", errors="replace")
                    if not raw:
                        continue

                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("Invalid command relay payload")
                        continue

                    host_id = str(payload.get("host_id", "") or "")
                    command_type = str(payload.get("command_type", "") or "")
                    data = payload.get("data", {}) or {}

                    if not host_id or not command_type:
                        continue

                    conn = self._connections.get(host_id)
                    if conn is None or not conn.online:
                        continue

                    command = json.dumps({"type": command_type, "data": data})
                    await conn.websocket.send_text(command)
                    logger.debug(
                        "Forwarded relayed command to local agent",
                        extra={"host_id": host_id, "command_type": command_type},
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Error in command relay loop iteration")
                    await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error in command relay loop")
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(settings.AGENT_COMMAND_CHANNEL)
                    await pubsub.close()
                except Exception:
                    logger.debug("Failed to close command relay pubsub cleanly", exc_info=True)

    async def _revocation_relay_loop(self) -> None:
        """Apply revocation broadcasts from other replicas."""
        pubsub = None
        try:
            redis = await get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe(settings.AGENT_REVOCATION_CHANNEL)

            while True:
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,
                    )
                    if not message:
                        continue

                    raw = message.get("data")
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", errors="replace")
                    if not raw:
                        continue

                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("Invalid revocation relay payload")
                        continue

                    host_id = str(payload.get("host_id", "") or "").strip()
                    reason = str(payload.get("reason", "revoked") or "revoked").strip()
                    revoked = bool(payload.get("revoked", True))
                    if not host_id:
                        continue

                    if revoked:
                        self._revoked_ids.add(host_id)
                        await self._disconnect_local(host_id, reason=reason, mark_offline=False)
                    else:
                        self._revoked_ids.discard(host_id)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Error in revocation relay loop iteration")
                    await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error in revocation relay loop")
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(settings.AGENT_REVOCATION_CHANNEL)
                    await pubsub.close()
                except Exception:
                    logger.debug("Failed to close revocation relay pubsub cleanly", exc_info=True)

    async def _check_timeouts(self) -> None:
        """Check all connections for heartbeat timeout."""
        now = time.time()
        timed_out: list[str] = []

        async with self._lock:
            for host_id, conn in self._connections.items():
                if conn.online and (now - conn.last_seen) > HEARTBEAT_TIMEOUT_SECONDS:
                    conn.online = False
                    timed_out.append(host_id)

        # Update cache and broadcast outside lock to avoid deadlocks
        for host_id in timed_out:
            logger.warning(
                "Agent heartbeat timeout - marking offline",
                extra={"host_id": host_id, "timeout_seconds": HEARTBEAT_TIMEOUT_SECONDS},
            )
            try:
                await self._mark_host_offline(host_id, log_context="heartbeat_timeout")
            except Exception:
                logger.exception(
                    "Failed to update host offline status in cache",
                    extra={"host_id": host_id},
                )

    async def _mark_host_offline_if_disconnected(self, host_id: str, log_context: str) -> None:
        """Mark host offline only if no active local connection exists."""
        async with self._lock:
            current = self._connections.get(host_id)
            if current is not None and current.online:
                logger.debug(
                    "Skipping offline mark because host has an active connection",
                    extra={"host_id": host_id, "context": log_context},
                )
                return
        await self._mark_host_offline(host_id, log_context=log_context)

    async def _mark_host_offline(self, host_id: str, log_context: str) -> None:
        """Best-effort host offline propagation across cache, UI, and DB presence."""
        from app.core.database import session_ctx
        from app.models.herald.herald_model import Herald
        from app.models.herald.crud.herald_crud import set_socket_presence
        from app.services.container_cache import get_container_cache
        from app.services.realtime_event_bus import get_realtime_event_bus

        cache = get_container_cache()
        decommissioned = await self.is_revoked(host_id)
        if not decommissioned:
            try:
                async with session_ctx() as session:
                    herald = await session.get(Herald, host_id)
                    decommissioned = bool(herald and getattr(herald, "unregistered", False))
            except Exception:
                logger.debug(
                    "Failed DB decommission lookup during offline propagation",
                    exc_info=True,
                    extra={"host_id": host_id, "context": log_context},
                )

        if decommissioned:
            async with self._lock:
                self._connections.pop(host_id, None)
            await cache.remove_host(host_id)
            await get_realtime_event_bus().emit_host_status(
                host_id=host_id,
                online=False,
                removed=True,
                reason="decommissioned",
            )
            try:
                async with session_ctx() as session:
                    await set_socket_presence(session, host_id, False)
            except Exception:
                logger.debug(
                    "Failed DB socket presence removal update",
                    exc_info=True,
                    extra={"host_id": host_id, "context": log_context},
                )
            return

        await cache.set_host_online(host_id, False)
        await get_realtime_event_bus().emit_host_status(host_id=host_id, online=False)
        try:
            async with session_ctx() as session:
                await set_socket_presence(session, host_id, False)
        except Exception:
            logger.debug(
                "Failed DB socket presence offline update",
                exc_info=True,
                extra={"host_id": host_id, "context": log_context},
            )


def get_agent_registry() -> AgentRegistry:
    """Get the singleton AgentRegistry instance."""
    return AgentRegistry()
