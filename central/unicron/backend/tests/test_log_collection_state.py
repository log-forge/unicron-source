import unittest
from unittest.mock import AsyncMock, patch

from app.routes.agent.ws_handler import _process_log_collection_state
from app.routes.container.overview import get_container_overview
from app.services.container_cache import ContainerCache


class _FakePipeline:
    def __init__(self, redis: "_FakeRedis") -> None:
        self._redis = redis
        self._commands: list[tuple[str, tuple, dict]] = []

    async def __aenter__(self) -> "_FakePipeline":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def set(self, key: str, value: str, **kwargs):
        self._commands.append(("set", (key, value), kwargs))
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

    async def smembers(self, key: str):
        self._commands.append(("smembers", (key,), {}))
        return self

    async def get(self, key: str):
        self._commands.append(("get", (key,), {}))
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
        self.published: list[tuple[str, str]] = []

    def pipeline(self, transaction: bool = False) -> _FakePipeline:
        return _FakePipeline(self)

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, **kwargs):
        self.values[key] = str(value)
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

class _FakeCache:
    def __init__(self, overview_snapshot, log_states):
        self._overview_snapshot = overview_snapshot
        self._log_states = log_states

    async def get_all_hosts(self):
        return [b"host-a"]

    async def get_overview_snapshot(self, host_ids):
        return self._overview_snapshot

    async def get_host_status_snapshot(self, host_ids):
        host_statuses, host_last_seen, host_status_changed_at, host_containers, _ = self._overview_snapshot
        return (
            host_statuses,
            host_last_seen,
            host_status_changed_at,
            {host_id: len(containers) for host_id, containers in host_containers.items()},
        )

    async def get_all_monitoring_states(self):
        return {}

    async def get_log_collection_states_for_hosts(self, host_ids):
        return self._log_states


class _FakeSession:
    pass


class LogCollectionStateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        ContainerCache._instance = None

    async def test_cache_round_trip_and_clear(self) -> None:
        fake_redis = _FakeRedis()
        with patch("app.services.container_cache.get_redis", new=AsyncMock(return_value=fake_redis)):
            cache = ContainerCache()
            await cache.set_log_collection_state(
                "host-a",
                "host-a:web",
                "web",
                "example/app:v1",
                status="unavailable",
                issue="missing_log_path",
                docker_container_id="abc123",
                container_name="/web",
            )

            states = await cache.get_log_collection_states_for_hosts(["host-a"])
            state = states["host-a"]["host-a:web"]
            self.assertEqual(state["host_id"], "host-a")
            self.assertEqual(state["name"], "web")
            self.assertEqual(state["image"], "example/app:v1")
            self.assertEqual(state["container_name"], "web")
            self.assertEqual(state["docker_container_id"], "abc123")
            self.assertEqual(state["log_collection_status"], "unavailable")
            self.assertEqual(state["log_collection_issue"], "missing_log_path")

            await cache.clear_log_collection_state("host-a", "host-a:web")
            states_after_clear = await cache.get_log_collection_states_for_hosts(["host-a"])
            self.assertEqual(states_after_clear["host-a"], {})

    async def test_process_log_collection_state_persists_and_broadcasts(self) -> None:
        fake_cache = AsyncMock()
        realtime = AsyncMock()
        with (
            patch("app.routes.agent.ws_handler.get_container_cache", return_value=fake_cache),
            patch("app.routes.agent.ws_handler.get_realtime_event_bus", return_value=realtime),
        ):
            await _process_log_collection_state(
                "host-a",
                {
                    "name": "web",
                    "image": "example/app:v1",
                    "log_collection_status": "unavailable",
                    "log_collection_issue": "missing_log_path",
                    "container_name": "/web",
                    "docker_container_id": "abc123",
                },
            )

        fake_cache.set_log_collection_state.assert_awaited_once_with(
            "host-a",
            "host-a:web",
            "web",
            "example/app:v1",
            status="unavailable",
            issue="missing_log_path",
            docker_container_id="abc123",
            container_name="web",
        )

        realtime.emit_log_collection_state_changed.assert_awaited_once_with(
            {
                "host_id": "host-a",
                "container_key": "host-a:web",
                "name": "web",
                "image": "example/app:v1",
                "log_collection_status": "unavailable",
                "log_collection_issue": "missing_log_path",
                "container_name": "web",
                "docker_container_id": "abc123",
            }
        )

    async def test_process_log_collection_state_missing_identity_returns_without_crashing(self) -> None:
        fake_cache = AsyncMock()
        realtime = AsyncMock()
        with (
            patch("app.routes.agent.ws_handler.get_container_cache", return_value=fake_cache),
            patch("app.routes.agent.ws_handler.get_realtime_event_bus", return_value=realtime),
        ):
            await _process_log_collection_state(
                "host-a",
                {
                    "image": "example/app:v1",
                    "log_collection_status": "unavailable",
                },
            )

        fake_cache.set_log_collection_state.assert_not_awaited()
        realtime.emit_log_collection_state_changed.assert_not_awaited()

    async def test_overview_annotates_log_collection_state_from_cache(self) -> None:
        fake_cache = _FakeCache(
            overview_snapshot=(
                {"host-a": True},
                {"host-a": None},
                {"host-a": None},
                {
                    "host-a": [
                        {
                            "container_key": "host-a:web",
                            "docker_container_id": "abc123",
                            "name": "web",
                            "status": "running",
                            "image": "example/app:v1",
                            "labels": {"app": "web"},
                            "ports": [],
                            "started_at": "2026-03-20T00:00:00Z",
                        }
                    ]
                },
                [],
            ),
            log_states={
                "host-a": {
                    "host-a:web": {
                        "log_collection_status": "unavailable",
                        "log_collection_issue": "missing_log_path",
                    }
                }
            },
        )

        with (
            patch("app.routes.container.overview.get_container_cache", return_value=fake_cache),
            patch(
                "app.routes.container.overview.list_registered_herald_ids_by_ids",
                new=AsyncMock(return_value=["host-a"]),
            ),
            patch("app.routes.container.overview.list_active_containers", new=AsyncMock()),
        ):
            response = await get_container_overview(session=_FakeSession())

        self.assertEqual(len(response.hosts), 1)
        self.assertEqual(len(response.containers), 1)
        container = response.containers[0]
        self.assertEqual(container.log_collection_status, "unavailable")
        self.assertEqual(container.log_collection_issue, "missing_log_path")


if __name__ == "__main__":
    unittest.main()
