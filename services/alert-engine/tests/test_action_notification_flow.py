import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.action_executor import ActionExecutor
from app.services.trigger_service import AlertTriggerService


class _FakeResponse:
    status_code = 200
    text = "OK"

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {
            "success": True,
            "duration_ms": 123,
            "container_state": "exited",
        }


class ActionNotificationFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_collect_notification_targets_from_notify_actions(self) -> None:
        trigger_service = AlertTriggerService(
            session=object(),
            dedup=SimpleNamespace(redis=AsyncMock()),
        )
        actions = [
            SimpleNamespace(
                action_type="notify",
                action_config={
                    "channel_ids": ["channel-1", "channel-1", ""],
                    "group_ids": ["group-1", "group-1", ""],
                    "preset_ids": ["preset-1", "preset-1", ""],
                },
            ),
            SimpleNamespace(
                action_type="stop",
                action_config={},
            ),
        ]

        with patch(
            "app.services.trigger_service.action_service.get_actions_for_rule",
            new=AsyncMock(return_value=actions),
        ):
            targets = await trigger_service._collect_notification_targets("rule-1")

        self.assertEqual(
            targets,
            {
                "channel_ids": ["channel-1"],
                "group_ids": ["group-1"],
                "preset_ids": ["preset-1"],
            },
        )

    async def test_call_central_action_api_uses_container_key_field(self) -> None:
        executor = ActionExecutor()
        fake_client = SimpleNamespace(post=AsyncMock(return_value=_FakeResponse()))

        with patch.object(executor, "_get_client", new=AsyncMock(return_value=fake_client)):
            result = await executor._call_central_action_api(
                container_id="local:unicron-demo-rule-worker",
                action_type="stop",
                action_config={"timeout_seconds": 30},
                rule_id="rule-1",
            )

        self.assertTrue(result.success)
        payload = fake_client.post.await_args.kwargs["json"]
        self.assertEqual(payload["container_key"], "local:unicron-demo-rule-worker")
        self.assertNotIn("container_id", payload)


if __name__ == "__main__":
    unittest.main()
