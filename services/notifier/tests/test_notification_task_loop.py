import asyncio
import logging
import sys
import unittest
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


class _SignalStub:
    def connect(self, func=None, **kwargs):
        if func is None:
            return lambda decorated: decorated
        return func


class _TaskStub:
    def __init__(self, func):
        self.func = func
        self.id = "task-stub"

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def delay(self, *args, **kwargs):
        return SimpleNamespace(id="task-stub")


class _CeleryAppStub:
    def task(self, *args, **kwargs):
        def decorator(func):
            return _TaskStub(func)

        return decorator


celery_signals = ModuleType("celery.signals")
celery_signals.worker_process_shutdown = _SignalStub()
celery_log = ModuleType("celery.utils.log")
celery_log.get_task_logger = logging.getLogger
sys.modules.setdefault("celery.signals", celery_signals)
sys.modules.setdefault("celery.utils.log", celery_log)
sys.modules.setdefault(
    "celery_app",
    SimpleNamespace(celery_app=_CeleryAppStub()),
)
sys.modules.setdefault(
    "apprise",
    SimpleNamespace(
        Apprise=lambda: SimpleNamespace(
            add=lambda url: None,
            notify=lambda **kwargs: True,
        )
    ),
)

from app.tasks import notification_tasks


async def _capture_running_loop_id() -> int:
    return id(asyncio.get_running_loop())


class NotificationTaskLoopTests(unittest.TestCase):
    def tearDown(self) -> None:
        loop = notification_tasks._task_loop
        if loop is not None and not loop.is_closed():
            with (
                patch("app.tasks.notification_tasks.close_redis", new=AsyncMock()),
                patch("app.tasks.notification_tasks.close_database", new=AsyncMock()),
            ):
                notification_tasks._close_task_runtime_resources()
        notification_tasks._task_loop = None

    def test_reuses_single_event_loop_per_worker_process(self) -> None:
        first = notification_tasks._run_async_in_task_loop(_capture_running_loop_id())
        second = notification_tasks._run_async_in_task_loop(_capture_running_loop_id())

        self.assertEqual(first, second)

    def test_extracts_organization_id_from_alert_payload(self) -> None:
        self.assertEqual(
            notification_tasks._organization_id_from_alert_data(
                {"organization_id": "org-1", "labels": {"organization_id": "org-2"}}
            ),
            "org-1",
        )
        self.assertEqual(
            notification_tasks._organization_id_from_alert_data(
                {"labels": {"organization_id": "org-2"}}
            ),
            "org-2",
        )
        self.assertEqual(notification_tasks._organization_id_from_alert_data({}), "local")


class ScalarResultStub:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class AsyncSessionStub:
    def __init__(self, values) -> None:
        self._values = list(values)

    async def execute(self, stmt):
        if not self._values:
            raise AssertionError("Unexpected execute() call")
        return ScalarResultStub(self._values.pop(0))


class AsyncSessionContextStub:
    def __init__(self, session) -> None:
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return None


class NotificationTaskAISettingsTests(unittest.IsolatedAsyncioTestCase):
    async def test_delivery_uses_org_scoped_ai_settings_when_global_ai_disabled(self) -> None:
        channel = SimpleNamespace(
            id="channel-1",
            channel_type="discord",
            label="Discord",
            config={},
            enabled=True,
            verified=True,
        )
        session = AsyncSessionStub([channel, None])
        effective_settings = SimpleNamespace(
            ai_enabled=True,
            ollama_url="http://ollama.local:11434",
            ollama_model="llama-test",
            ai_timeout=7,
            ai_cache_ttl=30,
            ai_default_preprompt="Summarize precisely.",
        )

        with (
            patch(
                "app.tasks.notification_tasks.async_session_maker",
                return_value=AsyncSessionContextStub(session),
            ),
            patch(
                "app.tasks.notification_tasks.ai_settings_service.get_effective_settings",
                new=AsyncMock(return_value=effective_settings),
            ) as settings_mock,
            patch(
                "app.tasks.notification_tasks.enforce_delivery_rate_limit",
                new=AsyncMock(),
            ),
            patch(
                "app.tasks.notification_tasks.ai_service.enrich",
                new=AsyncMock(return_value={"ai_summary": "short summary"}),
            ) as enrich_mock,
            patch(
                "app.tasks.notification_tasks.delivery_service.deliver",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "app.tasks.notification_tasks.template_service.render",
                return_value="rendered body",
            ),
        ):
            result = await notification_tasks._send_notification_async(
                "channel-1",
                "alert-1",
                {
                    "title": "Alert",
                    "message": "boom",
                    "severity": "warning",
                    "organization_id": "org-1",
                },
            )

        self.assertTrue(result["success"])
        settings_mock.assert_awaited_once()
        _, org_id = settings_mock.await_args.args
        self.assertEqual(org_id, "org-1")
        enrich_mock.assert_awaited_once()
        self.assertIs(
            enrich_mock.await_args.kwargs["effective_settings"],
            effective_settings,
        )


if __name__ == "__main__":
    unittest.main()
