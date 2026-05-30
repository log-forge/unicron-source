"""Redis-based container registry for monitored containers.

Stores only containers with monitoring enabled, keyed by ``{host_id}:{name}``.
Updated via Redis Stream consumption from Central.

Registry layout:
- Container data hash: ``alert-engine:containers:{host_id}:{name}``
- Global index set: ``alert-engine:containers:index:all`` (values ``{host}:{name}``)
- Per-host index set: ``alert-engine:containers:index:host:{host_id}``
- Host index set: ``alert-engine:containers:index:hosts`` (values ``{host_id}``)
"""

from typing import List, Optional, Set, Tuple

import redis.asyncio as redis

from app.core.logging import get_logger
from app.core.redis import get_redis

logger = get_logger("alert-engine.services.container_registry")

# Registry configuration
REGISTRY_PREFIX = "alert-engine:containers"
REGISTRY_INDEX_ALL = f"{REGISTRY_PREFIX}:index:all"
REGISTRY_INDEX_HOSTS = f"{REGISTRY_PREFIX}:index:hosts"
REGISTRY_INDEX_HOST_PREFIX = f"{REGISTRY_PREFIX}:index:host"
REGISTRY_TTL_SECONDS = 86400  # 24-hour TTL (matches MONITORING_TTL_SECONDS in Central)


def _container_data_key(host_id: str, name: str) -> str:
    return f"{REGISTRY_PREFIX}:{host_id}:{name}"


def _container_ref(host_id: str, name: str) -> str:
    return f"{host_id}:{name}"


def _host_index_key(host_id: str) -> str:
    return f"{REGISTRY_INDEX_HOST_PREFIX}:{host_id}"


