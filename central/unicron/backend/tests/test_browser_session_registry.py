import json
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.browser_session_registry import (
    BrowserSessionRegistry,
    KEY_HOST_FAST_LOGS,
    KEY_LOG_SESSION,
    KEY_LOG_VIEWERS,
    KEY_SID_LEASE,
    KEY_SID_LOGS,
    KEY_SID_STATS,
    KEY_SID_TERMS,
    KEY_STATS_SUBSCRIBERS,
    KEY_TERM_SESSION,
)


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

    async def exists(self, key: str):
        return 1 if key in self.values or key in self.sets or key in self.lists else 0

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

    async def scan_iter(self, match: str):
        prefix = match.rstrip("*")
        for key in sorted(self.values):
            if key.startswith(prefix):
                yield key
        for key in sorted(self.sets):
            if key.startswith(prefix):
                yield key


class BrowserSessionRegistryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        BrowserSessionRegistry._instance = None

    async def test_cleanup_sid_clears_sessions_and_returns_last_stats_stop(self) -> None:
        fake_redis = _FakeRedis()
        with patch("app.services.browser_session_registry.get_redis", new=AsyncMock(return_value=fake_redis)):
            registry = BrowserSessionRegistry()
            await registry.refresh_sid_lease("sid-a")
            await registry.register_log_session(
                sid="sid-a",
                session_id="log-1",
                host_id="host-a",
                container_key="host-a:web",
                source="monitored",
            )
            await registry.register_terminal_session(
                sid="sid-a",
                session_id="term-1",
                host_id="host-a",
                container_key="host-a:web",
            )
            first = await registry.add_stats_subscription(sid="sid-a", container_key="host-a:web")

            cleanup = await registry.cleanup_sid("sid-a")

        self.assertTrue(first)
        self.assertEqual([(session_id, record.host_id) for session_id, record in cleanup.logs], [("log-1", "host-a")])
        self.assertEqual(cleanup.stopped_logs, [("host-a", "host-a:web", "monitored")])
        self.assertEqual([(session_id, record.host_id) for session_id, record in cleanup.terms], [("term-1", "host-a")])
        self.assertEqual(cleanup.stopped_stats, [("host-a", "host-a:web")])
        self.assertNotIn(KEY_SID_LEASE.format(sid="sid-a"), fake_redis.values)
        self.assertNotIn(KEY_LOG_SESSION.format(session_id="log-1"), fake_redis.values)
        self.assertNotIn(KEY_TERM_SESSION.format(session_id="term-1"), fake_redis.values)
        self.assertEqual(fake_redis.sets.get(KEY_SID_LOGS.format(sid="sid-a"), set()), set())
        self.assertEqual(fake_redis.sets.get(KEY_LOG_VIEWERS.format(container_key="host-a:web"), set()), set())
        self.assertEqual(fake_redis.sets.get(KEY_HOST_FAST_LOGS.format(host_id="host-a"), set()), set())
        self.assertEqual(fake_redis.sets.get(KEY_SID_TERMS.format(sid="sid-a"), set()), set())
        self.assertEqual(fake_redis.sets.get(KEY_SID_STATS.format(sid="sid-a"), set()), set())
        self.assertEqual(fake_redis.sets.get(KEY_STATS_SUBSCRIBERS.format(container_key="host-a:web"), set()), set())

    async def test_reap_stale_sessions_stops_edge_streams(self) -> None:
        fake_redis = _FakeRedis()
        fake_redis.values[KEY_LOG_SESSION.format(session_id="log-1")] = json.dumps(
            {"sid": "stale-sid", "host_id": "host-a", "container_key": "host-a:web", "source": "monitored"}
        )
        fake_redis.values[KEY_TERM_SESSION.format(session_id="term-1")] = json.dumps(
            {"sid": "stale-sid", "host_id": "host-a", "container_key": "host-a:web"}
        )
        fake_redis.sets[KEY_SID_LOGS.format(sid="stale-sid")] = {"log-1"}
        fake_redis.sets[KEY_SID_TERMS.format(sid="stale-sid")] = {"term-1"}
        fake_redis.sets[KEY_SID_STATS.format(sid="stale-sid")] = {"host-a:web"}
        fake_redis.sets[KEY_STATS_SUBSCRIBERS.format(container_key="host-a:web")] = {"stale-sid"}

        send_command = AsyncMock(return_value=True)
        fake_agent_registry = type("FakeAgentRegistry", (), {"send_command": send_command})()
        container = SimpleNamespace(
            herald_id="host-a",
            docker_container_id="docker-123",
            name="web",
            container_key="host-a:web",
        )

        @asynccontextmanager
        async def _fake_session_ctx():
            yield object()

        with (
            patch("app.services.browser_session_registry.get_redis", new=AsyncMock(return_value=fake_redis)),
            patch("app.services.browser_session_registry.get_agent_registry", return_value=fake_agent_registry),
            patch("app.services.browser_session_registry.session_ctx", new=_fake_session_ctx),
            patch("app.services.browser_session_registry.get_container_by_key", new=AsyncMock(return_value=container)),
        ):
            registry = BrowserSessionRegistry()
            await registry._reap_stale_sessions()

        self.assertNotIn(KEY_LOG_SESSION.format(session_id="log-1"), fake_redis.values)
        self.assertNotIn(KEY_TERM_SESSION.format(session_id="term-1"), fake_redis.values)
        self.assertEqual(fake_redis.sets.get(KEY_STATS_SUBSCRIBERS.format(container_key="host-a:web"), set()), set())
        send_command.assert_any_await("host-a", "fast_tail_stop", {"container_key": "host-a:web", "source": "monitored"})
        send_command.assert_any_await("host-a", "exec_stop", {"session_id": "term-1"})
        send_command.assert_any_await(
            "host-a",
            "command",
            {
                "action": "stop_stats",
                "container_id": "docker-123",
                "container_key": "host-a:web",
            },
        )

    async def test_register_and_remove_log_sessions_track_first_and_last_viewer(self) -> None:
        fake_redis = _FakeRedis()
        with patch("app.services.browser_session_registry.get_redis", new=AsyncMock(return_value=fake_redis)):
            registry = BrowserSessionRegistry()

            first = await registry.register_log_session(
                sid="sid-a",
                session_id="log-1",
                host_id="host-a",
                container_key="host-a:web",
                source="monitored",
            )
            second = await registry.register_log_session(
                sid="sid-b",
                session_id="log-2",
                host_id="host-a",
                container_key="host-a:web",
                source="monitored",
            )
            active = await registry.get_active_fast_log_containers("host-a")
            still_subscribed = await registry.sid_has_log_subscription("sid-a", "host-a:web")
            _, last_after_first_remove = await registry.remove_log_session("log-1")
            _, last_after_second_remove = await registry.remove_log_session("log-2")

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(
            [(item.container_key, item.source, item.history_tail, item.history_since) for item in active],
            [("host-a:web", "monitored", "", "")],
        )
        self.assertTrue(still_subscribed)
        self.assertFalse(last_after_first_remove)
        self.assertTrue(last_after_second_remove)

    async def test_first_live_only_viewer_keeps_history_seed_for_replay(self) -> None:
        fake_redis = _FakeRedis()
        with patch("app.services.browser_session_registry.get_redis", new=AsyncMock(return_value=fake_redis)):
            registry = BrowserSessionRegistry()

            first = await registry.register_log_session(
                sid="sid-a",
                session_id="log-1",
                host_id="host-a",
                container_key="host-a:web",
                source="live_only",
                history_tail="250",
            )
            second = await registry.register_log_session(
                sid="sid-b",
                session_id="log-2",
                host_id="host-a",
                container_key="host-a:web",
                source="live_only",
                history_since="2026-03-21T12:00:00Z",
            )
            active = await registry.get_active_fast_log_containers("host-a")

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(
            [(item.container_key, item.source, item.history_tail, item.history_since) for item in active],
            [("host-a:web", "live_only", "250", "")],
        )


if __name__ == "__main__":
    unittest.main()
