"""Redis cache synchronisation for container group membership.

Populates and maintains the ``alert-engine:group-containers:{group_id}``
Redis SETs that ``RuleMatcher`` and ``RuleEvaluator`` read to expand
group-scoped rules to concrete canonical container keys.

Cache contract:
    Key   : ``alert-engine:group-containers:{group_id}``
    Type  : Redis SET
    Values: canonical container keys ``{host_id}:{container_name}``
    TTL   : 24 hours (refreshed on every sync)

Call sites:
    - Group CRUD routes (create / update / delete)
    - Monitoring state changes (container_stream_consumer)
    - Service bootstrap (main.py lifespan)
"""

from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.redis import get_redis
from app.services.container_service import ContainerService

logger = get_logger("alert-engine.services.group_cache")

CACHE_PREFIX = "alert-engine:group-containers"
CACHE_TTL_SECONDS = 86400  # 24 hours


async def sync_group_cache(group_id: str, session: AsyncSession) -> int:
    """Sync the Redis SET for *group_id* with current DB membership.

    Replaces the full set each time (delete + sadd) so that removals
    are correctly reflected.

    Args:
        group_id: The group UUID to sync.
        session: Active database session.

    Returns:
        Number of members written to cache.
    """
    service = ContainerService(session)
    members = await service.get_containers_by_group(group_id)

    redis = await get_redis()
    cache_key = f"{CACHE_PREFIX}:{group_id}"

    # Always delete first – handles the 0-member / dissolved case
    await redis.delete(cache_key)

    if not members:
        logger.debug("Group %s has no members – cache cleared", group_id)
        return 0

    container_keys = [m.container_key for m in members if m.container_key]
    if not container_keys:
        logger.debug("Group %s has no canonical container keys - cache cleared", group_id)
        return 0

    await redis.sadd(cache_key, *container_keys)
    await redis.expire(cache_key, CACHE_TTL_SECONDS)

    logger.debug(
        "Synced group cache %s: %d members", group_id, len(container_keys)
    )
    return len(container_keys)


async def delete_group_cache(group_id: str) -> None:
    """Remove the Redis SET for a deleted/dissolved group."""
    redis = await get_redis()
    cache_key = f"{CACHE_PREFIX}:{group_id}"
    await redis.delete(cache_key)
    logger.debug("Deleted group cache %s", group_id)


async def sync_all_group_caches(session: AsyncSession) -> int:
    """Bootstrap: sync caches for every group in the database.

    Called during service startup after the container registry is
    populated so that group-scoped rules work immediately.

    Returns:
        Total number of groups synced.
    """
    service = ContainerService(session)
    groups = await service.list_groups()

    count = 0
    for g in groups:
        try:
            await sync_group_cache(g.id, session)
            count += 1
        except Exception as e:
            logger.warning("Failed to sync cache for group %s: %s", g.id, e)

    logger.info("Bootstrapped Redis cache for %d groups", count)
    return count


async def sync_container_groups(
    host_id: str,
    container_name: str,
    session: AsyncSession,
) -> None:
    """Re-sync caches for every group that *container_name* belongs to.

    Called when monitoring state changes for a container so that
    group-scoped rules pick up the new member on the next index refresh.
    """
    from sqlalchemy import text as sa_text

    query = sa_text("""
        SELECT DISTINCT group_id
        FROM container
        WHERE herald_id = :host_id
          AND name = :name
          AND group_id IS NOT NULL
    """)
    result = await session.execute(
        query, {"host_id": host_id, "name": container_name}
    )
    group_ids = [row[0] for row in result.fetchall()]

    for gid in group_ids:
        try:
            await sync_group_cache(gid, session)
        except Exception as e:
            logger.warning(
                "Failed to re-sync group %s after monitoring change for %s:%s: %s",
                gid, host_id, container_name, e,
            )


__all__ = [
    "sync_group_cache",
    "delete_group_cache",
    "sync_all_group_caches",
    "sync_container_groups",
]
