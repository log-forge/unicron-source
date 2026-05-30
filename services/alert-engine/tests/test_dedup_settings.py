import unittest
from unittest.mock import AsyncMock, call

from app.core.config import Settings
from app.services.action_gatekeeper import ActionGatekeeper
from app.services.dedup import DEFAULT_DEDUP_WINDOW_SECONDS, DeduplicationService


class TestDeduplicationService(unittest.IsolatedAsyncioTestCase):
    async def test_default_window_is_fifteen_minutes(self) -> None:
        service = DeduplicationService(redis_client=AsyncMock())
        self.assertEqual(service.window_seconds, DEFAULT_DEDUP_WINDOW_SECONDS)
        self.assertEqual(DEFAULT_DEDUP_WINDOW_SECONDS, 900)

    async def test_window_seconds_is_clamped_to_one(self) -> None:
        service = DeduplicationService(redis_client=AsyncMock(), window_seconds=0)
        self.assertEqual(service.window_seconds, 1)

    async def test_disabled_dedup_never_suppresses_or_writes(self) -> None:
        redis_client = AsyncMock()
        service = DeduplicationService(
            redis_client=redis_client,
            window_seconds=300,
            enabled=False,
        )

        self.assertFalse(await service.is_duplicate("fingerprint"))
        self.assertFalse(await service.check_and_record("fingerprint"))

        redis_client.exists.assert_not_called()
        redis_client.set.assert_not_called()

    async def test_check_and_record_uses_fixed_window_set_nx_without_ttl_refresh(self) -> None:
        redis_client = AsyncMock()
        redis_client.set.side_effect = [True, False]
        service = DeduplicationService(redis_client=redis_client)

        self.assertFalse(await service.check_and_record("fingerprint"))
        self.assertTrue(await service.check_and_record("fingerprint"))

        redis_client.set.assert_has_awaits(
            [
                call("alert:dedup:fingerprint", "1", nx=True, ex=900),
                call("alert:dedup:fingerprint", "1", nx=True, ex=900),
            ]
        )
        redis_client.expire.assert_not_called()
        redis_client.pexpire.assert_not_called()


class TestGatekeeperDedupSettings(unittest.IsolatedAsyncioTestCase):
    async def test_default_settings_match_alert_suppression_defaults(self) -> None:
        gatekeeper = ActionGatekeeper()

        settings = gatekeeper.get_settings()
        self.assertEqual(
            settings["trigger_suppression_actions"],
            ["stop", "kill", "restart", "start", "notify"],
        )
        self.assertEqual(settings["dedup_window_seconds"], 900)

    async def test_apply_and_read_dedup_settings(self) -> None:
        gatekeeper = ActionGatekeeper()
        await gatekeeper.apply_settings(
            {"dedup_enabled": False, "dedup_window_seconds": 120}
        )

        settings = gatekeeper.get_settings()
        self.assertFalse(settings["dedup_enabled"])
        self.assertEqual(settings["dedup_window_seconds"], 120)

    async def test_dedup_window_is_clamped(self) -> None:
        gatekeeper = ActionGatekeeper()
        await gatekeeper.apply_settings({"dedup_window_seconds": 0})

        settings = gatekeeper.get_settings()
        self.assertEqual(settings["dedup_window_seconds"], 1)


class TestConfigDefaults(unittest.TestCase):
    def test_gatekeeper_config_defaults_match_alert_suppression_defaults(self) -> None:
        self.assertEqual(
            Settings.model_fields["GATEKEEPER_TRIGGER_SUPPRESSION_ACTIONS"].default,
            "stop,kill,restart,start,notify",
        )
        self.assertEqual(Settings.model_fields["GATEKEEPER_DEDUP_WINDOW_SECONDS"].default, 900)


if __name__ == "__main__":
    unittest.main()
