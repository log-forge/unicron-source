import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.monitoring_policy import MonitoringPolicyService


class _FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.commits = 0

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1


class MonitoringPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_toggle_monitoring_sends_resolved_name_and_image(self) -> None:
        service = MonitoringPolicyService()
        container = SimpleNamespace(
            name="unicron-demo-rule-worker",
            image="python:3.12-alpine",
            docker_container_id=None,
            status=None,
            monitoring_enabled=False,
        )
        fake_session = _FakeSession()
        fake_registry = SimpleNamespace(
            is_online=lambda host_id: True,
            send_command=AsyncMock(return_value=True),
        )
        fake_cache = SimpleNamespace(set_monitoring_state=AsyncMock())
        realtime = SimpleNamespace(emit_monitoring_state_changed=AsyncMock())
        publish_container_event = AsyncMock()

        @asynccontextmanager
        async def fake_session_ctx():
            yield fake_session

        with (
            patch("app.services.monitoring_policy.session_ctx", new=fake_session_ctx),
            patch("app.services.monitoring_policy.get_container_by_key", new=AsyncMock(return_value=container)),
            patch("app.services.monitoring_policy.get_agent_registry", return_value=fake_registry),
            patch("app.services.monitoring_policy.get_container_cache", return_value=fake_cache),
            patch("app.services.monitoring_policy.get_realtime_event_bus", return_value=realtime),
            patch("app.services.monitoring_policy.publish_container_event", new=publish_container_event),
            patch.object(service, "create_ack_slot", new=AsyncMock()),
            patch.object(service, "wait_for_ack", new=AsyncMock(return_value={"success": True, "error": ""})),
        ):
            resolved_key, enabled = await service.toggle_monitoring(
                container_key="local:unicron-demo-rule-worker",
                host_id="local",
                enabled=True,
            )

        self.assertEqual(resolved_key, "local:unicron-demo-rule-worker")
        self.assertTrue(enabled)
        self.assertTrue(container.monitoring_enabled)
        self.assertEqual(fake_session.commits, 1)

        fake_registry.send_command.assert_awaited_once()
        host_id, command_type, payload = fake_registry.send_command.await_args.args
        self.assertEqual(host_id, "local")
        self.assertEqual(command_type, "monitoring_toggle")
        self.assertEqual(payload["container_key"], "local:unicron-demo-rule-worker")
        self.assertEqual(payload["container"], "unicron-demo-rule-worker")
        self.assertEqual(payload["name"], "unicron-demo-rule-worker")
        self.assertEqual(payload["image"], "python:3.12-alpine")
        self.assertTrue(payload["enabled"])

        fake_cache.set_monitoring_state.assert_awaited_once_with("local:unicron-demo-rule-worker", True)
        publish_container_event.assert_awaited_once_with(
            {
                "type": "monitoring_state_changed",
                "herald_id": "local",
                "host_id": "local",
                "container_key": "local:unicron-demo-rule-worker",
                "name": "unicron-demo-rule-worker",
                "container_id": "",
                "image": "python:3.12-alpine",
                "status": "",
                "enabled": True,
            }
        )
        realtime.emit_monitoring_state_changed.assert_awaited_once_with(
            container_key="local:unicron-demo-rule-worker",
            host_id="local",
            monitoring_enabled=True,
        )
