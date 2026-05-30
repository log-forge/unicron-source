import json
import unittest
from unittest.mock import patch

import httpx

from app.routes.appliance.update import _proxy_updater


class _FailingClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def request(self, method, url, json=None):
        request = httpx.Request(method, url)
        raise httpx.ConnectError("connection refused", request=request)


class _OKResponse:
    status_code = 200

    def json(self):
        return {"status": "ok", "updater_health": "ok"}


class _OKClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def request(self, method, url, json=None):
        return _OKResponse()


class _SettingsResponse:
    status_code = 202

    def json(self):
        return {
            "status": "updating",
            "updater_health": "ok",
            "auto_update_enabled": True,
        }


class _SettingsClient:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def request(self, method, url, json=None):
        self.__class__.calls.append({"method": method, "url": url, "json": json})
        return _SettingsResponse()


class ApplianceUpdateProxyTests(unittest.IsolatedAsyncioTestCase):
    async def test_updater_unavailable_returns_degraded_payload(self) -> None:
        with patch("app.routes.appliance.update.httpx.AsyncClient", _FailingClient):
            response = await _proxy_updater("GET", "/status")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["updater_health"], "unavailable")
        self.assertTrue(payload["auto_update_enabled"])
        self.assertIn("connection refused", payload["last_error"])

    async def test_proxy_returns_updater_payload(self) -> None:
        with patch("app.routes.appliance.update.httpx.AsyncClient", _OKClient):
            response = await _proxy_updater("GET", "/status")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["updater_health"], "ok")

    async def test_settings_proxy_forwards_payload_and_status(self) -> None:
        _SettingsClient.calls = []
        with patch("app.routes.appliance.update.httpx.AsyncClient", _SettingsClient):
            response = await _proxy_updater("PUT", "/settings", {"auto_update_enabled": False})

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["status"], "updating")
        self.assertTrue(payload["auto_update_enabled"])
        self.assertEqual(
            _SettingsClient.calls,
            [
                {
                    "method": "PUT",
                    "url": "http://127.0.0.1:7078/settings",
                    "json": {"auto_update_enabled": False},
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
