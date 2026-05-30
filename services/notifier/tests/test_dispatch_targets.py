import unittest
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.modules.setdefault(
    "apprise",
    SimpleNamespace(Apprise=lambda: None),
)

from app.services.dispatch_service import dispatch_alert


class RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class ScalarsResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return list(self._values)


class DispatchTargetTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatch_resolves_group_targets_and_deduplicates(self) -> None:
        group = SimpleNamespace(
            target_config={
                "channel_ids": ["channel-1", "channel-3", "disabled-channel"],
                "preset_ids": ["preset-2", "missing-preset"],
            }
        )
        db = SimpleNamespace(
            execute=AsyncMock(
                side_effect=[
                    RowsResult([("channel-1",)]),
                    RowsResult([("preset-1",)]),
                    ScalarsResult([group]),
                    RowsResult([("channel-1",), ("channel-3",)]),
                    RowsResult([("preset-2",)]),
                ]
            )
        )
        queued: list[str] = []

        queued_payloads: list[dict] = []

        def queue_notification(channel_id, alert_id, alert_data):
            queued.append(channel_id)
            queued_payloads.append(dict(alert_data))
            return f"task-{channel_id}"

        notification_tasks_module = ModuleType("app.tasks.notification_tasks")
        notification_tasks_module.queue_notification = queue_notification
        tasks_package = ModuleType("app.tasks")
        tasks_package.notification_tasks = notification_tasks_module

        with (
            patch.dict(
                sys.modules,
                {
                    "app.tasks": tasks_package,
                    "app.tasks.notification_tasks": notification_tasks_module,
                },
            ),
            patch(
                "app.services.dispatch_service._acquire_idempotency",
                new=AsyncMock(return_value=(True, None)),
            ),
        ):
            result = await dispatch_alert(
                db=db,
                alert_id="alert-1",
                alert_data={"severity": "warning", "organization_id": "org-1"},
                channel_ids=["channel-1", "disabled-channel"],
                group_ids=["group-1"],
                preset_ids=["preset-1"],
            )

        self.assertEqual(set(queued), {"channel-1", "channel-3", "preset-1", "preset-2"})
        self.assertTrue(queued_payloads)
        self.assertEqual(
            {payload["organization_id"] for payload in queued_payloads},
            {"org-1"},
        )
        self.assertEqual(result["channels_targeted"], 4)


if __name__ == "__main__":
    unittest.main()
