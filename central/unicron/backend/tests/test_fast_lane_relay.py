import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.routes.agent.ws_handler import _process_fast_logs_frame, _send_fast_tail_replay_safe
from app.services.browser_session_registry import BrowserSessionRegistry
from app.socket.constants import room_for_container_logs
from app.socket.listeners.central.container_runtime import start_container_log_view, stop_container_log_view


class _FakePipeline:
    def __init__(self, redis: "_FakeRedis") -> None:
        self._redis = redis
        self._commands: list[tuple[str, tuple, dict]] = []

    async def __aenter__(self) -> "_FakePipeline":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def set(self, key: str, value: str, **kwargs):
        self._commands.append(("set", (key, value), kwargs))
        return self

    async def delete(self, key: str):
        self._commands.append(("delete", (key,), {}))
        return self

    async def sadd(self, key: str, *values: str):
        self._commands.append(("sadd", (key, *values), {}))
        return self

    async def scard(self, key: str):
        self._commands.append(("scard", (key,), {}))
        return self

    async def srem(self, key: str, *values: str):
        self._commands.append(("srem", (key, *values), {}))
        return self

    async def lpush(self, key: str, *values: str):
        self._commands.append(("lpush", (key, *values), {}))
        return self

    async def ltrim(self, key: str, start: int, end: int):
        self._commands.append(("ltrim", (key, start, end), {}))
        return self

    async def expire(self, key: str, seconds: int):
        self._commands.append(("expire", (key, seconds), {}))
        return self

    async def execute(self, *args, **kwargs):
        results = []
        for method, method_args, method_kwargs in self._commands:
            fn = getattr(self._redis, method)
            results.append(await fn(*method_args, **method_kwargs))
        self._commands.clear()
        return results


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
        self.lists: dict[str, list[str]] = {}

    def pipeline(self, transaction: bool = False) -> _FakePipeline:
        return _FakePipeline(self)

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, **kwargs):
        if kwargs.get("nx") and (key in self.values or key in self.sets or key in self.lists):
            return False
        self.values[key] = str(value)
        return True

    async def delete(self, key: str):
        existed = key in self.values or key in self.sets or key in self.lists
        self.values.pop(key, None)
        self.sets.pop(key, None)
        self.lists.pop(key, None)
        return 1 if existed else 0

    async def sadd(self, key: str, *values: str):
        bucket = self.sets.setdefault(key, set())
        before = len(bucket)
        bucket.update(str(v) for v in values)
        return len(bucket) - before

    async def srem(self, key: str, *values: str):
        bucket = self.sets.setdefault(key, set())
        removed = 0
        for value in values:
            if value in bucket:
                bucket.remove(value)
                removed += 1
        return removed

    async def smembers(self, key: str):
        return set(self.sets.get(key, set()))

    async def scard(self, key: str):
        return len(self.sets.get(key, set()))

    async def lpush(self, key: str, *values: str):
        bucket = self.lists.setdefault(key, [])
        for value in values:
            bucket.insert(0, str(value))
        return len(bucket)

    async def ltrim(self, key: str, start: int, end: int):
        bucket = self.lists.setdefault(key, [])
        if end == -1:
            self.lists[key] = bucket[start:]
        else:
            self.lists[key] = bucket[start : end + 1]
        return True

    async def expire(self, key: str, seconds: int):
        return True

    async def lrange(self, key: str, start: int, end: int):
        bucket = self.lists.get(key, [])
        if end == -1:
            return bucket[start:]
        return bucket[start : end + 1]


class _FakeSocketServer:
    def __init__(self) -> None:
        self.entered: list[tuple[str, str]] = []
        self.left: list[tuple[str, str]] = []
        self.emitted: list[tuple[str, dict, str | None]] = []

    async def enter_room(self, sid: str, room: str) -> None:
        self.entered.append((sid, room))

    async def leave_room(self, sid: str, room: str) -> None:
        self.left.append((sid, room))

    async def emit(self, event: str, payload: dict, to: str | None = None) -> None:
        self.emitted.append((event, payload, to))


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent_json: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent_json.append(payload)


@asynccontextmanager
async def _fake_session_ctx():
    yield object()


class FastLaneRelayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        BrowserSessionRegistry._instance = None

    async def test_start_stop_log_view_uses_first_viewer_start_and_last_viewer_stop(self) -> None:
        fake_redis = _FakeRedis()
        sio = _FakeSocketServer()
        send_command = AsyncMock(return_value=True)
        fake_agent_registry = SimpleNamespace(send_command=send_command)
        container = SimpleNamespace(
            herald_id="host-a",
            name="web",
            container_key="host-a:web",
            monitoring_enabled=True,
        )

        with (
            patch("app.services.browser_session_registry.get_redis", new=AsyncMock(return_value=fake_redis)),
            patch("app.socket.listeners.central.container_runtime.session_ctx", new=_fake_session_ctx),
            patch(
                "app.socket.listeners.central.container_runtime.get_container_by_key",
                new=AsyncMock(return_value=container),
            ),
            patch("app.socket.listeners.central.container_runtime.get_agent_registry", return_value=fake_agent_registry),
        ):
            first = await start_container_log_view(sio, "sid-a", {"container_key": "host-a:web", "host_id": "host-a"})
            second = await start_container_log_view(sio, "sid-b", {"container_key": "host-a:web", "host_id": "host-a"})
            await stop_container_log_view(sio, "sid-a", {"session_id": first["session_id"]})
            await stop_container_log_view(sio, "sid-b", {"session_id": second["session_id"]})

        self.assertEqual(
            sio.entered,
            [
                ("sid-a", room_for_container_logs("host-a:web")),
                ("sid-b", room_for_container_logs("host-a:web")),
            ],
        )
        send_command.assert_any_await("host-a", "fast_tail_start", {"container_key": "host-a:web", "source": "monitored", "history_tail": "", "history_since": ""})
        send_command.assert_any_await("host-a", "fast_tail_stop", {"container_key": "host-a:web", "source": "monitored"})
        self.assertEqual(send_command.await_count, 2)
        self.assertEqual(
            sio.left,
            [
                ("sid-a", room_for_container_logs("host-a:web")),
                ("sid-b", room_for_container_logs("host-a:web")),
            ],
        )

    async def test_start_log_view_prefers_canonical_monitoring_state(self) -> None:
        fake_redis = _FakeRedis()
        sio = _FakeSocketServer()
        send_command = AsyncMock(return_value=True)
        fake_agent_registry = SimpleNamespace(send_command=send_command)
        fake_cache = SimpleNamespace(get_monitoring_state=AsyncMock(return_value=True))
        container = SimpleNamespace(
            herald_id="host-a",
            name="web",
            container_key="host-a:web",
            monitoring_enabled=False,
        )

        with (
            patch("app.services.browser_session_registry.get_redis", new=AsyncMock(return_value=fake_redis)),
            patch("app.socket.listeners.central.container_runtime.session_ctx", new=_fake_session_ctx),
            patch(
                "app.socket.listeners.central.container_runtime.get_container_by_key",
                new=AsyncMock(return_value=container),
            ),
            patch("app.socket.listeners.central.container_runtime.get_agent_registry", return_value=fake_agent_registry),
            patch("app.socket.listeners.central.container_runtime.get_container_cache", return_value=fake_cache),
        ):
            await start_container_log_view(sio, "sid-a", {"container_key": "host-a:web", "host_id": "host-a"})

        send_command.assert_awaited_once_with(
            "host-a",
            "fast_tail_start",
            {"container_key": "host-a:web", "source": "monitored", "history_tail": "", "history_since": ""},
        )

    async def test_replay_sends_active_fast_tail_subscriptions(self) -> None:
        fake_redis = _FakeRedis()
        fake_ws = _FakeWebSocket()
        with patch("app.services.browser_session_registry.get_redis", new=AsyncMock(return_value=fake_redis)):
            registry = BrowserSessionRegistry()
            await registry.register_log_session(
                sid="sid-a",
                session_id="log-1",
                host_id="host-a",
                container_key="host-a:web",
                source="monitored",
            )
            await registry.register_log_session(
                sid="sid-b",
                session_id="log-2",
                host_id="host-a",
                container_key="host-a:worker",
                source="live_only",
                history_since="2026-03-21T11:55:00Z",
            )
            await _send_fast_tail_replay_safe("host-a", fake_ws)

        self.assertCountEqual(
            fake_ws.sent_json,
            [
                {
                    "type": "fast_tail_start",
                    "data": {
                        "container_key": "host-a:web",
                        "source": "monitored",
                        "history_tail": "",
                        "history_since": "",
                    },
                },
                {
                    "type": "fast_tail_start",
                    "data": {
                        "container_key": "host-a:worker",
                        "source": "live_only",
                        "history_tail": "",
                        "history_since": "2026-03-21T11:55:00Z",
                    },
                },
            ],
        )

    async def test_fast_logs_frame_emits_container_key_room_payload(self) -> None:
        realtime = AsyncMock()
        fake_redis = _FakeRedis()
        with (
            patch("app.routes.agent.ws_handler.get_realtime_event_bus", return_value=realtime),
            patch("app.services.browser_session_registry.get_redis", new=AsyncMock(return_value=fake_redis)),
        ):
            await _process_fast_logs_frame(
                "host-a",
                {
                    "container_key": "host-a:web",
                    "row": {
                        "time": "2026-03-21T12:00:00Z",
                        "msg": "hello",
                        "container_key": "host-a:web",
                    },
                },
            )

        realtime.emit_live_logs.assert_awaited_once_with(
            "host-a:web",
            {
                "container_key": "host-a:web",
                "row": {
                    "time": "2026-03-21T12:00:00Z",
                    "msg": "hello",
                    "container_key": "host-a:web",
                },
                "message": "hello",
                "timestamp": "2026-03-21T12:00:00Z",
            },
        )


if __name__ == "__main__":
    unittest.main()
