import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.core.config import settings
from app.core.origin_policy import (
    OriginPolicySnapshot,
    get_origin_policy,
    resolve_origin_policy,
    set_origin_policy,
)
from app.routes.settings.origin_policy import OriginPolicyUpdateBody, update_origin_policy_handler
from app.services.origin_policy_invalidation import publish_origin_policy_invalidation
from app.socket.socket_client import build_socket_server


class _FakeScalars:
    def __init__(self, cfg):
        self._cfg = cfg

    def first(self):
        return self._cfg


class _FakeResult:
    def __init__(self, cfg):
        self._cfg = cfg

    def scalars(self):
        return _FakeScalars(self._cfg)


class _FakeSession:
    def __init__(self, allowed_origins=None):
        self._cfg = None
        if allowed_origins is not None:
            self._cfg = SimpleNamespace(allowed_origins=allowed_origins)

    async def execute(self, _query):
        return _FakeResult(self._cfg)


class _FakeRedis:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, payload: str) -> int:
        self.published.append((channel, payload))
        return 1


def _request_for(origin: str):
    scheme, host = origin.split("://", 1)
    return SimpleNamespace(
        headers={"host": host},
        url=SimpleNamespace(scheme=scheme, netloc=host),
    )


class OriginPolicyResolutionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._previous_policy = get_origin_policy()

    def tearDown(self) -> None:
        set_origin_policy(self._previous_policy)

    async def test_env_origins_are_protected_and_db_origins_are_additions(self) -> None:
        session = _FakeSession(
            [
                "https://seed.example.com",
                "https://extra.example.com",
            ]
        )

        with (
            patch.object(settings, "UNICRON_ALLOWED_ORIGINS", "https://seed.example.com"),
            patch.object(settings, "CORS_ORIGINS", ""),
            patch.object(settings, "UNICRON_ALLOW_UI_ORIGIN_ADDITIONS", True),
        ):
            policy = await resolve_origin_policy(session)  # type: ignore[arg-type]

        self.assertEqual(policy.protected_allowed_origins, ("https://seed.example.com",))
        self.assertEqual(policy.stored_allowed_origins, ("https://extra.example.com",))
        self.assertEqual(policy.effective_allowed_origins, ("https://seed.example.com", "https://extra.example.com"))
        self.assertEqual(policy.source, "env+db")
        self.assertFalse(policy.env_managed)
        self.assertTrue(policy.ui_editable)

    async def test_env_origins_can_be_locked_against_ui_additions(self) -> None:
        session = _FakeSession(["https://extra.example.com"])

        with (
            patch.object(settings, "UNICRON_ALLOWED_ORIGINS", "https://seed.example.com"),
            patch.object(settings, "CORS_ORIGINS", ""),
            patch.object(settings, "UNICRON_ALLOW_UI_ORIGIN_ADDITIONS", False),
        ):
            policy = await resolve_origin_policy(session)  # type: ignore[arg-type]

        self.assertEqual(policy.protected_allowed_origins, ("https://seed.example.com",))
        self.assertEqual(policy.stored_allowed_origins, ("https://extra.example.com",))
        self.assertEqual(policy.effective_allowed_origins, ("https://seed.example.com",))
        self.assertTrue(policy.env_managed)
        self.assertFalse(policy.ui_editable)

    async def test_db_policy_still_works_without_env_origins(self) -> None:
        session = _FakeSession(["https://extra.example.com"])

        with (
            patch.object(settings, "UNICRON_ALLOWED_ORIGINS", ""),
            patch.object(settings, "CORS_ORIGINS", ""),
            patch.object(settings, "UNICRON_ALLOW_UI_ORIGIN_ADDITIONS", True),
        ):
            policy = await resolve_origin_policy(session)  # type: ignore[arg-type]

        self.assertEqual(policy.protected_allowed_origins, ())
        self.assertEqual(policy.stored_allowed_origins, ("https://extra.example.com",))
        self.assertEqual(policy.effective_allowed_origins, ("https://extra.example.com",))
        self.assertEqual(policy.source, "db")
        self.assertTrue(policy.ui_editable)


