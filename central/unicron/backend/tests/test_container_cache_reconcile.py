import json
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.container_cache import (
    ContainerCache,
    KEY_ALL_HOSTS,
    KEY_CONTAINER,
    KEY_HOST_CONTAINERS,
    KEY_HOST_ONLINE,
    KEY_MONITORING,
    KEY_MONITORING_INDEX_ALL,
    KEY_MONITORING_INDEX_HOST,
)


class _FakePipeline:
    def __init__(self, redis: "_FakeRedis") -> None:
        self._redis = redis
        self._commands: list[tuple[str, tuple, dict]] = []

    async def __aenter__(self) -> "_FakePipeline":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, key: str):
        self._commands.append(("get", (key,), {}))
        return self

    async def set(self, key: str, value: str, **kwargs):
        self._commands.append(("set", (key, value), kwargs))
        return self

    async def setnx(self, key: str, value: str):
        self._commands.append(("setnx", (key, value), {}))
        return self

    async def expire(self, key: str, seconds: int):
        self._commands.append(("expire", (key, seconds), {}))
        return self

    async def delete(self, key: str):
        self._commands.append(("delete", (key,), {}))
        return self

    async def sadd(self, key: str, *values: str):
        self._commands.append(("sadd", (key, *values), {}))
        return self

    async def srem(self, key: str, *values: str):
        self._commands.append(("srem", (key, *values), {}))
        return self

    async def scard(self, key: str):
        self._commands.append(("scard", (key,), {}))
        return self

    async def smembers(self, key: str):
        self._commands.append(("smembers", (key,), {}))
        return self

    async def hset(self, key: str, field: str, value: int):
        self._commands.append(("hset", (key, field, value), {}))
        return self

    async def hincrby(self, key: str, field: str, value: int):
        self._commands.append(("hincrby", (key, field, value), {}))
        return self

    async def execute(self, *args, **kwargs):
        results = []
        for method, method_args, method_kwargs in self._commands:
            fn = getattr(self._redis, method)
            results.append(await fn(*method_args, **method_kwargs))
        self._commands.clear()
        return results


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
        self.hashes: dict[str, dict[str, int]] = {}
        self.expirations: list[tuple[str, int]] = []

    def pipeline(self, transaction: bool = False) -> _FakePipeline:
        return _FakePipeline(self)

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, **kwargs):
        self.values[key] = str(value)
        return True

    async def setnx(self, key: str, value: str):
        if key in self.values:
            return False
        self.values[key] = str(value)
        return True

    async def expire(self, key: str, seconds: int):
        self.expirations.append((key, int(seconds)))
        return True

    async def delete(self, key: str):
        existed = key in self.values
        self.values.pop(key, None)
        return 1 if existed else 0

    async def sadd(self, key: str, *values: str):
        bucket = self.sets.setdefault(key, set())
        before = len(bucket)
        bucket.update(str(v) for v in values)
        return len(bucket) - before

    async def srem(self, key: str, *values: str):
        bucket = self.sets.setdefault(key, set())
        removed = 0
        for value in values:
            if value in bucket:
                bucket.remove(value)
                removed += 1
        return removed

    async def smembers(self, key: str):
        return set(self.sets.get(key, set()))

    async def scard(self, key: str):
        return len(self.sets.get(key, set()))

    async def mget(self, keys):
        return [self.values.get(key) for key in keys]

    async def hset(self, key: str, field: str, value: int):
        bucket = self.hashes.setdefault(key, {})
        bucket[field] = int(value)
        return 1

    async def hincrby(self, key: str, field: str, value: int):
        bucket = self.hashes.setdefault(key, {})
        bucket[field] = int(bucket.get(field, 0)) + int(value)
        return bucket[field]


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: list(self._rows)))


def _build_session_ctx(session: _FakeSession):
    @asynccontextmanager
    async def _fake_session_ctx():
        yield session

    return _fake_session_ctx


class MonitoringReconcileTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        ContainerCache._instance = None

    async def test_reconcile_prunes_stale_refs_removed_from_db(self) -> None:
        fake_redis = _FakeRedis()
        row = SimpleNamespace(
            herald_id="host-a",
            container_key="host-a:web",
            status="running",
            monitoring_enabled=True,
        )
        valid_ref = "host-a:web"
        stale_ref = "host-b:old"

        fake_redis.sets[KEY_MONITORING_INDEX_ALL] = {valid_ref, stale_ref}
        fake_redis.sets[KEY_MONITORING_INDEX_HOST.format(host_id="host-a")] = {valid_ref}
        fake_redis.sets[KEY_MONITORING_INDEX_HOST.format(host_id="host-b")] = {stale_ref}
        fake_redis.values[KEY_MONITORING.format(container_key=valid_ref)] = "0"
        fake_redis.values[KEY_MONITORING.format(container_key=stale_ref)] = "1"
        fake_session = _FakeSession([row])

        with (
            patch("app.services.container_cache.get_redis", new=AsyncMock(return_value=fake_redis)),
            patch("app.services.container_cache.session_ctx", new=_build_session_ctx(fake_session)),
        ):
            cache = ContainerCache()
            stats = await cache.reconcile_monitoring_cache()

        self.assertEqual(stats["scanned"], 1)
        self.assertEqual(stats["pruned"], 1)
        self.assertEqual(stats["repaired"], 1)

        # Valid entry repaired to enabled=true.
        self.assertEqual(
            fake_redis.values[KEY_MONITORING.format(container_key=valid_ref)],
            "1",
        )

        # Stale entry/indexes removed.
        self.assertNotIn(
            KEY_MONITORING.format(container_key=stale_ref),
            fake_redis.values,
        )
        self.assertNotIn(stale_ref, fake_redis.sets[KEY_MONITORING_INDEX_ALL])
        self.assertNotIn(stale_ref, fake_redis.sets[KEY_MONITORING_INDEX_HOST.format(host_id="host-b")])

    async def test_clear_monitoring_state_deletes_key_and_indexes(self) -> None:
        fake_redis = _FakeRedis()
        container_key = "host-a:web"
        fake_redis.values[KEY_MONITORING.format(container_key=container_key)] = "1"
        fake_redis.sets[KEY_MONITORING_INDEX_ALL] = {container_key}
        fake_redis.sets[KEY_MONITORING_INDEX_HOST.format(host_id="host-a")] = {container_key}

        with patch("app.services.container_cache.get_redis", new=AsyncMock(return_value=fake_redis)):
            cache = ContainerCache()
            await cache.clear_monitoring_state(container_key)

        self.assertNotIn(KEY_MONITORING.format(container_key=container_key), fake_redis.values)
        self.assertNotIn(container_key, fake_redis.sets[KEY_MONITORING_INDEX_ALL])
        self.assertNotIn(container_key, fake_redis.sets[KEY_MONITORING_INDEX_HOST.format(host_id="host-a")])

    async def test_reconcile_prunes_removed_container_monitoring_refs(self) -> None:
        fake_redis = _FakeRedis()
        removed = SimpleNamespace(
            herald_id="host-a",
            container_key="host-a:removed",
            status="removed",
            monitoring_enabled=False,
        )
        fake_redis.values[KEY_MONITORING.format(container_key=removed.container_key)] = "0"
        fake_redis.sets[KEY_MONITORING_INDEX_ALL] = {removed.container_key}
        fake_redis.sets[KEY_MONITORING_INDEX_HOST.format(host_id="host-a")] = {removed.container_key}
        fake_session = _FakeSession([removed])

        with (
            patch("app.services.container_cache.get_redis", new=AsyncMock(return_value=fake_redis)),
            patch("app.services.container_cache.session_ctx", new=_build_session_ctx(fake_session)),
        ):
            cache = ContainerCache()
            stats = await cache.reconcile_monitoring_cache()

        self.assertEqual(stats["scanned"], 1)
        self.assertEqual(stats["pruned"], 1)
        self.assertNotIn(KEY_MONITORING.format(container_key=removed.container_key), fake_redis.values)
        self.assertNotIn(removed.container_key, fake_redis.sets[KEY_MONITORING_INDEX_ALL])
        self.assertNotIn(removed.container_key, fake_redis.sets[KEY_MONITORING_INDEX_HOST.format(host_id="host-a")])

    async def test_get_host_status_snapshot_returns_counts_without_payload_scan(self) -> None:
        fake_redis = _FakeRedis()
        fake_redis.values["host:host-a:online"] = "1"
        fake_redis.values["host:host-a:last_seen"] = "1700000000"
        fake_redis.values["host:host-a:online:changed_at"] = "1700000001"
        fake_redis.sets["host:host-a:containers"] = {"abc", "def"}
        fake_redis.values["host:host-b:online"] = "0"
        fake_redis.sets["host:host-b:containers"] = {"zzz"}

        with patch("app.services.container_cache.get_redis", new=AsyncMock(return_value=fake_redis)):
            cache = ContainerCache()
            statuses, last_seen, changed_at, counts = await cache.get_host_status_snapshot(["host-a", "host-b"])

        self.assertEqual(statuses["host-a"], True)
        self.assertEqual(statuses["host-b"], False)
        self.assertEqual(last_seen["host-a"], 1700000000)
        self.assertEqual(changed_at["host-a"], 1700000001)
        self.assertEqual(counts["host-a"], 2)
        self.assertEqual(counts["host-b"], 1)

    async def test_find_host_for_container_prefers_online_host(self) -> None:
        cache = ContainerCache()
        with (
            patch.object(cache, "get_all_hosts", new=AsyncMock(return_value=["host-a", "host-b"])),
            patch.object(
                cache,
                "get_overview_snapshot",
                new=AsyncMock(
                    return_value=(
                        {"host-a": False, "host-b": True},
                        {},
                        {},
                        {
                            "host-a": [{"name": "web", "container_id": "aaaa1111"}],
                            "host-b": [{"name": "web", "container_id": "bbbb2222"}],
                        },
                        [],
                    )
                ),
            ),
        ):
            resolved = await cache.find_host_for_container_ref("web")

        self.assertEqual(resolved, "host-b")

    async def test_get_overview_snapshot_returns_status_and_containers(self) -> None:
        fake_redis = _FakeRedis()
        fake_redis.values["host:host-a:online"] = "1"
        fake_redis.values["host:host-a:last_seen"] = "1700001000"
        fake_redis.values["host:host-a:online:changed_at"] = "1700001001"
        fake_redis.sets["host:host-a:containers"] = {"abc123"}
        fake_redis.values[KEY_CONTAINER.format(host_id="host-a", container_key="abc123")] = json.dumps(
            {"container_key": "abc123", "name": "web", "status": "running"}
        )

        with patch("app.services.container_cache.get_redis", new=AsyncMock(return_value=fake_redis)):
            cache = ContainerCache()
            statuses, last_seen, changed_at, host_containers, empty_online_hosts = await cache.get_overview_snapshot(
                ["host-a"]
            )

        self.assertEqual(statuses["host-a"], True)
        self.assertEqual(last_seen["host-a"], 1700001000)
        self.assertEqual(changed_at["host-a"], 1700001001)
        self.assertEqual(len(host_containers["host-a"]), 1)
        self.assertEqual(host_containers["host-a"][0]["name"], "web")
        self.assertEqual(empty_online_hosts, [])

    async def test_touch_host_heartbeat_requests_inventory_when_container_set_empty(self) -> None:
        fake_redis = _FakeRedis()

        with patch("app.services.container_cache.get_redis", new=AsyncMock(return_value=fake_redis)):
            cache = ContainerCache()
            with patch.object(
                cache,
                "request_inventory_if_empty",
                new=AsyncMock(return_value=True),
            ) as request:
                await cache.touch_host_heartbeat("host-a")

        self.assertEqual(fake_redis.values[KEY_HOST_ONLINE.format(host_id="host-a")], "1")
        self.assertIn("host-a", fake_redis.sets[KEY_ALL_HOSTS])
        request.assert_awaited_once_with("host-a")

    async def test_touch_host_heartbeat_skips_inventory_request_when_container_set_populated(self) -> None:
        fake_redis = _FakeRedis()
        fake_redis.sets[KEY_HOST_CONTAINERS.format(host_id="host-a")] = {"host-a:web"}

        with patch("app.services.container_cache.get_redis", new=AsyncMock(return_value=fake_redis)):
            cache = ContainerCache()
            with patch.object(
                cache,
                "request_inventory_if_empty",
                new=AsyncMock(return_value=True),
            ) as request:
                await cache.touch_host_heartbeat("host-a")

        request.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
