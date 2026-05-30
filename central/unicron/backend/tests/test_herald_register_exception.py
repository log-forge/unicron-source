import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.routes.herald.register_exception import register_herald_fail
from app.socket.emitters.central.herald_register_emitters import emit_herald_registration_failed


class RegisterHeraldFailTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_registration_emit_includes_structured_failure_payload(self) -> None:
        sio = SimpleNamespace(emit=AsyncMock())
        failure = {
            "code": "REGISTER_FAILED",
            "message": "Bootstrap failed.",
        }

        await emit_herald_registration_failed(
            sio,
            "edge-a",
            "edge-a",
            "Bootstrap failed.",
            room="room:test",
            failure=failure,
        )

        sio.emit.assert_awaited_once()
        event_name, payload = sio.emit.await_args.args[:2]
        self.assertEqual(event_name, "herald:registered")
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["failure"]["code"], "REGISTER_FAILED")
        self.assertEqual(payload["failure"]["message"], "Bootstrap failed.")

    async def test_token_only_failure_emits_to_plain_browser_sid(self) -> None:
        manager = SimpleNamespace(get_participants=lambda namespace, room: [("sid-a", "eio-a")])
        sio = SimpleNamespace(manager=manager, emit=AsyncMock())
        failure = {
            "code": "REGISTER_FAILED",
            "message": "Bootstrap failed.",
        }

        with patch(
            "app.socket.emitters.central.herald_register_emitters.require_socket_permissions",
            new=AsyncMock(return_value={}),
        ) as require_permissions:
            await emit_herald_registration_failed(
                sio,
                "edge-a",
                "edge-a",
                "Bootstrap failed.",
                token_only=True,
                failure=failure,
            )

        require_permissions.assert_awaited_once_with(sio, "sid-a", {"herald": ["read"]})
        sio.emit.assert_awaited_once()
        args, kwargs = sio.emit.await_args
        self.assertEqual(args[0], "herald:registered")
        self.assertEqual(args[1]["failure"]["code"], "REGISTER_FAILED")
        self.assertEqual(kwargs["to"], "sid-a")

    async def test_existing_go_streamer_herald_expires_bootstrapped_token_and_emits_health(self) -> None:
        session = object()
        sio = object()
        token = SimpleNamespace(id="token-1")
        updated = SimpleNamespace(id="herald", health_status="failed", health_message="register: boom")

        with (
            patch("app.routes.herald.register_exception.get_herald_token", new=AsyncMock(return_value=None)),
            patch(
                "app.routes.herald.register_exception.get_latest_bootstrapped_go_streamer_token_by_name",
                new=AsyncMock(return_value=token),
            ) as get_fallback,
            patch("app.routes.herald.register_exception.update_herald_token_status", new=AsyncMock()) as update_token,
            patch("app.routes.herald.register_exception.update_herald_health", new=AsyncMock(return_value=updated)) as update_health,
            patch("app.routes.herald.register_exception.set_socket_presence", new=AsyncMock(return_value=updated)) as set_presence,
            patch("app.routes.herald.register_exception.emit_herald_health_update", new=AsyncMock()) as emit_health,
            patch("app.routes.herald.register_exception.emit_herald_registration_failed", new=AsyncMock()) as emit_failed,
        ):
            response = await register_herald_fail(
                payload=SimpleNamespace(herald_id="herald", herald_name="herald", reason="boom"),
                sio=sio,
                session=session,
            )

        self.assertTrue(response.success)
        get_fallback.assert_awaited_once_with(session, "herald")
        update_token.assert_awaited_once_with(session, "token-1", "expired", reason="boom")
        update_health.assert_awaited_once()
        set_presence.assert_awaited_once()
        emit_health.assert_awaited_once_with(updated, sio=sio)
        emit_failed.assert_awaited_once_with(sio, "herald", "herald", "boom", failure=None)


if __name__ == "__main__":
    unittest.main()
