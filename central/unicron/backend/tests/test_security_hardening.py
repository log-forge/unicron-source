import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from starlette.datastructures import Headers

from app.core.config import settings as internal_settings
from app.core.origin_policy import (
    OriginPolicySnapshot,
    get_origin_policy,
    is_socket_origin_allowed,
    set_origin_policy,
)
from app.core.internal_secret import verify_internal_secret_header
from app.core.ws_auth import is_browser_ws_origin_allowed
from app.routes.internal.context import verify_internal_secret as verify_context_internal_secret


class _FakeWebSocket:
    def __init__(self, headers: dict[str, str], *, scheme: str = "https", hostname: str = "localhost", port: int = 443):
        self.headers = Headers(headers)
        self.url = SimpleNamespace(
            scheme=scheme,
            hostname=hostname,
            port=port,
            netloc=f"{hostname}:{port}",
        )


class BrowserWsOriginPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_policy = get_origin_policy()
        set_origin_policy(
            OriginPolicySnapshot(
                effective_allowed_origins=(),
                stored_allowed_origins=(),
                source="default",
                env_managed=False,
                same_origin_only=True,
            )
        )

    def tearDown(self) -> None:
        set_origin_policy(self._previous_policy)

    def test_same_origin_websocket_is_allowed(self) -> None:
        ws = _FakeWebSocket(
            {
                "origin": "https://localhost",
                "host": "localhost",
            },
            hostname="localhost",
            port=443,
        )
        self.assertTrue(is_browser_ws_origin_allowed(ws))

    def test_cross_origin_websocket_is_rejected_without_allowlist(self) -> None:
        ws = _FakeWebSocket(
            {
                "origin": "https://attacker.example.com",
                "host": "localhost",
            },
            hostname="localhost",
            port=443,
        )
        self.assertFalse(is_browser_ws_origin_allowed(ws))

    def test_same_origin_websocket_is_allowed_when_backend_scheme_is_ws(self) -> None:
        ws = _FakeWebSocket(
            {
                "origin": "https://localhost",
                "host": "localhost",
            },
            scheme="ws",
            hostname="localhost",
            port=8000,
        )
        self.assertTrue(is_browser_ws_origin_allowed(ws))

    def test_socket_origin_allows_ws_scheme_when_origin_is_same(self) -> None:
        environ = {
            "HTTP_ORIGIN": "https://localhost",
            "wsgi.url_scheme": "ws",
            "HTTP_HOST": "localhost",
            "SERVER_NAME": "localhost",
            "SERVER_PORT": "8000",
        }
        self.assertTrue(is_socket_origin_allowed("https://localhost", environ))

    def test_allowlisted_origin_is_allowed(self) -> None:
        set_origin_policy(
            OriginPolicySnapshot(
                effective_allowed_origins=("https://app.example.com",),
                stored_allowed_origins=("https://app.example.com",),
                source="env",
                env_managed=True,
                same_origin_only=False,
            )
        )
        ws = _FakeWebSocket(
            {
                "origin": "https://app.example.com",
                "host": "localhost",
            },
            hostname="localhost",
            port=443,
        )
        self.assertTrue(is_browser_ws_origin_allowed(ws))


class InternalSecretVerificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_context_internal_secret_requires_match_in_production(self) -> None:
        with patch.object(internal_settings, "ENVIRONMENT", "production"), patch.object(
            internal_settings, "INTERNAL_API_SECRET", "super-secret-value-1234567890"
        ):
            await verify_context_internal_secret("super-secret-value-1234567890")
            with self.assertRaises(HTTPException):
                await verify_context_internal_secret("wrong-secret")

    async def test_context_internal_secret_fails_closed_when_missing_in_production(self) -> None:
        with patch.object(internal_settings, "ENVIRONMENT", "production"), patch.object(
            internal_settings, "INTERNAL_API_SECRET", ""
        ):
            with self.assertRaises(HTTPException):
                await verify_context_internal_secret("anything")

    async def test_shared_internal_secret_validator_requires_match(self) -> None:
        with patch.object(internal_settings, "ENVIRONMENT", "production"), patch.object(
            internal_settings, "INTERNAL_API_SECRET", "action-secret-value-1234567890"
        ):
            verify_internal_secret_header("action-secret-value-1234567890")
            with self.assertRaises(HTTPException):
                verify_internal_secret_header("nope")


if __name__ == "__main__":
    unittest.main()
