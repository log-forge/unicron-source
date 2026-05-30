import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.container_runtime import ContainerRuntimeService


@asynccontextmanager
async def _fake_session_ctx():
    yield object()


class _FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.commits = 0

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1


def _fake_session_ctx_for(session):
    @asynccontextmanager
    async def _ctx():
        yield session

    return _ctx


class ContainerRuntimeEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_die_event_keeps_container_cached_as_exited(self) -> None:
        service = ContainerRuntimeService()
        fake_cache = SimpleNamespace(
            remove_container=AsyncMock(),
            cache_single_container=AsyncMock(),
        )
        fake_bus = SimpleNamespace(emit_container_event=AsyncMock())
        fake_container = SimpleNamespace(
            container_key="local:unicron-demo-rule-worker",
            docker_container_id="abc123",
            name="unicron-demo-rule-worker",
            status="exited",
            image="python:3.12-alpine",
            labels={"com.docker.compose.project": "unicron-demo"},
            ports=[],
            started_at=None,
            monitoring_enabled=True,
        )

        with (
            patch("app.services.container_runtime.get_container_cache", return_value=fake_cache),
            patch("app.services.container_runtime.session_ctx", new=_fake_session_ctx),
            patch(
                "app.services.container_runtime.upsert_container",
                new=AsyncMock(return_value=(fake_container, False)),
            ),
            patch("app.services.container_runtime.get_realtime_event_bus", return_value=fake_bus),
        ):
            payload = await service.apply_lifecycle_event(
                "local",
                {
                    "name": "unicron-demo-rule-worker",
                    "action": "die",
                    "status": "exited",
                    "container_id": "abc123",
                },
            )

        fake_cache.remove_container.assert_not_awaited()
        fake_cache.cache_single_container.assert_awaited_once_with(
            "local",
            {
                "container_key": "local:unicron-demo-rule-worker",
                "docker_container_id": "abc123",
                "name": "unicron-demo-rule-worker",
                "status": "exited",
                "image": "python:3.12-alpine",
                "host_id": "local",
                "labels": {"com.docker.compose.project": "unicron-demo"},
                "ports": [],
                "started_at": None,
                "monitoring_enabled": True,
            },
        )
        self.assertEqual(payload["status"], "exited")
        self.assertEqual(payload["container_key"], "local:unicron-demo-rule-worker")

    async def test_destroy_event_removes_container_from_cache(self) -> None:
        service = ContainerRuntimeService()
        fake_cache = SimpleNamespace(
            remove_container=AsyncMock(),
            cache_single_container=AsyncMock(),
            clear_monitoring_state=AsyncMock(),
            clear_log_collection_state=AsyncMock(),
        )
        fake_bus = SimpleNamespace(
            emit_container_event=AsyncMock(),
            emit_monitoring_state_changed=AsyncMock(),
        )
        fake_session = _FakeSession()
        container = SimpleNamespace(
            container_key="local:unicron-demo-rule-worker",
            docker_container_id="abc123",
            name="unicron-demo-rule-worker",
            status="running",
            image="python:3.12-alpine",
            monitoring_enabled=True,
        )
        publish_container_event = AsyncMock()

        with (
            patch("app.services.container_runtime.get_container_cache", return_value=fake_cache),
            patch("app.services.container_runtime.session_ctx", new=_fake_session_ctx_for(fake_session)),
            patch("app.services.container_runtime.get_container_by_key", new=AsyncMock(return_value=container)),
            patch("app.services.container_runtime.get_realtime_event_bus", return_value=fake_bus),
            patch("app.services.container_runtime.publish_container_event", new=publish_container_event),
        ):
            payload = await service.apply_lifecycle_event(
                "local",
                {
                    "name": "unicron-demo-rule-worker",
                    "action": "destroy",
                    "status": "removed",
                    "container_id": "abc123",
                },
            )

        fake_cache.remove_container.assert_awaited_once_with(
            "local",
            "local:unicron-demo-rule-worker",
        )
        fake_cache.clear_log_collection_state.assert_awaited_once_with(
            "local",
            "local:unicron-demo-rule-worker",
        )
        fake_cache.clear_monitoring_state.assert_awaited_once_with("local:unicron-demo-rule-worker")
        fake_cache.cache_single_container.assert_not_awaited()
        self.assertEqual(container.status, "removed")
        self.assertFalse(container.monitoring_enabled)
        self.assertEqual(fake_session.added, [container])
        self.assertEqual(fake_session.commits, 1)
        publish_container_event.assert_awaited_once_with(
            {
                "type": "monitoring_state_changed",
                "herald_id": "local",
                "host_id": "local",
                "container_key": "local:unicron-demo-rule-worker",
                "name": "unicron-demo-rule-worker",
                "container_id": "abc123",
                "image": "python:3.12-alpine",
                "status": "removed",
                "enabled": False,
            }
        )
        fake_bus.emit_monitoring_state_changed.assert_awaited_once_with(
            container_key="local:unicron-demo-rule-worker",
            host_id="local",
            monitoring_enabled=False,
        )
        self.assertEqual(payload["status"], "removed")

    async def test_start_event_persists_compose_labels_from_event_payload(self) -> None:
        service = ContainerRuntimeService()
        fake_cache = SimpleNamespace(
            remove_container=AsyncMock(),
            cache_single_container=AsyncMock(),
        )
        fake_bus = SimpleNamespace(emit_container_event=AsyncMock())
        fake_container = SimpleNamespace(
            container_key="local:unicron-demo-web",
            docker_container_id="web123",
            name="unicron-demo-web",
            status="running",
            image="nginx:alpine",
            labels={"com.docker.compose.project": "unicron-demo"},
            ports=[],
            started_at=None,
            monitoring_enabled=False,
        )
        upsert_mock = AsyncMock(return_value=(fake_container, False))

        with (
            patch("app.services.container_runtime.get_container_cache", return_value=fake_cache),
            patch("app.services.container_runtime.session_ctx", new=_fake_session_ctx),
            patch("app.services.container_runtime.upsert_container", new=upsert_mock),
            patch("app.services.container_runtime.get_realtime_event_bus", return_value=fake_bus),
        ):
            await service.apply_lifecycle_event(
                "local",
                {
                    "name": "unicron-demo-web",
                    "action": "start",
                    "status": "running",
                    "container_id": "web123",
                    "image": "nginx:alpine",
                    "started_at": "2026-04-02T04:00:54Z",
                    "labels": {
                        "com.docker.compose.project": "unicron-demo",
                        "com.docker.compose.service": "demo-web",
                    },
                },
            )

        upsert_mock.assert_awaited_once()
        kwargs = upsert_mock.await_args.kwargs
        self.assertEqual(kwargs["started_at"].isoformat(), "2026-04-02T04:00:54+00:00")
        static_metrics = kwargs["static_metrics"]
        self.assertIsNotNone(static_metrics)
        self.assertEqual(static_metrics.labels["com.docker.compose.project"], "unicron-demo")
        self.assertEqual(static_metrics.labels["com.docker.compose.service"], "demo-web")


if __name__ == "__main__":
    unittest.main()