class OriginPolicyUpdateTests(unittest.IsolatedAsyncioTestCase):
    async def test_update_persists_only_ui_managed_additions(self) -> None:
        policy = OriginPolicySnapshot(
            effective_allowed_origins=("https://seed.example.com",),
            stored_allowed_origins=(),
            protected_allowed_origins=("https://seed.example.com",),
            source="env",
            env_managed=False,
            ui_editable=True,
            same_origin_only=False,
        )
        updated = OriginPolicySnapshot(
            effective_allowed_origins=("https://seed.example.com", "https://extra.example.com"),
            stored_allowed_origins=("https://extra.example.com",),
            protected_allowed_origins=("https://seed.example.com",),
            source="env+db",
            env_managed=False,
            ui_editable=True,
            same_origin_only=False,
        )
        update_config = AsyncMock(return_value=None)

        with (
            patch("app.routes.settings.origin_policy.refresh_origin_policy", new=AsyncMock(side_effect=[policy, updated])),
            patch("app.routes.settings.origin_policy.ensure_origin_policy_config", new=AsyncMock(return_value=SimpleNamespace())),
            patch("app.routes.settings.origin_policy.update_origin_policy_config", new=update_config),
            patch("app.routes.settings.origin_policy.publish_origin_policy_invalidation", new=AsyncMock()),
        ):
            response = await update_origin_policy_handler(
                OriginPolicyUpdateBody(
                    allowed_origins=[
                        "https://seed.example.com",
                        "https://extra.example.com",
                    ]
                ),
                request=_request_for("https://seed.example.com"),
                session=SimpleNamespace(),
            )

        update_config.assert_awaited_once()
        self.assertEqual(update_config.await_args.kwargs["allowed_origins"], ["https://extra.example.com"])
        self.assertEqual(response.protected_allowed_origins, ["https://seed.example.com"])
        self.assertEqual(response.stored_allowed_origins, ["https://extra.example.com"])

    async def test_update_preserves_current_request_origin_without_env_origins(self) -> None:
        policy = OriginPolicySnapshot(
            effective_allowed_origins=(),
            stored_allowed_origins=(),
            protected_allowed_origins=(),
            source="default",
            env_managed=False,
            ui_editable=True,
            same_origin_only=True,
        )
        updated = OriginPolicySnapshot(
            effective_allowed_origins=("https://extra.example.com", "https://localhost:8444"),
            stored_allowed_origins=("https://extra.example.com", "https://localhost:8444"),
            protected_allowed_origins=(),
            source="db",
            env_managed=False,
            ui_editable=True,
            same_origin_only=False,
        )
        update_config = AsyncMock(return_value=None)

        with (
            patch("app.routes.settings.origin_policy.refresh_origin_policy", new=AsyncMock(side_effect=[policy, updated])),
            patch("app.routes.settings.origin_policy.ensure_origin_policy_config", new=AsyncMock(return_value=SimpleNamespace())),
            patch("app.routes.settings.origin_policy.update_origin_policy_config", new=update_config),
            patch("app.routes.settings.origin_policy.publish_origin_policy_invalidation", new=AsyncMock()),
        ):
            response = await update_origin_policy_handler(
                OriginPolicyUpdateBody(allowed_origins=["https://extra.example.com"]),
                request=_request_for("https://localhost:8444"),
                session=SimpleNamespace(),
            )

        update_config.assert_awaited_once()
        self.assertEqual(
            update_config.await_args.kwargs["allowed_origins"],
            ["https://extra.example.com", "https://localhost:8444"],
        )
        self.assertEqual(response.stored_allowed_origins, ["https://extra.example.com", "https://localhost:8444"])

    async def test_locked_env_policy_rejects_updates(self) -> None:
        policy = OriginPolicySnapshot(
            effective_allowed_origins=("https://seed.example.com",),
            stored_allowed_origins=(),
            protected_allowed_origins=("https://seed.example.com",),
            source="env",
            env_managed=True,
            ui_editable=False,
            same_origin_only=False,
        )

        with patch("app.routes.settings.origin_policy.refresh_origin_policy", new=AsyncMock(return_value=policy)):
            with self.assertRaises(HTTPException) as ctx:
                await update_origin_policy_handler(
                    OriginPolicyUpdateBody(allowed_origins=["https://extra.example.com"]),
                    request=_request_for("https://seed.example.com"),
                    session=SimpleNamespace(),
                )

        self.assertEqual(ctx.exception.status_code, 423)


class SocketOriginPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_policy = get_origin_policy()

    def tearDown(self) -> None:
        set_origin_policy(self._previous_policy)

    def test_socket_cors_uses_live_origin_policy(self) -> None:
        server = build_socket_server(redis_url=None)
        environ = {
            "HTTP_ORIGIN": "https://allowed.example.com",
            "wsgi.url_scheme": "https",
            "HTTP_HOST": "central.example.com",
        }

        set_origin_policy(
            OriginPolicySnapshot(
                effective_allowed_origins=("https://allowed.example.com",),
                stored_allowed_origins=("https://allowed.example.com",),
                source="db",
                env_managed=False,
                same_origin_only=False,
            )
        )
        self.assertEqual(server.eio._cors_allowed_origins(environ), ["https://allowed.example.com"])

        set_origin_policy(
            OriginPolicySnapshot(
                effective_allowed_origins=("https://other.example.com",),
                stored_allowed_origins=("https://other.example.com",),
                source="db",
                env_managed=False,
                same_origin_only=False,
            )
        )
        self.assertEqual(server.eio._cors_allowed_origins(environ), [])


class OriginPolicyInvalidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_origin_policy_invalidation_uses_configured_channel(self) -> None:
        fake_redis = _FakeRedis()

        with patch("app.services.origin_policy_invalidation.get_redis", new=AsyncMock(return_value=fake_redis)):
            await publish_origin_policy_invalidation("test")

        self.assertEqual(len(fake_redis.published), 1)
        channel, payload = fake_redis.published[0]
        self.assertEqual(channel, settings.ORIGIN_POLICY_INVALIDATION_CHANNEL)
        body = json.loads(payload)
        self.assertEqual(body["type"], "origin_policy.invalidate")
        self.assertEqual(body["reason"], "test")


if __name__ == "__main__":
    unittest.main()
