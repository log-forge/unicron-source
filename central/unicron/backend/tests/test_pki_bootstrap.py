import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.routes.security.pki.pki import cert_bootstrap
from app.routes.security.pki.schemas import CSRRequest


class CertBootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def test_go_streamer_bootstrap_consumes_token_without_reactivating_herald(self) -> None:
        session = SimpleNamespace(commit=AsyncMock())
        token = SimpleNamespace(
            id="token-1",
            herald_name="local",
            status="pending",
            created_at=datetime.now(timezone.utc),
            tags=["go-streamer", "local"],
        )
        registry = SimpleNamespace(unrevoke=AsyncMock())

        with (
            patch("app.routes.security.pki.pki.get_herald_token", new=AsyncMock(return_value=token)),
            patch("app.routes.security.pki.pki.get_agent_registry", return_value=registry),
            patch(
                "app.routes.security.pki.pki.sign_csr",
                return_value=("cert-pem", "chain-pem", datetime.now(timezone.utc)),
            ),
        ):
            response = await cert_bootstrap(
                body=CSRRequest(csr_pem="-----BEGIN CERTIFICATE REQUEST-----\n-----END CERTIFICATE REQUEST-----"),
                session=session,
                token="token-1",
            )

        self.assertEqual(response.cert_pem, "cert-pem")
        self.assertEqual(token.status, "consumed")
        registry.unrevoke.assert_awaited_once_with("local", reason="Fresh bootstrap certificate issued")
        session.commit.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
