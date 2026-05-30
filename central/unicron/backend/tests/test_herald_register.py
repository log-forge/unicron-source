import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.routes.herald.register import register_herald
from app.utils.herald_register_state import (
    REBOOTSTRAP_REQUIRED_CODE,
)
from fastapi import HTTPException


class RegisterHeraldTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_herald_is_idempotent_without_touching_newer_tokens(self) -> None:
        session = object()
        sio = object()
        existing = SimpleNamespace(
            herald_name="herald",
            central_url="https://unicron.central/unicron",
            unregistered=False,
        )

        with (
            patch("app.routes.herald.register.get_herald", new=AsyncMock(return_value=existing)),
            patch("app.routes.herald.register.get_herald_token", new=AsyncMock()) as get_token,
            patch(
                "app.routes.herald.register.get_latest_bootstrapped_go_streamer_token_by_name",
                new=AsyncMock(),
            ) as get_fallback,
            patch("app.routes.herald.register.create_herald", new=AsyncMock()) as create_herald,
            patch("app.routes.herald.register.update_herald_token_status", new=AsyncMock()) as update_status,
            patch("app.routes.herald.register.emit_herald_registered", new=AsyncMock()) as emit_registered,
        ):
            response = await register_herald(session=session, sio=sio, herald_id="herald")

        self.assertTrue(response.success)
        self.assertEqual(response.herald_id, "herald")
        get_token.assert_not_awaited()
        get_fallback.assert_not_awaited()
        create_herald.assert_not_awaited()
        update_status.assert_not_awaited()
        emit_registered.assert_not_awaited()

    async def test_existing_registration_clears_registration_failed_health_state(self) -> None:
        session = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
        sio = object()
        existing = SimpleNamespace(
            herald_name="herald",
            central_url="https://unicron.central/unicron",
            unregistered=False,
            health_status="failed",
            health_message="register: previous failure",
        )

        with (
            patch("app.routes.herald.register.get_herald", new=AsyncMock(return_value=existing)),
            patch("app.routes.herald.register.emit_herald_health_update", new=AsyncMock()) as emit_health,
        ):
            response = await register_herald(session=session, sio=sio, herald_id="herald")

        self.assertTrue(response.success)
        self.assertEqual(existing.health_status, "unknown")
        self.assertEqual(existing.health_message, "")
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(existing)
        emit_health.assert_awaited_once_with(existing, sio=sio)

    async def test_first_registration_promotes_bootstrapped_go_streamer_token(self) -> None:
        session = object()
        sio = object()
        token = SimpleNamespace(
            id="token-1",
            herald_name="herald",
            central_url="https://unicron.central/unicron",
            status="consumed",
            check_in_interval=60,
            tags=["go-streamer", "remote"],
        )

        with (
            patch("app.routes.herald.register.get_herald", new=AsyncMock(return_value=None)),
            patch("app.routes.herald.register.get_herald_token", new=AsyncMock(return_value=None)),
            patch(
                "app.routes.herald.register.get_latest_bootstrapped_go_streamer_token_by_name",
                new=AsyncMock(return_value=token),
            ),
            patch("app.routes.herald.register.create_herald", new=AsyncMock()) as create_herald,
            patch("app.routes.herald.register.update_herald_token_status", new=AsyncMock()) as update_status,
            patch("app.routes.herald.register.emit_herald_registered", new=AsyncMock()) as emit_registered,
        ):
            response = await register_herald(session=session, sio=sio, herald_id="herald")

        self.assertTrue(response.success)
        create_herald.assert_awaited_once()
        update_status.assert_awaited_once_with(session, "token-1", "active")
        emit_registered.assert_awaited_once_with(sio, "herald", token)

    async def test_first_registration_clears_persisted_token_failure(self) -> None:
        session = object()
        sio = object()
        token = SimpleNamespace(
            id="token-1",
            herald_name="herald",
            central_url="https://unicron.central/unicron",
            status="consumed",
            reason="previous register failure",
            failure_details={"code": "REGISTER_FAILED"},
            check_in_interval=60,
            tags=["go-streamer", "remote"],
        )

        with (
            patch("app.routes.herald.register.get_herald", new=AsyncMock(return_value=None)),
            patch("app.routes.herald.register.get_herald_token", new=AsyncMock(return_value=None)),
            patch(
                "app.routes.herald.register.get_latest_bootstrapped_go_streamer_token_by_name",
                new=AsyncMock(return_value=token),
            ),
            patch("app.routes.herald.register.create_herald", new=AsyncMock()),
            patch("app.routes.herald.register.update_herald_token_status", new=AsyncMock()),
            patch("app.routes.herald.register.clear_herald_token_failure", new=AsyncMock()) as clear_failure,
            patch("app.routes.herald.register.emit_herald_registered", new=AsyncMock()),
        ):
            response = await register_herald(session=session, sio=sio, herald_id="herald")

        self.assertTrue(response.success)
        clear_failure.assert_awaited_once_with(session, "token-1")

    async def test_unknown_token_is_rejected(self) -> None:
        session = object()
        sio = object()
        with (
            patch("app.routes.herald.register.get_herald", new=AsyncMock(return_value=None)),
            patch("app.routes.herald.register.get_herald_token", new=AsyncMock(return_value=None)),
            patch(
                "app.routes.herald.register.get_latest_bootstrapped_go_streamer_token_by_name",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.routes.herald.register.get_latest_pending_go_streamer_token_by_name",
                new=AsyncMock(return_value=None),
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await register_herald(session=session, sio=sio, herald_id="missing")

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Unknown or expired herald_token")

    async def test_reused_cert_with_fresh_pending_same_name_token_requests_rebootstrap(self) -> None:
        session = object()
        sio = object()
        pending_token = SimpleNamespace(
            id="token-1",
            herald_name="edge-a",
            status="pending",
            created_at=datetime.now(timezone.utc),
            tags=["go-streamer", "remote"],
        )

        with (
            patch("app.routes.herald.register.get_herald", new=AsyncMock(return_value=None)),
            patch("app.routes.herald.register.get_herald_token", new=AsyncMock(return_value=None)),
            patch(
                "app.routes.herald.register.get_latest_bootstrapped_go_streamer_token_by_name",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.routes.herald.register.get_latest_pending_go_streamer_token_by_name",
                new=AsyncMock(return_value=pending_token),
            ),
            patch("app.routes.herald.register.create_herald", new=AsyncMock()) as create_herald,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await register_herald(session=session, sio=sio, herald_id="edge-a")

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail["code"], REBOOTSTRAP_REQUIRED_CODE)
        create_herald.assert_not_awaited()

    async def test_direct_pending_go_streamer_token_still_requests_rebootstrap(self) -> None:
        session = object()
        sio = object()
        pending_token = SimpleNamespace(
            id="edge-a",
            herald_name="edge-a",
            status="pending",
            created_at=datetime.now(timezone.utc),
            tags=["go-streamer", "remote"],
        )

        with (
            patch("app.routes.herald.register.get_herald", new=AsyncMock(return_value=None)),
            patch("app.routes.herald.register.get_herald_token", new=AsyncMock(return_value=pending_token)),
            patch(
                "app.routes.herald.register.get_latest_bootstrapped_go_streamer_token_by_name",
                new=AsyncMock(),
            ) as get_fallback,
            patch("app.routes.herald.register.create_herald", new=AsyncMock()) as create_herald,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await register_herald(session=session, sio=sio, herald_id="edge-a")

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail["code"], REBOOTSTRAP_REQUIRED_CODE)
        get_fallback.assert_not_awaited()
        create_herald.assert_not_awaited()

    async def test_direct_expired_pending_go_streamer_token_keeps_plain_401(self) -> None:
        session = object()
        sio = object()
        pending_token = SimpleNamespace(
            id="edge-a",
            herald_name="edge-a",
            status="pending",
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
            tags=["go-streamer", "remote"],
        )

        with (
            patch("app.routes.herald.register.get_herald", new=AsyncMock(return_value=None)),
            patch("app.routes.herald.register.get_herald_token", new=AsyncMock(return_value=pending_token)),
            patch("app.routes.herald.register.create_herald", new=AsyncMock()) as create_herald,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await register_herald(session=session, sio=sio, herald_id="edge-a")

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Unknown or expired herald_token")
        create_herald.assert_not_awaited()

    async def test_reused_cert_with_expired_pending_same_name_token_keeps_plain_401(self) -> None:
        session = object()
        sio = object()
        pending_token = SimpleNamespace(
            id="token-1",
            herald_name="edge-a",
            status="pending",
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
            tags=["go-streamer", "remote"],
        )

        with (
            patch("app.routes.herald.register.get_herald", new=AsyncMock(return_value=None)),
            patch("app.routes.herald.register.get_herald_token", new=AsyncMock(return_value=None)),
            patch(
                "app.routes.herald.register.get_latest_bootstrapped_go_streamer_token_by_name",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.routes.herald.register.get_latest_pending_go_streamer_token_by_name",
                new=AsyncMock(return_value=pending_token),
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await register_herald(session=session, sio=sio, herald_id="edge-a")

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Unknown or expired herald_token")

    async def test_unregistered_herald_reactivates_with_fresh_bootstrapped_token(self) -> None:
        unregistered_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        session = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
        sio = object()
        existing = SimpleNamespace(
            herald_name="herald",
            central_url="https://old.central/unicron",
            unregistered=True,
            unregistered_at=unregistered_at,
            unregistered_reason="admin",
            unregistered_by="admin",
            cpu_count=2,
            health_status="unknown",
            health_message="",
        )
        token = SimpleNamespace(
            id="token-1",
            herald_name="herald",
            central_url="https://unicron.central/unicron",
            status="consumed",
            created_at=unregistered_at + timedelta(minutes=1),
            check_in_interval=60,
            tags=["go-streamer", "local"],
            failure_details=None,
            reason=None,
        )

        with (
            patch("app.routes.herald.register.get_herald", new=AsyncMock(return_value=existing)),
            patch("app.routes.herald.register.get_herald_token", new=AsyncMock(return_value=None)),
            patch(
                "app.routes.herald.register.get_latest_bootstrapped_go_streamer_token_by_name",
                new=AsyncMock(return_value=token),
            ),
            patch("app.routes.herald.register.update_herald_token_status", new=AsyncMock()) as update_status,
            patch("app.routes.herald.register.emit_herald_registered", new=AsyncMock()) as emit_registered,
        ):
            response = await register_herald(session=session, sio=sio, herald_id="herald")

        self.assertTrue(response.success)
        self.assertFalse(existing.unregistered)
        self.assertIsNone(existing.unregistered_at)
        self.assertEqual(existing.central_url, "https://unicron.central/unicron")
        update_status.assert_awaited_once_with(session, "token-1", "active")
        emit_registered.assert_awaited_once_with(sio, "herald", token)

    async def test_unregistered_herald_with_old_token_is_still_rejected(self) -> None:
        session = object()
        sio = object()
        existing = SimpleNamespace(
            herald_name="herald",
            central_url="https://unicron.central/unicron",
            unregistered=True,
            unregistered_at=datetime.now(timezone.utc),
        )
        old_token = SimpleNamespace(
            id="token-1",
            herald_name="herald",
            status="active",
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
            tags=["go-streamer", "local"],
        )
        with (
            patch("app.routes.herald.register.get_herald", new=AsyncMock(return_value=existing)),
            patch("app.routes.herald.register.get_herald_token", new=AsyncMock(return_value=None)) as get_token,
            patch(
                "app.routes.herald.register.get_latest_bootstrapped_go_streamer_token_by_name",
                new=AsyncMock(return_value=old_token),
            ) as get_fallback,
            patch(
                "app.routes.herald.register.get_latest_pending_go_streamer_token_by_name",
                new=AsyncMock(return_value=None),
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await register_herald(session=session, sio=sio, herald_id="herald")

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, "Herald was deregistered; redeploy with a new ID")
        get_token.assert_awaited_once_with(session, "herald")
        get_fallback.assert_awaited_once_with(session, "herald")

    async def test_unregistered_herald_with_fresh_pending_same_name_token_requests_rebootstrap(self) -> None:
        unregistered_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        session = object()
        sio = object()
        existing = SimpleNamespace(
            herald_name="herald",
            central_url="https://unicron.central/unicron",
            unregistered=True,
            unregistered_at=unregistered_at,
        )
        pending_token = SimpleNamespace(
            id="token-1",
            herald_name="herald",
            status="pending",
            created_at=unregistered_at + timedelta(minutes=1),
            tags=["go-streamer", "local"],
        )

        with (
            patch("app.routes.herald.register.get_herald", new=AsyncMock(return_value=existing)),
            patch("app.routes.herald.register.get_herald_token", new=AsyncMock(return_value=None)),
            patch(
                "app.routes.herald.register.get_latest_bootstrapped_go_streamer_token_by_name",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.routes.herald.register.get_latest_pending_go_streamer_token_by_name",
                new=AsyncMock(return_value=pending_token),
            ),
            patch("app.routes.herald.register.update_herald_token_status", new=AsyncMock()) as update_status,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await register_herald(session=session, sio=sio, herald_id="herald")

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail["code"], REBOOTSTRAP_REQUIRED_CODE)
        update_status.assert_not_awaited()

    async def test_unregistered_herald_with_pending_token_older_than_deregister_keeps_plain_403(self) -> None:
        unregistered_at = datetime.now(timezone.utc)
        session = object()
        sio = object()
        existing = SimpleNamespace(
            herald_name="herald",
            central_url="https://unicron.central/unicron",
            unregistered=True,
            unregistered_at=unregistered_at,
        )
        pending_token = SimpleNamespace(
            id="token-1",
            herald_name="herald",
            status="pending",
            created_at=unregistered_at - timedelta(minutes=1),
            tags=["go-streamer", "local"],
        )

        with (
            patch("app.routes.herald.register.get_herald", new=AsyncMock(return_value=existing)),
            patch("app.routes.herald.register.get_herald_token", new=AsyncMock(return_value=None)),
            patch(
                "app.routes.herald.register.get_latest_bootstrapped_go_streamer_token_by_name",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.routes.herald.register.get_latest_pending_go_streamer_token_by_name",
                new=AsyncMock(return_value=pending_token),
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await register_herald(session=session, sio=sio, herald_id="herald")

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, "Herald was deregistered; redeploy with a new ID")


if __name__ == "__main__":
    unittest.main()
