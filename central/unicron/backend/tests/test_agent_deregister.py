import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.routes.agent.deregister import deregister_agent


class AgentDeregisterTests(unittest.IsolatedAsyncioTestCase):
    async def test_deregister_registered_agent_preserves_decommission_behavior(self) -> None:
        session = object()
        herald = SimpleNamespace(id="edge-a")
        registry = SimpleNamespace(
            send_command=AsyncMock(return_value=True),
            revoke_cert_identity=AsyncMock(return_value=("fingerprint", "serial")),
            revoke=AsyncMock(),
        )
        cache = SimpleNamespace(remove_host=AsyncMock())
        realtime = SimpleNamespace(emit_host_status=AsyncMock())

        with (
            patch("app.routes.agent.deregister.get_agent_registry", Mock(return_value=registry)),
            patch("app.routes.agent.deregister.get_container_cache", Mock(return_value=cache)),
            patch("app.routes.agent.deregister.get_realtime_event_bus", Mock(return_value=realtime)),
            patch("app.routes.agent.deregister.mark_herald_unregistered", new=AsyncMock(return_value=herald)),
            patch("app.routes.agent.deregister.update_herald_token_status", new=AsyncMock()) as update_token_by_id,
        ):
            response = await deregister_agent("edge-a", session=session, _auth=None)

        self.assertTrue(response.ok)
        self.assertIn("decommissioned", response.message)
        update_token_by_id.assert_awaited_once_with(session, "edge-a", "unregistered", reason="admin")
        registry.send_command.assert_awaited_once()
        registry.revoke_cert_identity.assert_awaited_once_with(
            "edge-a",
            reason="Agent decommissioned by admin",
        )
        registry.revoke.assert_awaited_once_with("edge-a", reason="Agent decommissioned by admin")
        cache.remove_host.assert_awaited_once_with("edge-a")
        realtime.emit_host_status.assert_awaited_once_with(
            host_id="edge-a",
            online=False,
            removed=True,
            reason="decommissioned",
        )


if __name__ == "__main__":
    unittest.main()
