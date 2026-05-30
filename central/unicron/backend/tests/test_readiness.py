import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.main import readyz


class _FakeConnection:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def execute(self, _query):
        return 1


class _FakeEngine:
    def connect(self):
        return _FakeConnection()


class _FakeRedis:
    def __init__(self, *, pong: bool) -> None:
        self._pong = pong

    async def ping(self):
        return self._pong


class ReadinessProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_readyz_returns_ok_when_dependencies_are_ready(self) -> None:
        with (
            patch("app.main.engine", new=_FakeEngine()),
            patch("app.main.get_redis", new=AsyncMock(return_value=_FakeRedis(pong=True))),
        ):
            response = await readyz()

        self.assertEqual(response.status, "ok")
        self.assertEqual(response.dependencies["postgres"], "ok")
        self.assertEqual(response.dependencies["redis"], "ok")

    async def test_readyz_returns_503_when_redis_unavailable(self) -> None:
        with (
            patch("app.main.engine", new=_FakeEngine()),
            patch("app.main.get_redis", new=AsyncMock(side_effect=RuntimeError("redis down"))),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await readyz()

        self.assertEqual(ctx.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
