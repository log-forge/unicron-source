"""Redis cache layer for container inventory data.

Provides fast lookups for the Container Overview UI with 10-minute TTL.
Write order: PostgreSQL first, then Redis (handles Redis failures gracefully).
"""

import json
import time
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
from sqlmodel import select

from app.core.config import settings
from app.core.database import session_ctx
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.models.container.container_model import Container

logger = get_logger("services.container_cache")

# Cache TTL configuration
CONTAINER_TTL_SECONDS = 600  # 10 minutes
HOST_STATUS_TTL_SECONDS = 600  # 10 minutes
HOST_LAST_SEEN_TTL_SECONDS = 86400 * 30  # 30 days
# Monitoring state is durable in PostgreSQL and mirrored in Redis cache.
# Cache keys are intentionally non-expiring to avoid state drift.

# Key patterns
KEY_CONTAINER = "container:{host_id}:{container_key}"  # JSON container data
KEY_HOST_CONTAINERS = "host:{host_id}:containers"  # Set of container keys
KEY_HOST_ONLINE = "host:{host_id}:online"  # Host online status ("1" or "0")
KEY_HOST_ONLINE_CHANGED_AT = "host:{host_id}:online:changed_at"  # unix timestamp
KEY_HOST_LAST_SEEN = "host:{host_id}:last_seen"  # unix timestamp of most recent heartbeat/connect
KEY_ALL_HOSTS = "agent:hosts"  # Set of all known host IDs
KEY_MONITORING = "monitoring:{container_key}"  # Monitoring enabled ("1" or "0")
KEY_MONITORING_INDEX_ALL = "monitoring:index:all"  # Set of "container_key"
KEY_MONITORING_INDEX_HOST = "monitoring:index:host:{host_id}"  # Set of "container_key"
KEY_LOG_COLLECTION = "log_collection:{host_id}:{container_key}"  # JSON runtime log-collection state
KEY_LOG_COLLECTION_INDEX_ALL = "log_collection:index:all"  # Set of "{host_id}:{container_key}"
KEY_LOG_COLLECTION_INDEX_HOST = "log_collection:index:host:{host_id}"  # Set of "container_key"


