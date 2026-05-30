"""Background scheduler for periodic rule evaluation.

Runs evaluation cycles at configurable intervals, fetching enabled rules
and evaluating them against log data. Triggered evaluations create alerts
via the AlertTriggerService with Redis-backed deduplication.

Alert grouping batches related alerts for notification dispatch.

End-to-End Pipeline:
    1. Scheduler fetches enabled rules from database
    2. RuleEvaluator evaluates each rule against log/metric data
    3. AlertTriggerService creates AlertState for triggered rules
    4. Trigger service dispatches alert to Redis Stream (unicron:alerts)
    5. Notifier stream_consumer reads from Redis Stream
    6. Notifier routes alerts to explicit channels, groups, and presets
    7. Celery workers deliver notifications via Apprise
"""

import asyncio
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.database import session_ctx
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.services.action_gatekeeper import gatekeeper
from app.services.dedup import DEFAULT_DEDUP_WINDOW_SECONDS, DeduplicationService
from app.services.evaluator import EvaluationResult, RuleEvaluator
from app.services.grouping import AlertGroup, AlertGrouper
from app.services.rule_service import AlertRule, RuleService
from app.services.trigger_service import AlertTriggerService

logger = get_logger("alert-engine.scheduler")


class EvaluationScheduler:
    """
    Background scheduler for periodic rule evaluation.

    Fetches enabled rules and evaluates them at configurable intervals.
    Triggered evaluations create alerts via AlertTriggerService with
    Redis-backed deduplication. Alerts are grouped for efficient notification.
    """

    def __init__(
        self,
        interval_seconds: Optional[int] = None,
        dedup_window_seconds: int = DEFAULT_DEDUP_WINDOW_SECONDS,
        group_wait_seconds: Optional[int] = None,
        group_interval_seconds: Optional[int] = None,
    ):
        """
        Initialize the scheduler.

        Args:
            interval_seconds: Evaluation interval in seconds. Uses settings default if not provided.
            dedup_window_seconds: Fallback deduplication window in seconds.
            group_wait_seconds: Time to wait before group is ready for notification.
            group_interval_seconds: Time window for grouping subsequent alerts.
        """
        self.interval_seconds = interval_seconds or settings.EVALUATION_INTERVAL_SECONDS
        self.dedup_window_seconds = dedup_window_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._evaluator = RuleEvaluator()

        # Initialize alert grouper for notification batching
        self._grouper = AlertGrouper(
            group_wait_seconds=group_wait_seconds or settings.GROUP_WAIT_SECONDS,
            group_interval_seconds=group_interval_seconds or settings.GROUP_INTERVAL_SECONDS,
        )

    async def _build_dedup_service(
        self, redis_client
    ) -> DeduplicationService:
        """Build dedup service from runtime gatekeeper settings."""
        dedup_enabled = True
        dedup_window_seconds = self.dedup_window_seconds

        try:
            await gatekeeper.ensure_initialized()
            gatekeeper_settings = gatekeeper.get_settings()
            dedup_enabled = bool(gatekeeper_settings.get("dedup_enabled", True))
            dedup_window_seconds = max(
                1,
                int(
                    gatekeeper_settings.get(
                        "dedup_window_seconds",
                        self.dedup_window_seconds,
                    )
                ),
            )
        except Exception as exc:
            logger.warning(
                "Failed to load dedup settings from gatekeeper; using fallback (%ss, enabled=%s): %s",
                dedup_window_seconds,
                dedup_enabled,
                exc,
            )

        return DeduplicationService(
            redis_client=redis_client,
            window_seconds=dedup_window_seconds,
            enabled=dedup_enabled,
        )

    def start(self) -> None:
        """Start the background evaluation loop."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._evaluation_loop())
        logger.info(
            "Evaluation scheduler started (interval: %ds)", self.interval_seconds
        )

    async def stop(self) -> None:
        """Stop the background evaluation loop gracefully."""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("Evaluation scheduler stopped")

    async def _evaluation_loop(self) -> None:
        """Main evaluation loop - runs continuously until stopped."""
        while self._running:
            try:
                # Evaluate periodic rules via VictoriaMetrics / VictoriaLogs
                results, alerts_created = await self.evaluate_and_trigger()
                triggered_count = sum(1 for r in results if r.triggered)

                # Check absence rules for expired last-seen timestamps
                async with session_ctx() as session:
                    absence_alerts = await self._check_absence_expiry(session)

                logger.debug(
                    "Evaluation cycle complete: %d periodic rules checked (%d triggered), %d absence rules checked, %d total alerts created",
                    len(results),
                    triggered_count,
                    absence_alerts,
                    alerts_created + absence_alerts,
                )

                # Check for ready groups - alerts are already dispatched individually
                # via trigger_service → Redis Stream. Groups are for batched
                # notification display (showing "5 alerts" vs 5 separate notifications)
                ready_groups = self._grouper.get_ready_groups()
                for group in ready_groups:
                    logger.info(
                        "Alert group ready: key=%s, alerts=%d (already dispatched to stream)",
                        group.key,
                        len(group.alerts),
                    )
                    # Individual alerts dispatched in trigger_service.trigger_alert()
                    # Group info available for notification batching in notifier

            except Exception as e:
                logger.exception("Evaluation cycle failed: %s", e)

            await asyncio.sleep(self.interval_seconds)

    async def evaluate_and_trigger(self) -> Tuple[List[EvaluationResult], int]:
        """
        Evaluate all rules and trigger alerts for matches.

        Returns:
            Tuple of (list of evaluation results, count of alerts created).
        """
        results: List[EvaluationResult] = []
        alerts_created = 0

        # Get Redis client for deduplication
        redis_client = await get_redis()
        dedup = await self._build_dedup_service(redis_client)

        async with session_ctx() as session:
            # Create trigger service for this evaluation cycle
            trigger_service = AlertTriggerService(session=session, dedup=dedup)

            # Build rule lookup for triggered results
            rule_map: Dict[str, AlertRule] = {}

            # Fetch all enabled periodic rules
            rules = await self._get_periodic_rules(session)

            for rule in rules:
                rule_map[rule.id] = rule

            logger.debug("Evaluating %d enabled periodic rules", len(rules))

            # Evaluate all rules concurrently using asyncio.gather
            import time
            start_time = time.time()

            tasks = [self._evaluator.evaluate_rule(rule) for rule in rules]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

            elapsed_time = time.time() - start_time
            logger.debug(
                "Concurrent evaluation completed in %.2fs for %d rules",
                elapsed_time,
                len(rules),
            )

            # Process results - handle exceptions and trigger alerts
            for rule, result in zip(rules, raw_results):
                # If evaluation raised an exception, create a failed result
                if isinstance(result, Exception):
                    logger.error("Failed to evaluate rule %s: %s", rule.id, result)
                    result = EvaluationResult(
                        rule_id=rule.id,
                        triggered=False,
                        message=f"Evaluation error: {str(result)}",
                        context={"error": str(result)},
                    )

                results.append(result)

                # If triggered, attempt to create alert
                try:
                    if result.triggered:
                        alert_id = await trigger_service.trigger_alert(result, rule)
                        if alert_id:
                            alerts_created += 1
                            logger.info(
                                "Alert created: %s (rule: %s, message: %s)",
                                alert_id,
                                rule.id,
                                result.message,
                            )

                            # Add to grouper for notification batching
                            labels = self._build_grouping_labels(rule, result)
                            annotations = rule.annotations or {}
                            group_by = annotations.get("group_by")
                            self._grouper.add_alert(
                                alert_id=alert_id,
                                labels=labels,
                                annotations=annotations,
                                group_by=group_by,
                            )
                        else:
                            logger.debug(
                                "Alert suppressed (duplicate/silenced) for rule %s",
                                rule.id,
                            )
                except Exception as e:
                    logger.error("Failed to trigger alert for rule %s: %s", rule.id, e)

        return results, alerts_created

    async def evaluate_all_rules(self) -> List[EvaluationResult]:
        """
        Fetch all enabled rules and evaluate each one (without triggering).

        This method is kept for backwards compatibility and testing.
        For full evaluation with alert creation, use evaluate_and_trigger().

        Returns:
            List of EvaluationResult for each evaluated rule.
        """
        results, _ = await self.evaluate_and_trigger()
        return results

    def _build_grouping_labels(
        self,
        rule: AlertRule,
        result: EvaluationResult,
    ) -> Dict[str, str]:
        """
        Build labels for alert grouping.

        These labels are used by AlertGrouper to batch related alerts.

        Args:
            rule: The alert rule that triggered.
            result: The evaluation result.

        Returns:
            Dictionary of labels for grouping.
        """
        labels: Dict[str, str] = {}

        # Start with rule's static labels
        if rule.labels:
            labels.update(rule.labels)

        # Add standard labels used for grouping
        labels["rule_id"] = rule.id
        labels["rule_name"] = rule.name
        labels["severity"] = rule.severity
        labels["trigger_type"] = rule.trigger_type
        labels["scope_type"] = rule.scope_type
        labels["organization_id"] = rule.organization_id

        return labels

    async def _get_periodic_rules(self, session) -> List[AlertRule]:
        """
        Get all enabled rules evaluated by the periodic scheduler.

        Threshold rules always run here. Keyword/rate rules run here only when
        realtime stream evaluation is disabled or dual-run mode is enabled.
        Absence rules remain hybrid: stream consumers update last-seen state
        and the scheduler checks for expiry separately.

        Args:
            session: The database session.

        Returns:
            List of enabled periodic AlertRule instances.
        """
        from sqlalchemy import select

        trigger_types = ["threshold"]
        if (not settings.REALTIME_RULE_EVAL_ENABLED) or settings.REALTIME_RULE_EVAL_DUAL_RUN:
            trigger_types.extend(["keyword", "rate"])

        stmt = select(AlertRule).where(
            AlertRule.enabled == True,  # noqa: E712
            AlertRule.trigger_type.in_(trigger_types),
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _check_absence_expiry(self, session) -> int:
        """
        Check absence rules for expired last-seen timestamps.

        Absence rules are a hybrid evaluation model:
        - LogStreamConsumer updates last-seen timestamps in real-time (on log arrival)
        - Scheduler checks periodically if timestamp has expired (no logs seen)

        Args:
            session: The database session.

        Returns:
            Count of absence alerts triggered.
        """
        from sqlalchemy import select
        import time

        # Get Redis client for last-seen timestamps
        redis_client = await get_redis()
        dedup = await self._build_dedup_service(redis_client)
        trigger_service = AlertTriggerService(session=session, dedup=dedup)

        # Fetch all enabled absence rules
        stmt = select(AlertRule).where(
            AlertRule.enabled == True,  # noqa: E712
            AlertRule.trigger_type == "absence"
        )
        result = await session.execute(stmt)
        absence_rules = list(result.scalars().all())

        if not absence_rules:
            return 0

        alerts_triggered = 0
        now = time.time()

        for rule in absence_rules:
            trigger_config = rule.trigger_config or {}
            raw_window_seconds = trigger_config.get("window_seconds")
            if raw_window_seconds is not None:
                window_seconds = max(1, int(raw_window_seconds))
                window_minutes = max(1, (window_seconds + 59) // 60)
            else:
                window_minutes = int(trigger_config.get("window_minutes", 5))
                window_seconds = window_minutes * 60

            try:
                # Resolve scope to container keys
                scope_targets = await self._evaluator._resolve_scope(rule)

                for container_key in scope_targets:
                    # Check Redis last-seen timestamp
                    absence_key = f"alert-engine:absence:{rule.id}:{container_key}"
                    last_seen_str = await redis_client.get(absence_key)

                    if not last_seen_str:
                        # Container never seen - can't detect absence until first log
                        continue

                    last_seen = float(last_seen_str)
                    elapsed = now - last_seen

                    # Check if elapsed time exceeds window
                    if elapsed > window_seconds:
                        # Absence condition met - trigger alert
                        result = EvaluationResult(
                            rule_id=rule.id,
                            triggered=True,
                            value=f"{elapsed:.0f}s since last log",
                            message=f"No logs matching pattern for {window_minutes} minutes",
                            context={
                                "container_id": container_key,
                                "window_minutes": window_minutes,
                                "elapsed_seconds": int(elapsed),
                                "last_seen": last_seen,
                            },
                        )

                        alert_id = await trigger_service.trigger_alert(result, rule)
                        if alert_id:
                            alerts_triggered += 1
                            logger.info(
                                "Absence alert triggered: rule=%s, container=%s, elapsed=%.0fs",
                                rule.id,
                                container_key,
                                elapsed,
                            )

            except Exception as e:
                logger.error(
                    "Failed to check absence expiry for rule %s: %s",
                    rule.id,
                    str(e),
                )

        return alerts_triggered

    @property
    def grouper(self) -> AlertGrouper:
        """Access the alert grouper for testing or inspection."""
        return self._grouper


# Singleton scheduler instance
scheduler = EvaluationScheduler()


__all__ = ["EvaluationScheduler", "scheduler"]
