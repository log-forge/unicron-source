import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.rule_matcher import RuleMatcher


class ContainerEventIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_container_key_is_preferred_for_event_identity(self) -> None:
        matcher = RuleMatcher()
        rule = SimpleNamespace(id="rule-1", trigger_type="container_event")
        eval_rule = AsyncMock()

        event = {
            "container_key": "local:lf-shell-no-scripts",
            # Docker runtime ID must never override canonical key.
            "container_id": "e725b4e0a19fc5c069d016241ab75bbb",
            "event_type": "start",
        }

        with (
            patch.object(matcher, "maybe_refresh", new=AsyncMock()),
            patch.object(matcher, "get_applicable_rules", return_value=[rule]) as get_rules,
            patch.object(matcher, "_evaluate_container_event_rule", new=eval_rule),
        ):
            await matcher.evaluate_container_event(event)

        get_rules.assert_called_once_with("local:lf-shell-no-scripts")
        self.assertEqual(event["container_key"], "local:lf-shell-no-scripts")
        eval_rule.assert_awaited_once()

    async def test_container_event_falls_back_to_container_id_when_composite(self) -> None:
        matcher = RuleMatcher()
        rule = SimpleNamespace(id="rule-1", trigger_type="container_event")
        eval_rule = AsyncMock()

        event = {
            "container_id": "local:lf-shell-no-scripts",
            "event_type": "start",
        }

        with (
            patch.object(matcher, "maybe_refresh", new=AsyncMock()),
            patch.object(matcher, "get_applicable_rules", return_value=[rule]) as get_rules,
            patch.object(matcher, "_evaluate_container_event_rule", new=eval_rule),
        ):
            await matcher.evaluate_container_event(event)

        get_rules.assert_called_once_with("local:lf-shell-no-scripts")
        self.assertEqual(event["container_key"], "local:lf-shell-no-scripts")
        eval_rule.assert_awaited_once()

    async def test_container_event_falls_back_to_host_and_name(self) -> None:
        matcher = RuleMatcher()
        rule = SimpleNamespace(id="rule-1", trigger_type="container_event")
        eval_rule = AsyncMock()

        event = {
            "host_id": "local",
            "container_name": "lf-shell-no-scripts",
            "event_type": "start",
        }

        with (
            patch.object(matcher, "maybe_refresh", new=AsyncMock()),
            patch.object(matcher, "get_applicable_rules", return_value=[rule]) as get_rules,
            patch.object(matcher, "_evaluate_container_event_rule", new=eval_rule),
        ):
            await matcher.evaluate_container_event(event)

        get_rules.assert_called_once_with("local:lf-shell-no-scripts")
        self.assertEqual(event["container_key"], "local:lf-shell-no-scripts")
        eval_rule.assert_awaited_once()

    async def test_container_event_without_resolvable_identity_is_skipped(self) -> None:
        matcher = RuleMatcher()
        eval_rule = AsyncMock()

        event = {
            "event_type": "start",
        }

        with (
            patch.object(matcher, "maybe_refresh", new=AsyncMock()),
            patch.object(matcher, "get_applicable_rules") as get_rules,
            patch.object(matcher, "_evaluate_container_event_rule", new=eval_rule),
        ):
            await matcher.evaluate_container_event(event)

        get_rules.assert_not_called()
        eval_rule.assert_not_awaited()

    async def test_event_window_is_keyed_by_container_key(self) -> None:
        matcher = RuleMatcher()
        fake_redis = SimpleNamespace(
            zadd=AsyncMock(),
            zremrangebyscore=AsyncMock(),
            zcard=AsyncMock(return_value=1),
            expire=AsyncMock(),
            delete=AsyncMock(),
        )
        trigger_alert = AsyncMock()
        rule = SimpleNamespace(
            id="rule-1",
            trigger_type="container_event",
            trigger_config={
                "trigger_value": "start",
                "timeline_minutes": 5,
                "timeline_count": 1,
            },
            annotations={},
            labels={},
        )

        with (
            patch("app.services.rule_matcher.get_redis", new=AsyncMock(return_value=fake_redis)),
            patch.object(matcher, "_trigger_alert", new=trigger_alert),
        ):
            await matcher._evaluate_container_event_rule(
                rule=rule,
                event_data={
                    "container_key": "local:lf-shell-no-scripts",
                    "host_id": "local",
                    "container_name": "lf-shell-no-scripts",
                    "image": "demo_containers-lf-shell-no-scripts",
                },
                event_type="start",
                exit_code=127,
            )

        window_key = fake_redis.zadd.await_args.args[0]
        self.assertEqual(
            window_key,
            "alert-engine:event-window:rule-1:local:lf-shell-no-scripts",
        )
        trigger_alert.assert_awaited_once()
        result = trigger_alert.await_args.args[1]
        self.assertEqual(
            result.context.get("container_key"),
            "local:lf-shell-no-scripts",
        )


if __name__ == "__main__":
    unittest.main()
