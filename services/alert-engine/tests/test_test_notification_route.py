import unittest
from unittest.mock import AsyncMock, patch

from app.core.deps import UserContext
from app.routes.notifications import TestNotificationRequest, test_notification as queue_test_notification


class TestNotificationRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_test_notification_publishes_selected_severity_to_alert_stream(self) -> None:
        publish_alert = AsyncMock(return_value="1-0")
        user = UserContext(
            user_id="user-1",
            email="user@example.com",
            organization_id="org-1",
            roles=["admin"],
        )

        with (
            patch("app.routes.notifications.publish_alert", new=publish_alert),
            patch("app.routes.notifications.time.time", return_value=1234.0),
        ):
            response = await queue_test_notification(
                TestNotificationRequest(
                    rule_preview="Container restart rate is high",
                    severity="critical",
                    channel_ids=["channel-1"],
                    group_ids=["group-1"],
                ),
                user=user,
            )

        self.assertEqual(response.status, "queued")
        self.assertEqual(response.alert_id, "test_1234")
        self.assertIn("queued to notifier pipeline", response.message)

        payload = publish_alert.await_args.args[0]
        self.assertEqual(payload["alert_id"], response.alert_id)
        self.assertEqual(payload["severity"], "critical")
        self.assertEqual(payload["organization_id"], "org-1")
        self.assertEqual(
            payload["notification_targets"],
            {
                "channel_ids": ["channel-1"],
                "group_ids": ["group-1"],
                "preset_ids": [],
            },
        )


if __name__ == "__main__":
    unittest.main()
