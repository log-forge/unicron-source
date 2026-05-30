import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.agent_registry import AgentRegistry


class _FakeWebSocket:
    def __init__(self) -> None:
        self.closed: list[tuple[int | None, str | None]] = []
        self.sent: list[str] = []

    async def close(self, code: int | None = None, reason: str | None = None) -> None:
        self.closed.append((code, reason))

    async def send_text(self, payload: str) -> None:
        self.sent.append(payload)


class _FakeRedis:
    def __init__(self) -> None:
        self.revoked: set[str] = set()
        self.published: list[tuple[str, str]] = []
        self.values: dict[str, str] = {}

    async def sismember(self, _key: str, value: str) -> bool:
        return value in self.revoked

    async def sadd(self, _key: str, value: str) -> int:
        self.revoked.add(value)
        return 1

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def publish(self, channel: str, payload: str) -> int:
        self.published.append((channel, payload))
        return 1


class _AsyncSessionCtx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class AgentRegistryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # Reset singleton state between tests.
        AgentRegistry._instance = None

    async def test_stale_unregister_does_not_replace_new_connection(self) -> None:
        fake_redis = _FakeRedis()
        with patch("app.services.agent_registry.get_redis", new=AsyncMock(return_value=fake_redis)):
            registry = AgentRegistry()
            ws_old = _FakeWebSocket()
            ws_new = _FakeWebSocket()

            old_connection_id = await registry.register("host-a", ws_old)
            self.assertIsNotNone(old_connection_id)

            new_connection_id = await registry.register("host-a", ws_new)
            self.assertIsNotNone(new_connection_id)
            self.assertNotEqual(old_connection_id, new_connection_id)
            self.assertTrue(ws_old.closed, "old connection should be closed when superseded")

            # Simulate stale finally-block unregister from old socket.
            await registry.unregister("host-a", connection_id=old_connection_id)

            active = registry.get_connection("host-a")
            self.assertIsNotNone(active)
            self.assertEqual(active.connection_id, new_connection_id)

    async def test_send_command_relays_to_pubsub_when_host_not_local(self) -> None:
        fake_redis = _FakeRedis()
        with patch("app.services.agent_registry.get_redis", new=AsyncMock(return_value=fake_redis)):
            registry = AgentRegistry()
            sent = await registry.send_command(
                "remote-host",
                "request_inventory",
                {"reason": "cache_empty"},
            )

        self.assertTrue(sent)
        self.assertEqual(len(fake_redis.published), 1)
        channel, payload = fake_redis.published[0]
        self.assertIn("agent:commands", channel)
        body = json.loads(payload)
        self.assertEqual(body["host_id"], "remote-host")
        self.assertEqual(body["command_type"], "request_inventory")

    async def test_send_command_rejects_shared_offline_host(self) -> None:
        fake_redis = _FakeRedis()
        fake_redis.values["host:remote-host:online"] = "0"
        with patch("app.services.agent_registry.get_redis", new=AsyncMock(return_value=fake_redis)):
            registry = AgentRegistry()
            sent = await registry.send_command(
                "remote-host",
                "request_inventory",
                {"reason": "offline-check"},
            )

        self.assertFalse(sent)
        self.assertEqual(len(fake_redis.published), 0)

    async def test_revoke_persists_and_disconnects_local_connection(self) -> None:
        fake_redis = _FakeRedis()
        with patch("app.services.agent_registry.get_redis", new=AsyncMock(return_value=fake_redis)):
            registry = AgentRegistry()
            ws = _FakeWebSocket()
            await registry.register("host-r", ws)
            with patch.object(registry, "_mark_host_offline", new=AsyncMock()) as mark_offline:
                await registry.revoke("host-r", reason="test-revoke")

            self.assertIsNone(registry.get_connection("host-r"))
            self.assertIn("host-r", fake_redis.revoked)
            self.assertTrue(ws.closed)
            mark_offline.assert_not_awaited()
            self.assertTrue(await registry.is_revoked("host-r"))

    async def test_revoked_host_offline_path_emits_removed_instead_of_offline(self) -> None:
        fake_redis = _FakeRedis()
        fake_redis.revoked.add("host-r")
        cache = SimpleNamespace(remove_host=AsyncMock(), set_host_online=AsyncMock())
        realtime = SimpleNamespace(emit_host_status=AsyncMock())

        with (
            patch("app.services.agent_registry.get_redis", new=AsyncMock(return_value=fake_redis)),
            patch("app.services.container_cache.get_container_cache", return_value=cache),
            patch("app.services.realtime_event_bus.get_realtime_event_bus", return_value=realtime),
            patch("app.core.database.session_ctx", return_value=_AsyncSessionCtx()),
            patch("app.models.herald.crud.herald_crud.set_socket_presence", new=AsyncMock()),
        ):
            registry = AgentRegistry()
            await registry._mark_host_offline("host-r", log_context="test")

        cache.remove_host.assert_awaited_once_with("host-r")
        cache.set_host_online.assert_not_awaited()
        realtime.emit_host_status.assert_awaited_once_with(
            host_id="host-r",
            online=False,
            removed=True,
            reason="decommissioned",
        )


if __name__ == "__main__":
    unittest.main()
