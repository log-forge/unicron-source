import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.routes.container.overview import _resolve_monitoring_enabled, get_container_overview


class _FakeCache:
    def __init__(self) -> None:
        self.repaired: list[tuple[str, dict]] = []
        self.removed_hosts: list[str] = []

    async def get_all_hosts(self):
        return [b"local"]

    async def get_overview_snapshot(self, host_ids):
        return (
            {"local": True},
            {"local": None},
            {"local": None},
            {
                "local": [
                    {
                        "container_key": "local:unicron-backend",
                        "docker_container_id": "abc123",
                        "name": "unicron-backend",
                        "status": "running",
                        "image": "backend:latest",
                        "labels": {},
                        "ports": [],
                    }
                ]
            },
            [],
        )

    async def get_host_status_snapshot(self, host_ids):
        return (
            {"local": True},
            {"local": None},
            {"local": None},
            {"local": 2},
        )

    async def get_all_monitoring_states(self):
        return {}

    async def get_log_collection_states_for_hosts(self, host_ids):
        return {"local": {}}

    async def request_inventory_if_empty(self, host_id):
        return None

    async def cache_single_container(self, host_id, payload):
        self.repaired.append((host_id, payload))

    async def remove_host(self, host_id):
        self.removed_hosts.append(host_id)


class _FakeSession:
    pass


class ContainerOverviewTests(unittest.TestCase):
    def test_resolve_monitoring_enabled_prefers_canonical_state(self) -> None:
        self.assertTrue(
            _resolve_monitoring_enabled(
                "local:unicron-demo-rule-worker",
                False,
                {"local:unicron-demo-rule-worker": True},
            )
        )

    def test_resolve_monitoring_enabled_falls_back_to_cached_value(self) -> None:
        self.assertFalse(
            _resolve_monitoring_enabled(
                "local:unicron-demo-rule-worker",
                False,
                {},
            )
        )


class ContainerOverviewRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_overview_excludes_decommissioned_cached_host(self) -> None:
        fake_cache = _FakeCache()

        with (
            patch("app.routes.container.overview.get_container_cache", return_value=fake_cache),
            patch(
                "app.routes.container.overview.list_registered_herald_ids_by_ids",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.routes.container.overview.list_active_containers",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = await get_container_overview(session=_FakeSession())

        self.assertEqual(response.hosts, [])
        self.assertEqual(response.containers, [])
        self.assertEqual(fake_cache.removed_hosts, ["local"])

    async def test_overview_recovers_missing_cached_containers_from_db(self) -> None:
        fake_cache = _FakeCache()
        db_containers = [
            SimpleNamespace(
                container_key="local:unicron-backend",
                docker_container_id="abc123",
                name="unicron-backend",
                status="running",
                image="backend:latest",
                herald_id="local",
                labels={},
                ports=[],
                started_at=None,
                monitoring_enabled=False,
            ),
            SimpleNamespace(
                container_key="local:unicron-frontend",
                docker_container_id="def456",
                name="unicron-frontend",
                status="running",
                image="frontend:latest",
                herald_id="local",
                labels={},
                ports=[],
                started_at=None,
                monitoring_enabled=False,
            ),
        ]

        with (
            patch("app.routes.container.overview.get_container_cache", return_value=fake_cache),
            patch(
                "app.routes.container.overview.list_registered_herald_ids_by_ids",
                new=AsyncMock(return_value=["local"]),
            ),
            patch(
                "app.routes.container.overview.list_active_containers",
                new=AsyncMock(return_value=db_containers),
            ),
        ):
            response = await get_container_overview(session=_FakeSession())

        self.assertEqual(len(response.hosts), 1)
        self.assertEqual(response.hosts[0].container_count, 2)
        self.assertEqual(
            {container.container_key for container in response.containers},
            {"local:unicron-backend", "local:unicron-frontend"},
        )
        self.assertEqual(len(fake_cache.repaired), 2)
        self.assertEqual({host_id for host_id, _payload in fake_cache.repaired}, {"local"})
        self.assertEqual(
            {payload["container_key"] for _host_id, payload in fake_cache.repaired},
            {"local:unicron-backend", "local:unicron-frontend"},
        )

    async def test_overview_backfills_incomplete_cached_payload_from_db(self) -> None:
        fake_cache = _FakeCache()

        async def _partial_snapshot(host_ids):
            return (
                {"local": True},
                {"local": None},
                {"local": None},
                {
                    "local": [
                        {
                            "container_key": "local:unicron-demo-rule-worker",
                            "docker_container_id": "abc123",
                            "name": "unicron-demo-rule-worker",
                            "status": "exited",
                            "image": "python:3.12-alpine",
                        }
                    ]
                },
                [],
            )

        async def _status_snapshot(host_ids):
            return (
                {"local": True},
                {"local": None},
                {"local": None},
                {"local": 1},
            )

        fake_cache.get_overview_snapshot = _partial_snapshot
        fake_cache.get_host_status_snapshot = _status_snapshot

        db_containers = [
            SimpleNamespace(
                container_key="local:unicron-demo-rule-worker",
                docker_container_id="abc123",
                name="unicron-demo-rule-worker",
                status="exited",
                image="python:3.12-alpine",
                herald_id="local",
                labels={"com.docker.compose.project": "unicron-demo"},
                ports=[],
                started_at=None,
                monitoring_enabled=True,
            ),
        ]

        with (
            patch("app.routes.container.overview.get_container_cache", return_value=fake_cache),
            patch(
                "app.routes.container.overview.list_registered_herald_ids_by_ids",
                new=AsyncMock(return_value=["local"]),
            ),
            patch(
                "app.routes.container.overview.list_active_containers",
                new=AsyncMock(return_value=db_containers),
            ),
        ):
            response = await get_container_overview(session=_FakeSession())

        self.assertEqual(len(response.containers), 1)
        self.assertEqual(
            response.containers[0].labels["com.docker.compose.project"],
            "unicron-demo",
        )
        self.assertEqual(len(fake_cache.repaired), 1)
        self.assertEqual(
            fake_cache.repaired[0][1]["labels"]["com.docker.compose.project"],
            "unicron-demo",
        )


if __name__ == "__main__":
    unittest.main()
