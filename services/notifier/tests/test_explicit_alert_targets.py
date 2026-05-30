import sys
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.modules.setdefault(
    "apprise",
    SimpleNamespace(Apprise=lambda: None),
)

from app.services.stream_consumer import StreamConsumer
from app.services.template_service import template_service


@asynccontextmanager
async def _session_ctx_stub():
    yield object()


class ExplicitAlertTargetsTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_consumer_dispatches_explicit_targets_only(self) -> None:
        consumer = StreamConsumer()
        dispatch_mock = AsyncMock(
            return_value={
                "channels_targeted": 1,
                "tasks_queued": [{"channel_id": "channel-1", "task_id": "task-1"}],
                "duplicate_suppressed": 0,
            }
        )
        alert_data = {
            "alert_id": "alert-1",
            "rule_id": "rule-1",
            "rule_name": "Keyword Error",
            "organization_id": "org-1",
            "severity": "warning",
            "fingerprint": "fp-1",
            "annotations": {"message": "matched"},
            "labels": {"container_id": "local:unicron-demo-rule-worker"},
            "notification_targets": {
                "channel_ids": ["channel-1"],
                "group_ids": ["group-1"],
                "preset_ids": ["preset-1"],
            },
        }

        with (
            patch("app.services.stream_consumer.session_ctx", new=_session_ctx_stub),
            patch("app.services.stream_consumer.dispatch_alert", new=dispatch_mock),
        ):
            await consumer._dispatch_alert(alert_data)

        kwargs = dispatch_mock.await_args.kwargs
        self.assertEqual(kwargs["alert_id"], "alert-1")
        self.assertEqual(kwargs["alert_data"]["rule_name"], "Keyword Error")
        self.assertEqual(kwargs["alert_data"]["organization_id"], "org-1")
        self.assertEqual(kwargs["channel_ids"], ["channel-1"])
        self.assertEqual(kwargs["group_ids"], ["group-1"])
        self.assertEqual(kwargs["preset_ids"], ["preset-1"])

    async def test_stream_consumer_without_explicit_targets_queues_no_defaults(self) -> None:
        consumer = StreamConsumer()
        dispatch_mock = AsyncMock(
            return_value={
                "channels_targeted": 0,
                "tasks_queued": [],
                "duplicate_suppressed": 0,
            }
        )
        alert_data = {
            "alert_id": "alert-1",
            "rule_id": "rule-1",
            "rule_name": "Keyword Error",
            "severity": "warning",
            "fingerprint": "fp-1",
            "annotations": {"message": "matched"},
            "labels": {"container_id": "local:unicron-demo-rule-worker"},
        }

        with (
            patch("app.services.stream_consumer.session_ctx", new=_session_ctx_stub),
            patch("app.services.stream_consumer.dispatch_alert", new=dispatch_mock),
        ):
            await consumer._dispatch_alert(alert_data)

        kwargs = dispatch_mock.await_args.kwargs
        self.assertIsNone(kwargs["channel_ids"])
        self.assertIsNone(kwargs["group_ids"])
        self.assertIsNone(kwargs["preset_ids"])
        self.assertEqual(kwargs["alert_data"]["organization_id"], "local")

    def test_default_discord_template_omits_duplicate_title_in_body(self) -> None:
        rendered = template_service.render(
            "discord",
            {
                "title": "[WARNING] Keyword Error",
                "rule_name": "Keyword Error",
                "message": "Pattern 'DEMO_FLOW_TRIGGER' matched 1 times in 300s (threshold=1)",
                "severity": "warning",
                "triggered_at": "2026-04-02T00:36:43.448586+00:00",
            },
        )

        self.assertNotIn("*[WARNING] Keyword Error*", rendered)
        self.assertIn("- *Rule:* Keyword Error", rendered)
        self.assertIn("- *Severity:* warning", rendered)


if __name__ == "__main__":
    unittest.main()