def _decode(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def _parse_container_ref(ref: object) -> Optional[Tuple[str, str]]:
    ref_str = _decode(ref)
    if ":" not in ref_str:
        return None
    host_id, name = ref_str.split(":", 1)
    if not host_id or not name:
        return None
    return host_id, name


def _parse_container_key(key: object) -> Optional[Tuple[str, str]]:
    key_str = _decode(key)
    prefix = f"{REGISTRY_PREFIX}:"
    if not key_str.startswith(prefix):
        return None
    remainder = key_str[len(prefix) :]
    if ":" not in remainder:
        return None
    host_id, name = remainder.split(":", 1)
    if host_id == "index" or not host_id or not name:
        return None
    return host_id, name


def _parse_monitoring_key(key: object) -> Optional[Tuple[str, str]]:
    """Parse canonical Central monitoring keys: monitoring:{host_id}:{container_name}."""
    key_str = _decode(key)
    prefix = "monitoring:"
    if not key_str.startswith(prefix):
        return None
    remainder = key_str[len(prefix) :]
    if remainder.startswith("index:") or ":" not in remainder:
        return None
    host_id, name = remainder.split(":", 1)
    if not host_id or not name:
        return None
    return host_id, name


class ContainerRegistry:
    """Redis Hash-based container registry for monitored containers.

    Stores container metadata for all monitored containers across all hosts.
    Each container is keyed by {host_id}:{name} and stored as a Redis Hash.

    TTL is refreshed on every update to prevent stale entries from lingering
    after monitoring is disabled or container is removed.
    """

    async def _ensure_indexes(self, client: redis.Redis) -> None:
        """Backfill index sets from legacy keys when indexes are empty."""
        try:
            index_size = await client.scard(REGISTRY_INDEX_ALL)
            if index_size > 0:
                return

            discovered: Set[Tuple[str, str]] = set()
            async for key in client.scan_iter(match=f"{REGISTRY_PREFIX}:*:*"):
                parsed = _parse_container_key(key)
                if parsed is None:
                    continue
                discovered.add(parsed)

            if not discovered:
                return

            async with client.pipeline(transaction=False) as pipe:
                for host_id, name in discovered:
                    ref = _container_ref(host_id, name)
                    await pipe.sadd(REGISTRY_INDEX_ALL, ref)
                    await pipe.sadd(_host_index_key(host_id), ref)
                    await pipe.sadd(REGISTRY_INDEX_HOSTS, host_id)
                await pipe.execute()

            logger.info(
                "Backfilled container registry indexes",
                extra={"indexed_containers": len(discovered)},
            )
        except Exception:
            logger.exception("Failed to backfill container registry indexes")

    async def _prune_stale_refs(self, client: redis.Redis, refs: List[str]) -> None:
        """Remove stale index references whose data keys no longer exist."""
        if not refs:
            return
        try:
            async with client.pipeline(transaction=False) as pipe:
                for ref in refs:
                    parsed = _parse_container_ref(ref)
                    if parsed is None:
                        continue
                    host_id, _name = parsed
                    await pipe.srem(REGISTRY_INDEX_ALL, ref)
                    await pipe.srem(_host_index_key(host_id), ref)
                await pipe.execute()
        except Exception:
            logger.exception("Failed pruning stale container registry references")

    async def add_container(
        self,
        host_id: str,
        name: str,
        container_id: str,
        image: str,
        status: str,
    ) -> None:
        """Add or update a monitored container in the registry.

        Args:
            host_id: The agent host identifier
            name: Container name
            container_id: Docker container ID
            image: Container image
            status: Container status (running, stopped, etc.)
        """
        try:
            client = await get_redis()
            data_key = _container_data_key(host_id, name)
            ref = _container_ref(host_id, name)

            # Use ISO UTC timestamp for last_seen
            from datetime import datetime, timezone
            last_seen = datetime.now(timezone.utc).isoformat()

            async with client.pipeline(transaction=False) as pipe:
                # Store container data as Redis Hash
                await pipe.hset(
                    data_key,
                    mapping={
                        "container_id": container_id,
                        "name": name,
                        "host_id": host_id,
                        "image": image,
                        "status": status,
                        "last_seen": last_seen,
                    },
                )
                # Set TTL to expire after 24 hours without updates
                await pipe.expire(data_key, REGISTRY_TTL_SECONDS)

                # Maintain index sets for O(1) list/count without global SCAN.
                await pipe.sadd(REGISTRY_INDEX_ALL, ref)
                await pipe.sadd(_host_index_key(host_id), ref)
                await pipe.sadd(REGISTRY_INDEX_HOSTS, host_id)
                await pipe.execute()

            logger.debug(
                "Container added to registry",
                extra={
                    "host_id": host_id,
                    "name": name,
                    "container_id": container_id[:12],
                },
            )
        except redis.ConnectionError:
            logger.warning(
                "Redis connection error during add_container - degrading gracefully",
                extra={"host_id": host_id, "name": name},
            )
        except Exception:
            logger.exception(
                "Unexpected error during add_container",
                extra={"host_id": host_id, "name": name},
            )

    async def remove_container(self, host_id: str, name: str) -> None:
        """Remove a container from the registry (monitoring disabled).

        Args:
            host_id: The agent host identifier
            name: Container name
        """
        try:
            client = await get_redis()
            data_key = _container_data_key(host_id, name)
            ref = _container_ref(host_id, name)

            async with client.pipeline(transaction=False) as pipe:
                await pipe.delete(data_key)
                await pipe.srem(REGISTRY_INDEX_ALL, ref)
                await pipe.srem(_host_index_key(host_id), ref)
                await pipe.execute()

            # Keep the hosts index clean when the host has no registry entries.
            host_remaining = await client.scard(_host_index_key(host_id))
            if host_remaining == 0:
                await client.srem(REGISTRY_INDEX_HOSTS, host_id)

            logger.debug(
                "Container removed from registry",
                extra={"host_id": host_id, "name": name},
            )
        except redis.ConnectionError:
            logger.warning(
                "Redis connection error during remove_container",
                extra={"host_id": host_id, "name": name},
            )
        except Exception:
            logger.exception(
                "Unexpected error during remove_container",
                extra={"host_id": host_id, "name": name},
            )

    async def get_container(self, host_id: str, name: str) -> Optional[dict]:
        """Get a specific container from the registry.

        Args:
            host_id: The agent host identifier
            name: Container name

        Returns:
            Container data dict if found, None otherwise
        """
        try:
            client = await get_redis()
            key = _container_data_key(host_id, name)
            data = await client.hgetall(key)

            if data:
                return dict(data)
            return None
        except redis.ConnectionError:
            logger.warning(
                "Redis connection error during get_container",
                extra={"host_id": host_id, "name": name},
            )
            return None
        except Exception:
            logger.exception(
                "Unexpected error during get_container",
                extra={"host_id": host_id, "name": name},
            )
            return None

    async def list_containers(
        self,
        host_id: Optional[str] = None,
        *,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> List[dict]:
        """List all monitored containers, optionally filtered by host.

        Args:
            host_id: Optional host filter. If provided, only return containers from this host.
            offset: Result offset (for paging).
            limit: Max results to return. ``None`` returns all.

        Returns:
            List of container data dicts
        """
        try:
            client = await get_redis()
            await self._ensure_indexes(client)

            offset = max(0, int(offset))
            if limit is not None:
                limit = max(0, int(limit))

            index_key = _host_index_key(host_id) if host_id else REGISTRY_INDEX_ALL
            refs_raw = await client.smembers(index_key)
            if not refs_raw:
                return []

            refs = sorted(_decode(ref) for ref in refs_raw)
            if offset:
                refs = refs[offset:]
            if limit is not None:
                refs = refs[:limit]

            if not refs:
                return []

            data_keys: List[str] = []
            valid_refs: List[str] = []
            for ref in refs:
                parsed = _parse_container_ref(ref)
                if parsed is None:
                    continue
                ref_host, ref_name = parsed
                data_keys.append(_container_data_key(ref_host, ref_name))
                valid_refs.append(ref)

            if not data_keys:
                return []

            async with client.pipeline(transaction=False) as pipe:
                for key in data_keys:
                    await pipe.hgetall(key)
                rows = await pipe.execute()

            containers: List[dict] = []
            stale_refs: List[str] = []
            for ref, row in zip(valid_refs, rows):
                if row:
                    containers.append(dict(row))
                else:
                    stale_refs.append(ref)

            if stale_refs:
                await self._prune_stale_refs(client, stale_refs)
            return containers
        except redis.ConnectionError:
            logger.warning(
                "Redis connection error during list_containers",
                extra={"host_id": host_id},
            )
            return []
        except Exception:
            logger.exception(
                "Unexpected error during list_containers",
                extra={"host_id": host_id},
            )
            return []

    async def clear_all(self) -> int:
        """Clear all containers from the registry.

        Used during bootstrap to reset registry before repopulating from
        Central's monitoring state.

        Returns:
            Number of containers deleted
        """
        try:
            client = await get_redis()
            await self._ensure_indexes(client)

            refs_raw = await client.smembers(REGISTRY_INDEX_ALL)
            hosts_raw = await client.smembers(REGISTRY_INDEX_HOSTS)

            refs = [_decode(ref) for ref in refs_raw]
            hosts = [_decode(host) for host in hosts_raw]

            data_keys: List[str] = []
            for ref in refs:
                parsed = _parse_container_ref(ref)
                if parsed is None:
                    continue
                host_id, name = parsed
                data_keys.append(_container_data_key(host_id, name))

            deleted = 0
            async with client.pipeline(transaction=False) as pipe:
                if data_keys:
                    await pipe.delete(*data_keys)
                for host_id in hosts:
                    await pipe.delete(_host_index_key(host_id))
                await pipe.delete(REGISTRY_INDEX_ALL)
                await pipe.delete(REGISTRY_INDEX_HOSTS)
                results = await pipe.execute()

            if data_keys and results:
                deleted = int(results[0] or 0)

            if deleted == 0:
                # Legacy safety net: remove non-indexed keys.
                legacy_keys = []
                async for key in client.scan_iter(match=f"{REGISTRY_PREFIX}:*:*"):
                    parsed = _parse_container_key(key)
                    if parsed is not None:
                        legacy_keys.append(key)
                if legacy_keys:
                    deleted = int(await client.delete(*legacy_keys))

            logger.info(
                "Registry cleared",
                extra={"deleted_count": deleted},
            )
            return deleted
        except redis.ConnectionError:
            logger.warning("Redis connection error during clear_all")
            return 0
        except Exception:
            logger.exception("Unexpected error during clear_all")
            return 0

    async def bootstrap_from_monitoring_keys(self, clear_existing: bool = True) -> int:
        """Populate the registry from shared monitoring state keys.

        Monitoring keys are stored in Redis by Central using:
        ``monitoring:{host_id}:{container_name}`` -> ``"1"`` when enabled.

        This backfills the alert-engine registry when the service starts before
        monitoring keys exist, or when the registry is unexpectedly empty while
        monitoring is still enabled.

        Args:
            clear_existing: Whether to clear the current registry before
                repopulating it.

        Returns:
            Number of monitored containers added to the registry.
        """
        try:
            if clear_existing:
                await self.clear_all()

            client = await get_redis()
            count = 0

            async for key in client.scan_iter(match="monitoring:*"):
                parsed = _parse_monitoring_key(key)
                if parsed is None:
                    continue
                host_id, name = parsed

                value = await client.get(key)
                if value is None:
                    continue

                value_str = value if isinstance(value, str) else value.decode()
                if value_str != "1":
                    continue

                await self.add_container(
                    host_id=host_id,
                    name=name,
                    container_id="",
                    image="",
                    status="running",
                )
                count += 1

            if count:
                logger.info(
                    "Registry bootstrapped from monitoring keys",
                    extra={"container_count": count, "clear_existing": clear_existing},
                )
            else:
                logger.info(
                    "No enabled monitoring keys found during registry bootstrap",
                    extra={"clear_existing": clear_existing},
                )

            return count
        except redis.ConnectionError:
            logger.warning("Redis connection error during bootstrap_from_monitoring_keys")
            return 0
        except Exception:
            logger.exception("Unexpected error during bootstrap_from_monitoring_keys")
            return 0

    async def count(self) -> int:
        """Count total monitored containers in registry.

        Returns:
            Number of containers in registry
        """
        try:
            client = await get_redis()
            await self._ensure_indexes(client)
            return int(await client.scard(REGISTRY_INDEX_ALL))
        except redis.ConnectionError:
            logger.warning("Redis connection error during count")
            return 0
        except Exception:
            logger.exception("Unexpected error during count")
            return 0

    async def list_container_refs(self, host_id: Optional[str] = None) -> Set[Tuple[str, str]]:
        """List monitored ``(host_id, container_name)`` pairs from index sets."""
        try:
            client = await get_redis()
            await self._ensure_indexes(client)
            index_key = _host_index_key(host_id) if host_id else REGISTRY_INDEX_ALL
            refs_raw = await client.smembers(index_key)
            refs: Set[Tuple[str, str]] = set()
            for ref in refs_raw:
                parsed = _parse_container_ref(ref)
                if parsed is not None:
                    refs.add(parsed)
            return refs
        except redis.ConnectionError:
            logger.warning("Redis connection error during list_container_refs")
            return set()
        except Exception:
            logger.exception("Unexpected error during list_container_refs")
            return set()


# Module-level singleton
_registry: Optional[ContainerRegistry] = None


def get_container_registry() -> ContainerRegistry:
    """Get the singleton ContainerRegistry instance.

    Returns:
        Global ContainerRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = ContainerRegistry()
    return _registry


__all__ = ["ContainerRegistry", "get_container_registry"]
