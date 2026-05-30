import unittest
from unittest.mock import AsyncMock

from app.services.group_service import GroupService


class TestGroupServiceContainerKeyQueries(unittest.IsolatedAsyncioTestCase):
    async def test_add_containers_updates_by_container_key(self) -> None:
        session = AsyncMock()
        session.execute.return_value = type("Result", (), {"rowcount": 2})()
        service = GroupService(session)

        await service._add_containers_to_group(
            group_id="group-1",
            container_ids=["local:c1", "local:c2"],
        )

        query = str(session.execute.await_args.args[0])
        params = session.execute.await_args.args[1]
        self.assertIn("container_key IN", query)
        self.assertNotIn("container_id IN", query)
        self.assertEqual(params["group_id"], "group-1")

    async def test_remove_containers_updates_by_container_key(self) -> None:
        session = AsyncMock()
        session.execute.return_value = type("Result", (), {"rowcount": 1})()
        service = GroupService(session)

        await service._remove_containers_from_group(
            group_id="group-1",
            container_ids=["local:c1"],
        )

        query = str(session.execute.await_args.args[0])
        params = session.execute.await_args.args[1]
        self.assertIn("container_key IN", query)
        self.assertNotIn("container_id IN", query)
        self.assertEqual(params["group_id"], "group-1")


if __name__ == "__main__":
    unittest.main()
