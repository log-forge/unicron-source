import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.routes.agent import ws_handler
from app.routes.agent.ws_handler import (
    _apply_inventory_reconciliation_side_effects,
    _build_cached_container_payload,
    _request_inventory_refresh_safe,
    _send_agent_reconnect_replay_safe,
)


class AgentWsHandlerInventoryTests(unittest.TestCase):
    def test_build_cached_container_payload_serializes_started_at(self) -> None:
        payload = _build_cached_container_payload(
            SimpleNamespace(
                container_key="local:unicron-demo-rule-worker",
                docker_container_id="abc123",
                name="unicron-demo-rule-worker",
                status="running",
                image="python:3.12-alpine",
                labels={"demo": "true"},
                ports={"8080/tcp": [{"HostPort": "8080"}]},
                started_at=datetime(2026, 4, 1, 20, 47, 10, tzinfo=timezone.utc),
                monitoring_enabled=True,
            ),
            "local",
        )

        self.assertEqual(payload["started_at"], "2026-04-01T20:47:10+00:00")
        self.assertEqual(payload["host_id"], "local")
        self.assertTrue(payload["monitoring_enabled"])

        # This is the regression guard: Socket.IO and Redis Stream payloads must
        # be plain JSON-compatible after inventory sync.
        json.dumps(payload)


class AgentWsHandlerInventoryRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_inventory_reconciliation_clears_runtime_mirrors_and_emits_events(self) -> None:
        fake_cache = SimpleNamespace(
            remove_container=AsyncMock(),
            clear_monitoring_state=AsyncMock(),
            clear_log_collection_state=AsyncMock(),
        )
        realtime = SimpleNamespace(
            emit_monitoring_state_changed=AsyncMock(),
            emit_container_event=AsyncMock(),
        )
        result = SimpleNamespace(
            removed_container_keys=["host-a:gone"],
            monitoring_disabled_container_keys=["host-a:gone"],
        )
        publish_container_event = AsyncMock()

        with patch("app.services.alerting.streams.publish_container_event", new=publish_container_event):
            await _apply_inventory_reconciliation_side_effects(
                host_id="host-a",
                result=result,
                cache=fake_cache,
                realtime=realtime,
            )

        fake_cache.remove_container.assert_awaited_once_with("host-a", "host-a:gone")
        fake_cache.clear_monitoring_state.assert_awaited_once_with("host-a:gone")
        fake_cache.clear_log_collection_state.assert_awaited_once_with("host-a", "host-a:gone")
        publish_container_event.assert_awaited_once_with(
            {
                "type": "monitoring_state_changed",
                "herald_id": "host-a",
                "host_id": "host-a",
                "container_key": "host-a:gone",
                "name": "gone",
                "container_id": "",
                "image": "",
                "status": "removed",
                "enabled": False,
            }
        )
        realtime.emit_monitoring_state_changed.assert_awaited_once_with(
            container_key="host-a:gone",
            host_id="host-a",
            monitoring_enabled=False,
        )
        realtime.emit_container_event.assert_awaited_once_with(
            {
                "host_id": "host-a",
                "container_key": "host-a:gone",
                "name": "gone",
                "docker_container_id": None,
                "action": "destroy",
                "status": "removed",
            }
        )

    async def test_request_inventory_refresh_safe_sends_registry_command(self) -> None:
        registry = SimpleNamespace(send_command=AsyncMock(return_value=True))

        with (
            patch("app.routes.agent.ws_handler.get_agent_registry", return_value=registry),
            patch.object(ws_handler.logger, "info") as log_info,
        ):
            await _request_inventory_refresh_safe("host-a")

        registry.send_command.assert_awaited_once_with("host-a", "request_inventory")
        log_info.assert_called_once()

    async def test_request_inventory_refresh_safe_logs_false_send(self) -> None:
        registry = SimpleNamespace(send_command=AsyncMock(return_value=False))

        with (
            patch("app.routes.agent.ws_handler.get_agent_registry", return_value=registry),
            patch.object(ws_handler.logger, "warning") as log_warning,
        ):
            await _request_inventory_refresh_safe("host-a")

        registry.send_command.assert_awaited_once_with("host-a", "request_inventory")
        log_warning.assert_called_once()

    async def test_request_inventory_refresh_safe_swallows_send_failure(self) -> None:
        registry = SimpleNamespace(send_command=AsyncMock(side_effect=RuntimeError("send failed")))

        with (
            patch("app.routes.agent.ws_handler.get_agent_registry", return_value=registry),
            patch.object(ws_handler.logger, "warning") as log_warning,
        ):
            await _request_inventory_refresh_safe("host-a")

        registry.send_command.assert_awaited_once_with("host-a", "request_inventory")
        log_warning.assert_called_once()

    async def test_reconnect_replay_orders_sync_tail_then_inventory_refresh(self) -> None:
        calls: list[str] = []

        async def record_monitoring(host_id, websocket) -> None:
            calls.append("monitoring_sync")

        async def record_fast_tail(host_id, websocket) -> None:
            calls.append("fast_tail_replay")

        async def record_inventory(host_id) -> None:
            calls.append("inventory_refresh")

        with (
            patch(
                "app.routes.agent.ws_handler._send_monitoring_sync_safe",
                new=AsyncMock(side_effect=record_monitoring),
            ),
            patch(
                "app.routes.agent.ws_handler._send_fast_tail_replay_safe",
                new=AsyncMock(side_effect=record_fast_tail),
            ),
            patch(
                "app.routes.agent.ws_handler._request_inventory_refresh_safe",
                new=AsyncMock(side_effect=record_inventory),
            ),
        ):
            await _send_agent_reconnect_replay_safe("host-a", object())

        self.assertEqual(calls, ["monitoring_sync", "fast_tail_replay", "inventory_refresh"])


if __name__ == "__main__":
    unittest.main()
