import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.inventory_sync import InventorySyncService
from unicron_shared import ContainerState


class _FakeSession:
    def __init__(self, rows=None) -> None:
        self.rows = list(rows or [])
        self.added = []
        self.flushes = 0

    async def execute(self, _stmt):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: list(self.rows)))

    def add(self, row) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        self.flushes += 1


class InventorySyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_inventory_does_not_overwrite_central_monitoring_state(self) -> None:
        service = InventorySyncService()
        captured: dict[str, object] = {}

        async def fake_upsert(session, items, commit=False):
            captured["items"] = items
            return [], []

        with (
            patch("app.services.inventory_sync.upsert_containers_batch", new=AsyncMock(side_effect=fake_upsert)),
            patch("app.services.inventory_sync.set_container_group", new=AsyncMock()),
        ):
            await service.sync_inventory(
                _FakeSession(),
                herald_id="local",
                containers=[
                    ContainerState(
                        name="unicron-demo-rule-worker",
                        docker_container_id="abc123",
                        status="running",
                        monitoring_enabled=False,
                    )
                ],
            )

        items = captured["items"]
        self.assertEqual(len(items), 1)
        self.assertIsNone(items[0]["monitoring_enabled"])

    async def test_absent_monitored_container_is_marked_removed_and_disabled(self) -> None:
        service = InventorySyncService()
        present = SimpleNamespace(
            container_key="local:present",
            name="present",
            status="running",
            monitoring_enabled=True,
        )
        stale = SimpleNamespace(
            container_key="local:stale",
            name="stale",
            status="running",
            monitoring_enabled=True,
        )
        fake_session = _FakeSession([present, stale])

        async def fake_upsert(session, items, commit=False):
            return [present], []

        with (
            patch("app.services.inventory_sync.upsert_containers_batch", new=AsyncMock(side_effect=fake_upsert)),
            patch("app.services.inventory_sync.set_container_group", new=AsyncMock()),
        ):
            result = await service.sync_inventory(
                fake_session,
                herald_id="local",
                containers=[
                    ContainerState(
                        name="present",
                        docker_container_id="abc123",
                        status="running",
                        monitoring_enabled=False,
                    )
                ],
            )

        self.assertEqual(stale.status, "removed")
        self.assertFalse(stale.monitoring_enabled)
        self.assertTrue(present.monitoring_enabled)
        self.assertEqual(result.removed_container_keys, ["local:stale"])
        self.assertEqual(result.monitoring_disabled_container_keys, ["local:stale"])
        self.assertEqual(fake_session.added, [stale])
        self.assertEqual(fake_session.flushes, 1)

    async def test_absent_unmonitored_container_is_removed_without_disabled_event(self) -> None:
        service = InventorySyncService()
        stale = SimpleNamespace(
            container_key="local:stale",
            name="stale",
            status="exited",
            monitoring_enabled=False,
        )
        fake_session = _FakeSession([stale])

        with (
            patch("app.services.inventory_sync.upsert_containers_batch", new=AsyncMock(return_value=([], []))),
            patch("app.services.inventory_sync.set_container_group", new=AsyncMock()),
        ):
            result = await service.sync_inventory(
                fake_session,
                herald_id="local",
                containers=[],
            )

        self.assertEqual(stale.status, "removed")
        self.assertEqual(result.removed_container_keys, ["local:stale"])
        self.assertEqual(result.monitoring_disabled_container_keys, [])


if __name__ == "__main__":
    unittest.main()
