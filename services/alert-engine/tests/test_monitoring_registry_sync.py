import fnmatch
import unittest
from unittest.mock import AsyncMock, patch

from app.services.container_registry import ContainerRegistry
from app.services.container_stream_consumer import ContainerStreamConsumer


class _FakeRedis:
    def __init__(self, values=None, sets=None) -> None:
        self.values = values or {}
        self.sets = sets or {}

    async def get(self, key):
        return self.values.get(key)

    async def smembers(self, key):
        return self.sets.get(key, set())

    async def scan_iter(self, match=None):
        keys = sorted(set(self.values) | set(self.sets))
        for key in keys:
            if match is None or fnmatch.fnmatch(key, match):
                yield key


class MonitoringRegistrySyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_bootstrap_from_canonical_monitoring_keys(self) -> None:
        registry = ContainerRegistry()
        fake_redis = _FakeRedis(
            values={
                "monitoring:local:unicron-demo-rule-worker": "1",
                "monitoring:local:unicron-demo-web": "0",
            },
            sets={
                "monitoring:index:all": {
                    "local:unicron-demo-rule-worker",
                    "local:unicron-demo-web",
                }
            },
        )

        with (
            patch("app.services.container_registry.get_redis", new=AsyncMock(return_value=fake_redis)),
            patch.object(registry, "clear_all", new=AsyncMock()),
            patch.object(registry, "add_container", new=AsyncMock()) as add_container,
        ):
            count = await registry.bootstrap_from_monitoring_keys()

        self.assertEqual(count, 1)
        add_container.assert_awaited_once_with(
            host_id="local",
            name="unicron-demo-rule-worker",
            container_id="",
            image="",
            status="running",
        )

    async def test_is_monitoring_enabled_reads_canonical_key(self) -> None:
        consumer = ContainerStreamConsumer()
        fake_redis = _FakeRedis(
            values={"monitoring:local:unicron-demo-rule-worker": "1"},
        )

        with patch("app.services.container_stream_consumer.get_redis", new=AsyncMock(return_value=fake_redis)):
            enabled = await consumer._is_monitoring_enabled("local", "unicron-demo-rule-worker")

        self.assertTrue(enabled)


if __name__ == "__main__":
    unittest.main()
