import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.group_cache import sync_group_cache


class _FakeRedis:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.sets: dict[str, set[str]] = {}
        self.expired: list[tuple[str, int]] = []

    async def delete(self, key: str):
        self.deleted.append(key)
        self.sets.pop(key, None)
        return 1

    async def sadd(self, key: str, *values: str):
        self.sets.setdefault(key, set()).update(values)
        return len(values)

    async def expire(self, key: str, seconds: int):
        self.expired.append((key, seconds))
        return True


class _FakeContainerService:
    def __init__(self, _session) -> None:
        pass

    async def get_containers_by_group(self, group_id: str):
        return [
            SimpleNamespace(container_key="host-a:web", herald_id="wrong-host", name="wrong-name"),
            SimpleNamespace(container_key="host-b:api", herald_id=None, name="api"),
        ]


class GroupCacheContainerKeyTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_group_cache_uses_persisted_container_key(self) -> None:
        redis = _FakeRedis()

        with (
            patch("app.services.group_cache.ContainerService", _FakeContainerService),
            patch("app.services.group_cache.get_redis", new=AsyncMock(return_value=redis)),
        ):
            count = await sync_group_cache("group-1", object())

        cache_key = "alert-engine:group-containers:group-1"
        self.assertEqual(count, 2)
        self.assertEqual(redis.sets[cache_key], {"host-a:web", "host-b:api"})
        self.assertNotIn("wrong-host:wrong-name", redis.sets[cache_key])


if __name__ == "__main__":
    unittest.main()