class ContainerCache:
    """Redis cache for container inventory with pipeline writes and TTL.

    Provides:
    - Bulk inventory caching with pipeline for efficiency
    - Per-host container lookups
    - Host online/offline status tracking
    - Graceful degradation on Redis connection failures
    """

    _instance: Optional["ContainerCache"] = None

    def __new__(cls) -> "ContainerCache":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

    async def _get_client(self) -> redis.Redis:
        """Get Redis client from the app-wide pool."""
        return await get_redis()

    async def _incr_metric(self, field: str, amount: int = 1) -> None:
        """Best-effort metrics counter update in Redis hash."""
        try:
            client = await self._get_client()
            await client.hincrby(settings.MONITORING_METRICS_KEY, field, int(amount))
        except Exception:
            logger.debug("Failed to update monitoring metrics counter", exc_info=True, extra={"field": field})

    async def _set_metric_value(self, field: str, value: int) -> None:
        """Best-effort metrics gauge update in Redis hash."""
        try:
            client = await self._get_client()
            await client.hset(settings.MONITORING_METRICS_KEY, field, int(value))
        except Exception:
            logger.debug("Failed to update monitoring metrics gauge", exc_info=True, extra={"field": field})

    async def cache_inventory(self, host_id: str, containers: List[Dict[str, Any]]) -> None:
        """Cache a full inventory of containers for a host using pipeline.

        Replaces any existing cached containers for this host.
        Uses Redis pipeline for atomic bulk write.

        Args:
            host_id: The agent host identifier
            containers: List of container dicts with fields matching ContainerStaticMetrics
        """
        try:
            client = await self._get_client()

            # Build key names
            host_containers_key = KEY_HOST_CONTAINERS.format(host_id=host_id)

            # Use pipeline for atomic writes
            async with client.pipeline(transaction=True) as pipe:
                # Clear existing container set for this host
                await pipe.delete(host_containers_key)

                container_keys = []
                for container_data in containers:
                    container_key = str(container_data.get("container_key", "") or "").strip()
                    if not container_key:
                        continue

                    container_keys.append(container_key)
                    cache_key = KEY_CONTAINER.format(
                        host_id=host_id, container_key=container_key
                    )

                    # Store container JSON with TTL
                    await pipe.set(
                        cache_key,
                        json.dumps(container_data, default=str),
                        ex=CONTAINER_TTL_SECONDS,
                    )

                # Rebuild container-key set for this host
                if container_keys:
                    await pipe.sadd(host_containers_key, *container_keys)
                    await pipe.expire(host_containers_key, CONTAINER_TTL_SECONDS)

                # Track this host in global hosts set
                await pipe.sadd(KEY_ALL_HOSTS, host_id)

                await pipe.execute()

            logger.debug(
                "Cached inventory",
                extra={"host_id": host_id, "container_count": len(container_keys)},
            )
        except redis.ConnectionError:
            logger.warning(
                "Redis connection error during cache_inventory - degrading gracefully",
                extra={"host_id": host_id},
            )
        except Exception:
            logger.exception(
                "Unexpected error during cache_inventory",
                extra={"host_id": host_id},
            )

    async def remove_container(self, host_id: str, container_key: str) -> None:
        """Remove a container from the cache (on destroy/die events).

        Args:
            host_id: The agent host identifier
            container_key: The canonical container key to remove
        """
        try:
            client = await self._get_client()
            cache_key = KEY_CONTAINER.format(
                host_id=host_id, container_key=container_key
            )
            host_containers_key = KEY_HOST_CONTAINERS.format(host_id=host_id)

            async with client.pipeline(transaction=True) as pipe:
                await pipe.delete(cache_key)
                await pipe.srem(host_containers_key, container_key)
                await pipe.execute()

            logger.debug(
                "Removed container from cache",
                extra={"host_id": host_id, "container_key": container_key},
            )
        except redis.ConnectionError:
            logger.warning(
                "Redis connection error during remove_container",
                extra={"host_id": host_id, "container_key": container_key},
            )
        except Exception:
            logger.exception(
                "Unexpected error during remove_container",
                extra={"host_id": host_id, "container_key": container_key},
            )

    async def cache_single_container(
        self, host_id: str, container_data: Dict[str, Any]
    ) -> None:
        """Cache or update a single container entry.

        Args:
            host_id: The agent host identifier
            container_data: Container dict with container_key field
        """
        try:
            client = await self._get_client()
            container_key = str(container_data.get("container_key", "") or "").strip()
            if not container_key:
                return

            cache_key = KEY_CONTAINER.format(
                host_id=host_id, container_key=container_key
            )
            host_containers_key = KEY_HOST_CONTAINERS.format(host_id=host_id)

            async with client.pipeline(transaction=True) as pipe:
                await pipe.set(
                    cache_key,
                    json.dumps(container_data, default=str),
                    ex=CONTAINER_TTL_SECONDS,
                )
                await pipe.sadd(host_containers_key, container_key)
                await pipe.expire(host_containers_key, CONTAINER_TTL_SECONDS)
                await pipe.sadd(KEY_ALL_HOSTS, host_id)
                await pipe.execute()

        except redis.ConnectionError:
            logger.warning(
                "Redis connection error during cache_single_container",
                extra={"host_id": host_id, "container_key": container_key},
            )
        except Exception:
            logger.exception(
                "Unexpected error during cache_single_container",
                extra={"host_id": host_id},
            )

    async def get_host_containers(self, host_id: str) -> List[Dict[str, Any]]:
        """Get all cached containers for a host.

        Args:
            host_id: The agent host identifier

        Returns:
            List of container dicts, empty list on cache miss or error.
        """
        try:
            client = await self._get_client()
            host_containers_key = KEY_HOST_CONTAINERS.format(host_id=host_id)

            container_keys = await client.smembers(host_containers_key)
            if not container_keys:
                return []

            container_key_list = [
                container_key if isinstance(container_key, str) else container_key.decode()
                for container_key in container_keys
            ]
            cache_keys = [
                KEY_CONTAINER.format(host_id=host_id, container_key=container_key)
                for container_key in container_key_list
            ]
            raw_values = await client.mget(cache_keys)

            containers: List[Dict[str, Any]] = []
            for raw in raw_values:
                if not raw:
                    continue
                try:
                    payload = raw if isinstance(raw, str) else raw.decode()
                    containers.append(json.loads(payload))
                except Exception:
                    logger.debug(
                        "Skipping malformed cached container payload",
                        exc_info=True,
                        extra={"host_id": host_id},
                    )

            return containers
        except redis.ConnectionError:
            logger.warning(
                "Redis connection error during get_host_containers",
                extra={"host_id": host_id},
            )
            return []
        except Exception:
            logger.exception(
                "Unexpected error during get_host_containers",
                extra={"host_id": host_id},
            )
            return []

    async def get_overview_snapshot(
        self, host_ids: List[str]
    ) -> tuple[
        Dict[str, Optional[bool]],
        Dict[str, Optional[int]],
        Dict[str, Optional[int]],
        Dict[str, List[Dict[str, Any]]],
        List[str],
    ]:
        """Fetch host status and container snapshots in bulk for overview UI.

        Returns:
            - host_statuses: host_id -> True/False/None
            - host_last_seen: host_id -> epoch seconds of last seen heartbeat/connect
            - host_status_changed_at: host_id -> epoch seconds when online/offline last changed
            - host_containers: host_id -> list[container dict]
            - empty_online_hosts: online hosts with no cached containers
        """
        host_statuses: Dict[str, Optional[bool]] = {}
        host_last_seen: Dict[str, Optional[int]] = {}
        host_status_changed_at: Dict[str, Optional[int]] = {}
        host_containers: Dict[str, List[Dict[str, Any]]] = {host_id: [] for host_id in host_ids}
        empty_online_hosts: List[str] = []

        if not host_ids:
            return (
                host_statuses,
                host_last_seen,
                host_status_changed_at,
                host_containers,
                empty_online_hosts,
            )

        try:
            client = await self._get_client()

            async with client.pipeline(transaction=False) as pipe:
                for host_id in host_ids:
                    await pipe.smembers(KEY_HOST_CONTAINERS.format(host_id=host_id))
                    await pipe.get(KEY_HOST_ONLINE.format(host_id=host_id))
                    await pipe.get(KEY_HOST_LAST_SEEN.format(host_id=host_id))
                    await pipe.get(KEY_HOST_ONLINE_CHANGED_AT.format(host_id=host_id))
                host_results = await pipe.execute()

            cache_keys: List[str] = []
            container_lookup: List[tuple[str, str]] = []

            def _parse_int(raw: Any) -> Optional[int]:
                if raw is None:
                    return None
                value = (
                    raw
                    if isinstance(raw, str)
                    else raw.decode()
                    if isinstance(raw, (bytes, bytearray))
                    else str(raw)
                )
                return int(value) if value.isdigit() else None

            for idx, host_id in enumerate(host_ids):
                base = idx * 4
                ids_raw = host_results[base]
                status_raw = host_results[base + 1]
                last_seen_raw = host_results[base + 2]
                changed_raw = host_results[base + 3]

                decoded_ids = [
                    cid if isinstance(cid, str) else cid.decode()
                    for cid in (ids_raw or [])
                ]

                if status_raw is None:
                    host_statuses[host_id] = None
                else:
                    status_value = (
                        status_raw if isinstance(status_raw, str) else status_raw.decode()
                    )
                    host_statuses[host_id] = status_value == "1"
                host_last_seen[host_id] = _parse_int(last_seen_raw)
                host_status_changed_at[host_id] = _parse_int(changed_raw)

                for container_id in decoded_ids:
                    cache_keys.append(KEY_CONTAINER.format(host_id=host_id, container_key=container_id))
                    container_lookup.append((host_id, container_id))

            container_payloads: List[Optional[str]] = []
            if cache_keys:
                raw_payloads = await client.mget(cache_keys)
                container_payloads = [
                    payload if isinstance(payload, str) or payload is None else payload.decode()
                    for payload in raw_payloads
                ]

            for (host_id, _container_id), payload in zip(container_lookup, container_payloads):
                if not payload:
                    continue
                try:
                    host_containers[host_id].append(json.loads(payload))
                except Exception:
                    logger.debug(
                        "Skipping malformed cached container payload in overview snapshot",
                        exc_info=True,
                        extra={"host_id": host_id},
                    )

            for host_id in host_ids:
                if host_statuses.get(host_id) and not host_containers.get(host_id):
                    empty_online_hosts.append(host_id)

            return (
                host_statuses,
                host_last_seen,
                host_status_changed_at,
                host_containers,
                empty_online_hosts,
            )
        except redis.ConnectionError:
            logger.warning("Redis connection error during get_overview_snapshot")
            return (
                host_statuses,
                host_last_seen,
                host_status_changed_at,
                host_containers,
                empty_online_hosts,
            )
        except Exception:
            logger.exception("Unexpected error during get_overview_snapshot")
            return (
                host_statuses,
                host_last_seen,
                host_status_changed_at,
                host_containers,
                empty_online_hosts,
            )

    async def get_host_status_snapshot(
        self,
        host_ids: List[str],
    ) -> tuple[
        Dict[str, Optional[bool]],
        Dict[str, Optional[int]],
        Dict[str, Optional[int]],
        Dict[str, int],
    ]:
        """Fetch host presence + container counts without loading container payloads.

        This is optimized for host/agent list views where only status metadata
        and counts are needed.
        """
        host_statuses: Dict[str, Optional[bool]] = {}
        host_last_seen: Dict[str, Optional[int]] = {}
        host_status_changed_at: Dict[str, Optional[int]] = {}
        host_container_counts: Dict[str, int] = {host_id: 0 for host_id in host_ids}

        if not host_ids:
            return (
                host_statuses,
                host_last_seen,
                host_status_changed_at,
                host_container_counts,
            )

        try:
            client = await self._get_client()

            async with client.pipeline(transaction=False) as pipe:
                for host_id in host_ids:
                    await pipe.get(KEY_HOST_ONLINE.format(host_id=host_id))
                    await pipe.get(KEY_HOST_LAST_SEEN.format(host_id=host_id))
                    await pipe.get(KEY_HOST_ONLINE_CHANGED_AT.format(host_id=host_id))
                    await pipe.scard(KEY_HOST_CONTAINERS.format(host_id=host_id))
                host_results = await pipe.execute()

            def _parse_int(raw: Any) -> Optional[int]:
                if raw is None:
                    return None
                value = (
                    raw
                    if isinstance(raw, str)
                    else raw.decode()
                    if isinstance(raw, (bytes, bytearray))
                    else str(raw)
                )
                return int(value) if value.isdigit() else None

            for idx, host_id in enumerate(host_ids):
                base = idx * 4
                status_raw = host_results[base]
                last_seen_raw = host_results[base + 1]
                changed_raw = host_results[base + 2]
                container_count_raw = host_results[base + 3]

                if status_raw is None:
                    host_statuses[host_id] = None
                else:
                    status_value = (
                        status_raw if isinstance(status_raw, str) else status_raw.decode()
                    )
                    host_statuses[host_id] = status_value == "1"

                host_last_seen[host_id] = _parse_int(last_seen_raw)
                host_status_changed_at[host_id] = _parse_int(changed_raw)

                try:
                    host_container_counts[host_id] = int(container_count_raw or 0)
                except (TypeError, ValueError):
                    host_container_counts[host_id] = 0

            return (
                host_statuses,
                host_last_seen,
                host_status_changed_at,
                host_container_counts,
            )
        except redis.ConnectionError:
            logger.warning("Redis connection error during get_host_status_snapshot")
            return (
                host_statuses,
                host_last_seen,
                host_status_changed_at,
                host_container_counts,
            )
        except Exception:
            logger.exception("Unexpected error during get_host_status_snapshot")
            return (
                host_statuses,
                host_last_seen,
                host_status_changed_at,
                host_container_counts,
            )

    async def get_all_hosts(self) -> List[str]:
        """Get list of all known host IDs.

        Returns:
            List of host ID strings, empty list on error.
        """
        try:
            client = await self._get_client()
            hosts = await client.smembers(KEY_ALL_HOSTS)
            return list(hosts) if hosts else []
        except redis.ConnectionError:
            logger.warning("Redis connection error during get_all_hosts")
            return []
        except Exception:
            logger.exception("Unexpected error during get_all_hosts")
            return []

    async def find_host_for_container_ref(self, container_ref: str) -> Optional[str]:
        """Resolve host_id for a container name/id using one bulk snapshot call.

        Matching rules:
        - exact container name match
        - exact container id match
        - container id prefix match (for short IDs)
        """
        target = (container_ref or "").strip()
        if not target:
            return None

        host_ids_raw = await self.get_all_hosts()
        host_ids = [
            host_id.decode("utf-8") if isinstance(host_id, bytes) else str(host_id)
            for host_id in host_ids_raw
        ]
        if not host_ids:
            return None

        host_statuses, _, _, host_containers, _ = await self.get_overview_snapshot(host_ids)

        # Prefer online hosts first when names collide across disconnected hosts.
        ordered_host_ids = sorted(
            host_ids,
            key=lambda host_id: 0 if host_statuses.get(host_id) is True else 1,
        )

        for host_id in ordered_host_ids:
            for container in host_containers.get(host_id, []):
                name = str(container.get("name", "") or "")
                container_id = str(container.get("container_id", "") or "")
                if name == target:
                    return host_id
                if container_id == target:
                    return host_id
                if container_id and container_id.startswith(target):
                    return host_id

        return None

    async def remove_host(self, host_id: str) -> None:
        """Remove all cached data for a host.

        This is used for explicit decommission operations where the host should
        disappear immediately from cache-backed views.
        """
        try:
            client = await self._get_client()
            host_containers_key = KEY_HOST_CONTAINERS.format(host_id=host_id)
            host_online_key = KEY_HOST_ONLINE.format(host_id=host_id)
            host_online_changed_key = KEY_HOST_ONLINE_CHANGED_AT.format(host_id=host_id)
            host_last_seen_key = KEY_HOST_LAST_SEEN.format(host_id=host_id)
            host_monitoring_index_key = KEY_MONITORING_INDEX_HOST.format(host_id=host_id)
            host_log_collection_index_key = KEY_LOG_COLLECTION_INDEX_HOST.format(host_id=host_id)

            container_keys_raw = await client.smembers(host_containers_key)
            container_keys = [
                key if isinstance(key, str) else key.decode()
                for key in (container_keys_raw or [])
            ]

            monitoring_keys_raw = await client.smembers(host_monitoring_index_key)
            monitoring_keys = [
                key if isinstance(key, str) else key.decode()
                for key in (monitoring_keys_raw or [])
            ]
            log_collection_keys_raw = await client.smembers(host_log_collection_index_key)
            log_collection_keys = [
                key if isinstance(key, str) else key.decode()
                for key in (log_collection_keys_raw or [])
            ]

            async with client.pipeline(transaction=False) as pipe:
                for container_key in container_keys:
                    await pipe.delete(KEY_CONTAINER.format(host_id=host_id, container_key=container_key))

                for container_key in monitoring_keys:
                    await pipe.delete(KEY_MONITORING.format(container_key=container_key))

                if monitoring_keys:
                    await pipe.srem(KEY_MONITORING_INDEX_ALL, *monitoring_keys)

                for container_key in log_collection_keys:
                    await pipe.delete(KEY_LOG_COLLECTION.format(host_id=host_id, container_key=container_key))

                if log_collection_keys:
                    refs = [f"{host_id}:{container_key}" for container_key in log_collection_keys]
                    await pipe.srem(KEY_LOG_COLLECTION_INDEX_ALL, *refs)

                await pipe.delete(host_containers_key)
                await pipe.delete(host_online_key)
                await pipe.delete(host_online_changed_key)
                await pipe.delete(host_last_seen_key)
                await pipe.delete(host_monitoring_index_key)
                await pipe.delete(host_log_collection_index_key)
                await pipe.srem(KEY_ALL_HOSTS, host_id)
                await pipe.execute()

            logger.info(
                "Removed host cache entries",
                extra={
                    "host_id": host_id,
                    "removed_containers": len(container_keys),
                    "removed_monitoring_keys": len(monitoring_keys),
                    "removed_log_collection_keys": len(log_collection_keys),
                },
            )
        except redis.ConnectionError:
            logger.warning(
                "Redis connection error during remove_host",
                extra={"host_id": host_id},
            )
        except Exception:
            logger.exception(
                "Unexpected error during remove_host",
                extra={"host_id": host_id},
            )

    async def set_host_online(self, host_id: str, online: bool) -> None:
        """Update host online/offline status in Redis.

        Args:
            host_id: The agent host identifier
            online: True if host is connected and healthy
        """
        try:
            client = await self._get_client()
            status_key = KEY_HOST_ONLINE.format(host_id=host_id)
            changed_at_key = KEY_HOST_ONLINE_CHANGED_AT.format(host_id=host_id)
            last_seen_key = KEY_HOST_LAST_SEEN.format(host_id=host_id)
            new_value = "1" if online else "0"
            previous = await client.get(status_key)
            previous_value = previous if isinstance(previous, str) or previous is None else previous.decode()
            now_ts = int(time.time())

            await client.set(status_key, new_value, ex=HOST_STATUS_TTL_SECONDS)
            if online:
                await client.set(last_seen_key, str(now_ts), ex=HOST_LAST_SEEN_TTL_SECONDS)

            if previous_value is None:
                await client.set(changed_at_key, str(now_ts), ex=HOST_LAST_SEEN_TTL_SECONDS)
            elif previous_value != new_value:
                last_changed_raw = await client.get(changed_at_key)
                last_changed_str = (
                    last_changed_raw
                    if isinstance(last_changed_raw, str)
                    else last_changed_raw.decode()
                    if isinstance(last_changed_raw, (bytes, bytearray))
                    else ""
                )
                last_changed = int(last_changed_str) if last_changed_str.isdigit() else 0
                await client.set(changed_at_key, str(now_ts), ex=HOST_LAST_SEEN_TTL_SECONDS)
                await self._incr_metric("host_status_transitions_total", 1)
                if last_changed and (now_ts - last_changed) <= settings.HOST_FLAP_WINDOW_SECONDS:
                    await self._incr_metric("host_flaps_total", 1)

            logger.debug(
                "Host status updated",
                extra={"host_id": host_id, "online": online},
            )
        except redis.ConnectionError:
            logger.warning(
                "Redis connection error during set_host_online",
                extra={"host_id": host_id},
            )
        except Exception:
            logger.exception(
                "Unexpected error during set_host_online",
                extra={"host_id": host_id},
            )

    async def touch_host_heartbeat(self, host_id: str) -> None:
        """Refresh host presence lease on heartbeat with minimal writes.

        Heartbeats should not trigger per-container cache TTL refreshes.
        This method only updates:
        - host online lease key
        - host last_seen timestamp
        - host membership in global host set
        - online changed timestamp only if missing
        """
        try:
            client = await self._get_client()
            status_key = KEY_HOST_ONLINE.format(host_id=host_id)
            changed_at_key = KEY_HOST_ONLINE_CHANGED_AT.format(host_id=host_id)
            last_seen_key = KEY_HOST_LAST_SEEN.format(host_id=host_id)
            host_containers_key = KEY_HOST_CONTAINERS.format(host_id=host_id)
            now_ts = int(time.time())

            async with client.pipeline(transaction=False) as pipe:
                await pipe.set(status_key, "1", ex=HOST_STATUS_TTL_SECONDS)
                await pipe.set(last_seen_key, str(now_ts), ex=HOST_LAST_SEEN_TTL_SECONDS)
                await pipe.setnx(changed_at_key, str(now_ts))
                await pipe.expire(changed_at_key, HOST_LAST_SEEN_TTL_SECONDS)
                await pipe.sadd(KEY_ALL_HOSTS, host_id)
                await pipe.scard(host_containers_key)
                results = await pipe.execute()

            try:
                container_count = int(results[-1] or 0)
            except (TypeError, ValueError, IndexError):
                container_count = 0

            if container_count == 0:
                await self.request_inventory_if_empty(host_id)
        except redis.ConnectionError:
            logger.warning(
                "Redis connection error during touch_host_heartbeat",
                extra={"host_id": host_id},
            )
        except Exception:
            logger.exception(
                "Unexpected error during touch_host_heartbeat",
                extra={"host_id": host_id},
            )

    async def get_host_status(self, host_id: str) -> Optional[bool]:
        """Get host online/offline status from Redis.

        Args:
            host_id: The agent host identifier

        Returns:
            True if online, False if offline, None if unknown.
        """
        try:
            client = await self._get_client()
            status_key = KEY_HOST_ONLINE.format(host_id=host_id)
            value = await client.get(status_key)
            if value is None:
                return None
            return value == "1"
        except redis.ConnectionError:
            logger.warning(
                "Redis connection error during get_host_status",
                extra={"host_id": host_id},
            )
            return None
        except Exception:
            logger.exception(
                "Unexpected error during get_host_status",
                extra={"host_id": host_id},
            )
            return None

    async def set_monitoring_state(self, container_key: str, enabled: bool) -> None:
        """Set the monitoring enabled/disabled state for a container.
        """
        try:
            client = await self._get_client()
            host_id = str(container_key or "").split(":", 1)[0]
            monitoring_key = KEY_MONITORING.format(container_key=container_key)
            host_index_key = KEY_MONITORING_INDEX_HOST.format(host_id=host_id)

            async with client.pipeline(transaction=False) as pipe:
                await pipe.set(monitoring_key, "1" if enabled else "0")
                await pipe.sadd(host_index_key, container_key)
                await pipe.sadd(KEY_MONITORING_INDEX_ALL, container_key)
                await pipe.execute()
            logger.debug(
                "Container monitoring state updated",
                extra={
                    "host_id": host_id,
                    "container_key": container_key,
                    "enabled": enabled,
                },
            )
        except redis.ConnectionError:
            logger.warning(
                "Redis connection error during set_monitoring_state",
                extra={"container_key": container_key},
            )
        except Exception:
            logger.exception(
                "Unexpected error during set_monitoring_state",
                extra={"container_key": container_key},
            )

    async def clear_monitoring_state(self, container_key: str) -> None:
        """Remove any cached monitoring mirror/index entries for a container."""
        container_key = str(container_key or "").strip()
        if not container_key:
            return
        try:
            client = await self._get_client()
            host_id = container_key.split(":", 1)[0]
            host_index_key = KEY_MONITORING_INDEX_HOST.format(host_id=host_id)

            async with client.pipeline(transaction=False) as pipe:
                await pipe.delete(KEY_MONITORING.format(container_key=container_key))
                await pipe.srem(host_index_key, container_key)
                await pipe.srem(KEY_MONITORING_INDEX_ALL, container_key)
                await pipe.execute()
        except redis.ConnectionError:
            logger.warning(
                "Redis connection error during clear_monitoring_state",
                extra={"container_key": container_key},
            )
        except Exception:
            logger.exception(
                "Unexpected error during clear_monitoring_state",
                extra={"container_key": container_key},
            )

    async def get_monitoring_state(self, container_key: str) -> bool:
        """Get the monitoring enabled/disabled state for a container.
        """
        try:
            client = await self._get_client()
            monitoring_key = KEY_MONITORING.format(container_key=container_key)
            value = await client.get(monitoring_key)
            if value is None:
                return False  # Default to disabled if not set
            return value == "1"
        except redis.ConnectionError:
            logger.warning(
                "Redis connection error during get_monitoring_state",
                extra={"container_key": container_key},
            )
            return False
        except Exception:
            logger.exception(
                "Unexpected error during get_monitoring_state",
                extra={"container_key": container_key},
            )
            return False

    async def get_all_monitoring_states(self) -> Dict[str, bool]:
        """Get all container monitoring states from Redis.

        Reads indexed monitoring refs and returns container_key -> enabled mapping.
        Falls back to key scan if indexes are not yet present.

        Returns:
            Dict mapping "container_key" to monitoring enabled state.
        """
        try:
            client = await self._get_client()
            states: Dict[str, bool] = {}
            refs = await client.smembers(KEY_MONITORING_INDEX_ALL)
            stale_refs: List[str] = []

            if refs:
                refs_list = [
                    ref if isinstance(ref, str) else ref.decode()
                    for ref in refs
                ]
                monitoring_keys: List[str] = []
                valid_refs: List[str] = []
                for ref in refs_list:
                    if ":" not in ref:
                        stale_refs.append(ref)
                        continue
                    host_id, container_key = ref.split(":", 1)
                    if not host_id or not container_key:
                        stale_refs.append(ref)
                        continue
                    monitoring_keys.append(KEY_MONITORING.format(container_key=ref))
                    valid_refs.append(ref)

                values: List[Optional[str]] = []
                if monitoring_keys:
                    async with client.pipeline(transaction=False) as pipe:
                        for key in monitoring_keys:
                            await pipe.get(key)
                        raw_values = await pipe.execute()
                    values = [
                        value if isinstance(value, str) or value is None else value.decode()
                        for value in raw_values
                    ]

                for ref, value in zip(valid_refs, values):
                    if value is None:
                        stale_refs.append(ref)
                        continue
                    states[ref] = value == "1"

                if stale_refs:
                    await client.srem(KEY_MONITORING_INDEX_ALL, *stale_refs)
                return states

            # Legacy fallback for index bootstrap.
            pattern = "monitoring:*"
            async for key in client.scan_iter(match=pattern):
                key_str = key if isinstance(key, str) else key.decode()
                parts = key_str.split(":", 1)
                if len(parts) != 2:
                    continue
                container_key = parts[1]
                if ":" not in container_key or container_key.startswith("index:"):
                    # Skip monitoring index keys (sets), e.g. monitoring:index:host:{id}
                    continue
                value = await client.get(key)
                if value is not None:
                    value_str = value if isinstance(value, str) else value.decode()
                    states[container_key] = value_str == "1"
            return states
        except redis.ConnectionError:
            logger.warning("Redis connection error during get_all_monitoring_states")
            return {}
        except Exception:
            logger.exception("Unexpected error during get_all_monitoring_states")
            return {}

    async def get_monitoring_states_for_host(self, host_id: str) -> Dict[str, bool]:
        """Get monitoring states for all containers on a specific host.

        Reads indexed monitoring keys for a host and returns
        container_key -> enabled mapping. Falls back to key scan if needed.

        Args:
            host_id: The agent host identifier

        Returns:
            Dict mapping "container_key" to monitoring enabled state.
        """
        try:
            client = await self._get_client()
            states: Dict[str, bool] = {}
            host_index_key = KEY_MONITORING_INDEX_HOST.format(host_id=host_id)
            container_keys = await client.smembers(host_index_key)
            stale_container_keys: List[str] = []

            if container_keys:
                key_list = [
                    k if isinstance(k, str) else k.decode()
                    for k in container_keys
                ]
                monitoring_keys = [
                    KEY_MONITORING.format(container_key=container_key)
                    for container_key in key_list
                ]

                async with client.pipeline(transaction=False) as pipe:
                    for key in monitoring_keys:
                        await pipe.get(key)
                    raw_values = await pipe.execute()

                for container_key, raw_value in zip(key_list, raw_values):
                    value = raw_value if isinstance(raw_value, str) or raw_value is None else raw_value.decode()
                    if value is None:
                        stale_container_keys.append(container_key)
                        continue
                    states[container_key] = value == "1"

                if stale_container_keys:
                    async with client.pipeline(transaction=False) as pipe:
                        await pipe.srem(host_index_key, *stale_container_keys)
                        await pipe.srem(KEY_MONITORING_INDEX_ALL, *stale_container_keys)
                        await pipe.execute()
                return states

            # Legacy fallback for index bootstrap.
            pattern = "monitoring:*"
            async for key in client.scan_iter(match=pattern):
                key_str = key if isinstance(key, str) else key.decode()
                parts = key_str.split(":", 1)
                if len(parts) != 2:
                    continue
                container_key = parts[1]
                if not container_key.startswith(f"{host_id}:"):
                    continue
                value = await client.get(key)
                if value is not None:
                    value_str = value if isinstance(value, str) else value.decode()
                    states[container_key] = value_str == "1"
            return states
        except redis.ConnectionError:
            logger.warning(
                "Redis connection error during get_monitoring_states_for_host",
                extra={"host_id": host_id},
            )
            return {}
        except Exception:
            logger.exception(
                "Unexpected error during get_monitoring_states_for_host",
                extra={"host_id": host_id},
            )
            return {}

    async def prime_monitoring_states_for_host(
        self,
        host_id: str,
        states: Dict[str, bool],
    ) -> None:
        """Write a complete host monitoring-state snapshot into Redis cache."""
        if not states:
            return

        try:
            client = await self._get_client()
            host_index_key = KEY_MONITORING_INDEX_HOST.format(host_id=host_id)
            async with client.pipeline(transaction=False) as pipe:
                for container_key, enabled in states.items():
                    monitoring_key = KEY_MONITORING.format(container_key=container_key)
                    await pipe.set(monitoring_key, "1" if enabled else "0")
                    await pipe.sadd(host_index_key, container_key)
                    await pipe.sadd(KEY_MONITORING_INDEX_ALL, container_key)
                await pipe.execute()
        except Exception:
            logger.debug(
                "Failed to prime monitoring states into cache",
                exc_info=True,
                extra={"host_id": host_id, "state_count": len(states)},
            )

    async def set_log_collection_state(
        self,
        host_id: str,
        container_key: str,
        name: str,
        image: str,
        *,
        status: str,
        issue: str | None = None,
        docker_container_id: str | None = None,
        container_name: str | None = None,
    ) -> None:
        """Write the latest log-collection state for one monitored container."""
        container_key = str(container_key or "").strip()
        name = str(name or "").strip()
        image = str(image or "").strip()
        host_id = str(host_id or "").strip()
        if not host_id or not container_key or not name or not image:
            return
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"ok", "unavailable"}:
            normalized_status = "ok"

        normalized_issue = str(issue or "").strip().lower()
        if not normalized_issue or normalized_status != "unavailable":
            normalized_issue = ""

        payload: Dict[str, Any] = {
            "host_id": host_id,
            "name": name,
            "image": image,
            "container_key": container_key,
            "log_collection_status": normalized_status,
            "log_collection_issue": normalized_issue,
            "updated_at": time.time(),
        }
        if docker_container_id:
            payload["docker_container_id"] = str(docker_container_id).strip()
        if container_name:
            payload["container_name"] = str(container_name).strip().lstrip("/")

        try:
            client = await self._get_client()
            host_index_key = KEY_LOG_COLLECTION_INDEX_HOST.format(host_id=host_id)
            async with client.pipeline(transaction=True) as pipe:
                await pipe.set(
                    KEY_LOG_COLLECTION.format(host_id=host_id, container_key=container_key),
                    json.dumps(payload, default=str),
                )
                await pipe.sadd(host_index_key, container_key)
                await pipe.sadd(KEY_LOG_COLLECTION_INDEX_ALL, f"{host_id}:{container_key}")
                await pipe.execute()
        except Exception:
            logger.debug(
                "Failed to set log-collection state in cache",
                exc_info=True,
                extra={"host_id": host_id, "container_key": container_key},
            )

    async def clear_log_collection_state(self, host_id: str, container_key: str) -> None:
        """Remove any cached log-collection state for a monitored container."""
        host_id = str(host_id or "").strip()
        container_key = str(container_key or "").strip()
        if not host_id or not container_key:
            return
        try:
            client = await self._get_client()
            host_index_key = KEY_LOG_COLLECTION_INDEX_HOST.format(host_id=host_id)
            async with client.pipeline(transaction=False) as pipe:
                await pipe.delete(KEY_LOG_COLLECTION.format(host_id=host_id, container_key=container_key))
                await pipe.srem(host_index_key, container_key)
                await pipe.srem(KEY_LOG_COLLECTION_INDEX_ALL, f"{host_id}:{container_key}")
                await pipe.execute()
        except Exception:
            logger.debug(
                "Failed to clear log-collection state from cache",
                exc_info=True,
                extra={"host_id": host_id, "container_key": container_key},
            )

    async def get_log_collection_states_for_hosts(
        self,
        host_ids: List[str],
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Get cached log-collection state snapshots for one or more hosts."""
        host_ids = [str(host_id or "").strip() for host_id in host_ids if str(host_id or "").strip()]
        if not host_ids:
            return {}

        try:
            client = await self._get_client()
            host_states: Dict[str, Dict[str, Dict[str, Any]]] = {host_id: {} for host_id in host_ids}

            async with client.pipeline(transaction=False) as pipe:
                for host_id in host_ids:
                    await pipe.smembers(KEY_LOG_COLLECTION_INDEX_HOST.format(host_id=host_id))
                raw_refs = await pipe.execute()

            for host_id, refs_raw in zip(host_ids, raw_refs):
                refs = [
                    ref if isinstance(ref, str) else ref.decode()
                    for ref in (refs_raw or [])
                ]
                if not refs:
                    continue

                state_keys = [
                    KEY_LOG_COLLECTION.format(host_id=host_id, container_key=container_key)
                    for container_key in refs
                ]
                async with client.pipeline(transaction=False) as pipe:
                    for key in state_keys:
                        await pipe.get(key)
                    raw_states = await pipe.execute()

                for container_key, raw_state in zip(refs, raw_states):
                    if not raw_state:
                        continue
                    payload = raw_state if isinstance(raw_state, str) else raw_state.decode()
                    try:
                        state = json.loads(payload)
                    except Exception:
                        logger.debug(
                            "Skipping malformed cached log-collection state",
                            exc_info=True,
                            extra={"host_id": host_id, "container_key": container_key},
                        )
                        continue
                    if isinstance(state, dict):
                        host_states[host_id][container_key] = state

            return host_states
        except redis.ConnectionError:
            logger.warning("Redis connection error during get_log_collection_states_for_hosts")
            return {}
        except Exception:
            logger.exception("Unexpected error during get_log_collection_states_for_hosts")
            return {}

    async def reconcile_monitoring_cache(self) -> Dict[str, int]:
        """Repair Redis monitoring cache/indexes from durable PostgreSQL state."""
        started = time.perf_counter()
        repaired = 0
        pruned = 0
        scanned = 0
        valid_refs: set[str] = set()

        client = await self._get_client()

        try:
            async with session_ctx() as session:
                rows = list((await session.execute(select(Container))).scalars().all())
                scanned = len(rows)

                monitoring_keys = [KEY_MONITORING.format(container_key=row.container_key) for row in rows]

                async with client.pipeline(transaction=False) as read_pipe:
                    for key in monitoring_keys:
                        await read_pipe.get(key)
                    existing_values = await read_pipe.execute()

                async with client.pipeline(transaction=False) as write_pipe:
                    for row, existing in zip(rows, existing_values):
                        if getattr(row, "status", None) == "removed":
                            continue
                        desired = "1" if bool(row.monitoring_enabled) else "0"
                        existing_str = existing if isinstance(existing, str) or existing is None else existing.decode()
                        valid_refs.add(row.container_key)
                        if existing_str != desired:
                            await write_pipe.set(KEY_MONITORING.format(container_key=row.container_key), desired)
                            repaired += 1
                        if row.herald_id:
                            await write_pipe.sadd(KEY_MONITORING_INDEX_HOST.format(host_id=row.herald_id), row.container_key)
                        await write_pipe.sadd(KEY_MONITORING_INDEX_ALL, row.container_key)
                    await write_pipe.execute()

            # Prune Redis monitoring refs/keys that no longer exist in durable state.
            all_refs_raw = await client.smembers(KEY_MONITORING_INDEX_ALL)
            all_refs = {
                ref if isinstance(ref, str) else ref.decode()
                for ref in all_refs_raw
                if ref
            }
            stale_refs = sorted(all_refs - valid_refs)
            if stale_refs:
                async with client.pipeline(transaction=False) as pipe:
                    for ref in stale_refs:
                        if ":" not in ref:
                            await pipe.srem(KEY_MONITORING_INDEX_ALL, ref)
                            continue
                        host_id, container_key = ref.split(":", 1)
                        if not host_id or not container_key:
                            await pipe.srem(KEY_MONITORING_INDEX_ALL, ref)
                            continue
                        await pipe.delete(KEY_MONITORING.format(container_key=ref))
                        await pipe.srem(KEY_MONITORING_INDEX_HOST.format(host_id=host_id), ref)
                        await pipe.srem(KEY_MONITORING_INDEX_ALL, ref)
                    await pipe.execute()
                pruned = len(stale_refs)

            duration_ms = int((time.perf_counter() - started) * 1000)
            await self._incr_metric("monitoring_reconcile_runs_total", 1)
            if repaired:
                await self._incr_metric("monitoring_repaired_entries_total", repaired)
            if pruned:
                await self._incr_metric("monitoring_pruned_entries_total", pruned)
            await self._set_metric_value("monitoring_reconcile_last_duration_ms", duration_ms)
            await self._set_metric_value("monitoring_reconcile_last_scanned", scanned)
            await self._set_metric_value("monitoring_reconcile_last_pruned", pruned)

            return {
                "scanned": scanned,
                "repaired": repaired,
                "pruned": pruned,
                "duration_ms": duration_ms,
            }
        except Exception:
            logger.exception("Monitoring cache reconciliation failed")
            return {
                "scanned": scanned,
                "repaired": repaired,
                "pruned": pruned,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            }

    async def request_inventory_if_empty(self, host_id: str) -> bool:
        """Request inventory from agent if cache is empty for this host.

        Proactively hydrates the cache when it's empty but the agent is online.
        This handles cache expiration edge cases and backend restarts.

        Args:
            host_id: The agent host identifier

        Returns:
            True if request was sent, False otherwise
        """
        try:
            client = await self._get_client()
            host_containers_key = KEY_HOST_CONTAINERS.format(host_id=host_id)

            # Check if cache is empty
            container_count = await client.scard(host_containers_key)
            if container_count > 0:
                return False  # Cache has data, no need to request

            # Cache is empty - check if agent is online and request inventory
            from app.services.agent_registry import get_agent_registry

            registry = get_agent_registry()
            if not registry.is_online(host_id):
                shared_online = await self.get_host_status(host_id)
                if shared_online is False:
                    return False  # Agent offline, can't request

            # Send request_inventory command to agent
            sent = await registry.send_command(host_id, "request_inventory")
            if sent:
                logger.info(
                    "Requested inventory from agent (cache was empty)",
                    extra={"host_id": host_id},
                )
            return sent

        except redis.ConnectionError:
            logger.warning(
                "Redis connection error during request_inventory_if_empty",
                extra={"host_id": host_id},
            )
            return False
        except Exception:
            logger.exception(
                "Unexpected error during request_inventory_if_empty",
                extra={"host_id": host_id},
            )
            return False

    async def refresh_host_ttl(self, host_id: str) -> None:
        """Refresh TTL on all cached data for a host.

        Called on agent heartbeat to keep cache alive while agent is connected.
        This prevents cache expiration while the agent is still actively heartbeating.
        If cache has already expired, proactively requests inventory to repopulate.

        Args:
            host_id: The agent host identifier
        """
        try:
            client = await self._get_client()
            host_containers_key = KEY_HOST_CONTAINERS.format(host_id=host_id)

            # Get all container IDs for this host
            container_keys = await client.smembers(host_containers_key)
            if not container_keys:
                # Cache is empty - proactively request inventory
                # This handles the case where TTL expired between heartbeats
                await self.request_inventory_if_empty(host_id)
                return  # No containers to refresh TTL on

            # Use pipeline for efficient bulk TTL refresh
            async with client.pipeline(transaction=False) as pipe:
                # Refresh TTL on host containers set
                await pipe.expire(host_containers_key, CONTAINER_TTL_SECONDS)

                # Refresh TTL on each container key
                for container_key in container_keys:
                    container_key_str = (
                        container_key
                        if isinstance(container_key, str)
                        else container_key.decode()
                    )
                    cache_key = KEY_CONTAINER.format(
                        host_id=host_id, container_key=container_key_str
                    )
                    await pipe.expire(cache_key, CONTAINER_TTL_SECONDS)

                # Refresh host online status TTL
                status_key = KEY_HOST_ONLINE.format(host_id=host_id)
                await pipe.expire(status_key, HOST_STATUS_TTL_SECONDS)

                await pipe.execute()

        except redis.ConnectionError:
            # Graceful degradation - don't fail heartbeat processing
            pass
        except Exception:
            logger.exception(
                "Unexpected error during refresh_host_ttl",
                extra={"host_id": host_id},
            )
def get_container_cache() -> ContainerCache:
    """Get the singleton ContainerCache instance."""
    return ContainerCache()
