"""Alert trigger service for alert-engine.

Converts rule evaluation results into alert state records,
using deduplication to suppress duplicate alerts within a time window.
Integrates with silence service to suppress alerts during maintenance.
Executes remediation actions when alerts fire.
"""

import urllib.parse
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.alert_history import AlertHistory
from app.models.alert_state import AlertState
from app.services.alert_dispatcher import build_alert_payload, publish_alert
from app.services.alert_websocket import publish_alert_fired, publish_alert_stacked
from app.services.action_gatekeeper import gatekeeper
from app.services.action_service import action_service
from app.services.dedup import DeduplicationService, generate_fingerprint
from app.services.evaluator import EvaluationResult
from app.services.rule_service import AlertRule
from app.services.silence_service import SilenceService
from app.services.state_service import retire_alert_fingerprint

logger = get_logger("alert-engine.services.trigger")


class AlertTriggerService:
    """
    Service for converting evaluation results to alerts.

    Handles:
    - Fingerprint generation for deduplication
    - Duplicate alert suppression via Redis cache
    - Silence checking to suppress alerts during maintenance
    - AlertState record creation in database
    - AlertHistory logging for silenced alerts
    - Remediation action execution when alerts fire
    """

    TRIGGER_SUPPRESSION_KEY_PREFIX = "alert-engine:trigger-suppress"

    def __init__(
        self,
        session: AsyncSession,
        dedup: DeduplicationService,
        silence_service: Optional[SilenceService] = None,
    ):
        """
        Initialize the trigger service.

        Args:
            session: Async database session.
            dedup: DeduplicationService instance for duplicate detection.
            silence_service: Optional SilenceService for silence checking.
        """
        self.session = session
        self.dedup = dedup
        self.silence_service = silence_service or SilenceService(session)
        self._http_client: Optional[httpx.AsyncClient] = None

    @staticmethod
    def _is_container_key(value: str) -> bool:
        raw = (value or "").strip()
        if ":" not in raw:
            return False
        host_id, container_name = raw.split(":", 1)
        return bool(host_id.strip()) and bool(container_name.strip())

    @staticmethod
    def _normalize_lower_set(values: Any) -> set[str]:
        if not isinstance(values, list):
            return set()
        return {
            str(value or "").strip().lower()
            for value in values
            if str(value or "").strip()
        }

    def _suppression_key(self, organization_id: str, container_id: str) -> str:
        return f"{self.TRIGGER_SUPPRESSION_KEY_PREFIX}:{organization_id}:{container_id}"

    async def _is_trigger_suppressed(
        self,
        rule: AlertRule,
        labels: Dict[str, str],
    ) -> bool:
        """Return True when this alert should be dropped due to active suppression."""
        container_id = str(labels.get("container_key") or labels.get("container_id") or "").strip()
        if not self._is_container_key(container_id):
            return False

        await gatekeeper.ensure_initialized()
        gatekeeper_settings = gatekeeper.get_settings()
        if not gatekeeper_settings.get("trigger_suppression_enabled", False):
            return False

        suppression_rule_types = self._normalize_lower_set(
            gatekeeper_settings.get("trigger_suppression_rule_types", [])
        )
        if not suppression_rule_types:
            return False

        trigger_type = str(rule.trigger_type or "").strip().lower()
        applies_to_rule_type = (
            "all" in suppression_rule_types or trigger_type in suppression_rule_types
        )
        if not applies_to_rule_type:
            return False

        suppress_key = self._suppression_key(rule.organization_id, container_id)
        is_active = bool(await self.dedup.redis.exists(suppress_key))
        if is_active:
            logger.info(
                "Trigger suppressed for rule=%s container=%s (key=%s)",
                rule.id,
                container_id,
                suppress_key,
            )
        return is_active

    async def _activate_trigger_suppression(
        self,
        rule: AlertRule,
        container_id: str,
        action_results: List[Any],
        action_types_by_id: Dict[str, str],
    ) -> None:
        """Start suppression TTL when configured remediation actions succeed."""
        if not self._is_container_key(container_id):
            return

        await gatekeeper.ensure_initialized()
        gatekeeper_settings = gatekeeper.get_settings()
        if not gatekeeper_settings.get("trigger_suppression_enabled", False):
            return

        suppression_minutes = max(
            0,
            int(gatekeeper_settings.get("trigger_suppression_minutes", 0) or 0),
        )
        if suppression_minutes <= 0:
            return

        suppression_actions = self._normalize_lower_set(
            gatekeeper_settings.get("trigger_suppression_actions", [])
        )
        if not suppression_actions:
            return

        successful_actions: set[str] = set()
        for action_result in action_results:
            if not getattr(action_result, "success", False):
                continue
            action_id = str(getattr(action_result, "action_id", "") or "").strip()
            action_type = str(action_types_by_id.get(action_id, "") or "").strip().lower()
            if action_type:
                successful_actions.add(action_type)

        matched_actions = sorted(successful_actions.intersection(suppression_actions))
        if not matched_actions:
            return

        suppress_key = self._suppression_key(rule.organization_id, container_id)
        ttl_seconds = suppression_minutes * 60
        await self.dedup.redis.set(suppress_key, ",".join(matched_actions), ex=ttl_seconds)
        logger.info(
            "Activated trigger suppression for container=%s rule=%s actions=%s ttl=%ss",
            container_id,
            rule.id,
            ",".join(matched_actions),
            ttl_seconds,
        )

    async def trigger_alert(
        self,
        result: EvaluationResult,
        rule: AlertRule,
    ) -> Optional[str]:
        """
        Create an alert from an evaluation result if not a duplicate or silenced.

        The processing pipeline is:
        1. Check if rule triggered
        2. Generate fingerprint and check deduplication
        3. Check if alert is silenced (log but don't fire)
        4. Create AlertState if not silenced

        Args:
            result: The evaluation result from RuleEvaluator.
            rule: The AlertRule that was evaluated.

        Returns:
            The alert_id if a new alert was created, None if suppressed/silenced.
        """
        if not result.triggered:
            # Rule didn't trigger - no alert to create
            return None

        # Build labels from rule labels + evaluation context
        labels = self._build_labels(rule, result)

        # Skip alert creation if this container is in a post-remediation suppression window.
        if await self._is_trigger_suppressed(rule, labels):
            return None

        # Generate fingerprint for deduplication
        fingerprint = generate_fingerprint(
            rule_id=rule.id,
            scope=rule.scope_type,
            labels=labels,
        )

        # Check deduplication - atomic check-and-set
        is_duplicate = await self.dedup.check_and_record(fingerprint)

        if is_duplicate:
            logger.debug(
                "Duplicate alert suppressed for rule %s (fingerprint: %s)",
                rule.id,
                fingerprint,
            )
            return None

        # Check silencing - alert is logged but does not fire
        is_silenced = await self.silence_service.is_silenced(
            rule.organization_id, labels
        )

        if is_silenced:
            logger.info(
                "Alert for rule %s is silenced, logging but not firing",
                rule.id,
            )
            await self._log_silenced_alert(result, rule, labels)
            return None

        # Legacy acknowledged alerts may still hold the active fingerprint.
        # Retire the old row before we try to create a fresh firing alert.
        acknowledged_result = await self.session.execute(
            select(AlertState).where(
                AlertState.fingerprint == fingerprint,
                AlertState.status == "acknowledged",
                AlertState.organization_id == rule.organization_id,
            )
        )
        acknowledged_alert = acknowledged_result.scalar_one_or_none()
        if acknowledged_alert and retire_alert_fingerprint(acknowledged_alert):
            await self.session.commit()

        # Build stacking key for dedup grouping: rule_id:host_id:container_name
        stacking_target = labels.get("container_key") or labels.get("container_id", "")
        if not stacking_target:
            stacking_target = "global"
        stacking_key = f"{rule.id}:{stacking_target}"
        now = datetime.now(timezone.utc)

        # Check for existing firing alert with the same stacking key
        existing_result = await self.session.execute(
            select(AlertState).where(
                AlertState.stacking_key == stacking_key,
                AlertState.status == "firing",
                AlertState.organization_id == rule.organization_id,
            )
        )
        existing_alert = existing_result.scalar_one_or_none()

        if existing_alert:
            # STACKING PATH: Increment count and update last_seen
            existing_alert.count += 1
            existing_alert.last_seen = now
            existing_alert.updated_at = now
            existing_alert.last_trigger_context = result.context
            existing_alert.value = result.value
            self.session.add(
                self._build_history_entry(
                    result=result,
                    rule=rule,
                    labels=labels,
                    status="triggered",
                    triggered_at=now,
                    alert_id=existing_alert.id,
                    stacked=True,
                    occurrence_count=existing_alert.count,
                )
            )

            await self.session.commit()
            await self.session.refresh(existing_alert)

            logger.info(
                "Alert stacked: id=%s, rule=%s, count=%d",
                existing_alert.id,
                rule.id,
                existing_alert.count,
            )

            # Publish stacking event for real-time UI update.
            # Do not re-dispatch to the alert stream; this is the same alert.
            try:
                await publish_alert_stacked(
                    alert_id=existing_alert.id,
                    count=existing_alert.count,
                    last_seen=now,
                    organization_id=rule.organization_id,
                )
            except Exception as e:
                logger.warning(
                    "Alert stacked publish error (non-blocking): alert_id=%s, error=%s",
                    existing_alert.id,
                    str(e),
                )

            # A post-dedup stack event is still a fresh trigger episode.
            # Re-run remediation actions here; the gatekeeper applies cooldowns.
            notification_targets = await self._collect_notification_targets(rule.id)
            await self._execute_remediation_actions(
                rule,
                result,
                labels,
                notification_targets=notification_targets,
                notification_dispatched=False,
            )

            return existing_alert.id

        # NEW ALERT PATH: Create AlertState record with stacking fields
        alert_id = uuid.uuid4().hex

        alert_state = AlertState(
            id=alert_id,
            rule_id=rule.id,
            fingerprint=fingerprint,
            status="firing",
            severity=rule.severity,
            labels=labels,
            annotations=self._build_annotations(rule, result),
            value=result.value,
            started_at=now,
            updated_at=now,
            organization_id=rule.organization_id,
            stacking_key=stacking_key,
            count=1,
            first_seen=now,
            last_seen=now,
            last_trigger_context=result.context,
        )

        self.session.add(alert_state)
        self.session.add(
            self._build_history_entry(
                result=result,
                rule=rule,
                labels=labels,
                status="triggered",
                triggered_at=now,
                alert_id=alert_id,
                stacked=False,
                occurrence_count=1,
            )
        )
        await self.session.commit()
        await self.session.refresh(alert_state)

        logger.info(
            "Alert created: id=%s, rule=%s, severity=%s, fingerprint=%s",
            alert_id,
            rule.id,
            rule.severity,
            fingerprint,
        )

        # Dispatch alert to Redis Stream for notifier consumption
        # Done AFTER commit so notifier can query alert if needed
        # Non-blocking: log warning on failure but continue (at-least-once)
        notification_targets = await self._collect_notification_targets(rule.id)
        notification_dispatched = False
        try:
            alert_payload = build_alert_payload(
                alert_id=alert_id,
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                fingerprint=fingerprint,
                labels=labels,
                annotations=alert_state.annotations,
                value=result.value,
                triggered_at=now,
                organization_id=rule.organization_id,
            )
            if any(notification_targets.values()):
                alert_payload["notification_targets"] = notification_targets
            message_id = await publish_alert(alert_payload)
            if message_id:
                notification_dispatched = True
                logger.info(
                    "Alert dispatched to stream: alert_id=%s, message_id=%s",
                    alert_id,
                    message_id,
                )
            else:
                logger.warning(
                    "Alert dispatch failed (will retry via stream recovery): alert_id=%s",
                    alert_id,
                )
        except Exception as e:
            logger.warning(
                "Alert dispatch error (non-blocking): alert_id=%s, error=%s",
                alert_id,
                str(e),
            )

        # Publish self-contained alert:fired event to Redis pub/sub
        # Central subscribes to unicron:alert-updates and relays to browsers
        # Non-blocking: log warning on failure but continue
        try:
            await publish_alert_fired(
                alert_id=alert_id,
                rule_id=rule.id,
                rule_name=rule.name,
                rule_type=rule.trigger_type,
                container_name=labels.get("container_name", ""),
                host_id=labels.get("host_id", ""),
                severity=rule.severity,
                message=result.message,
                trigger_value=str(result.value) if result.value is not None else "",
                threshold=str(result.context.get("threshold", "")) if result.context else "",
                status="firing",
                started_at=now,
                updated_at=now,
                organization_id=rule.organization_id,
            )
            logger.debug(
                "Published alert:fired event: alert_id=%s, rule=%s",
                alert_id,
                rule.name,
            )
        except Exception as e:
            logger.warning(
                "Alert publish error (non-blocking): alert_id=%s, error=%s",
                alert_id,
                str(e),
            )

        # Execute remediation actions if configured
        # Done AFTER notification dispatch so alerts are visible even if actions fail
        # Non-blocking: log error on failure but do not affect alert creation
        await self._execute_remediation_actions(
            rule,
            result,
            labels,
            notification_targets=notification_targets,
            notification_dispatched=notification_dispatched,
        )

        return alert_id

    async def _log_silenced_alert(
        self,
        result: EvaluationResult,
        rule: AlertRule,
        labels: Dict[str, str],
    ) -> None:
        """
        Log a silenced alert to AlertHistory.

        Creates a history record with status='silenced' but does NOT
        create an AlertState (no firing alert).

        Args:
            result: The evaluation result from RuleEvaluator.
            rule: The AlertRule that was evaluated.
        """
        now = datetime.now(timezone.utc)
        history = self._build_history_entry(
            result=result,
            rule=rule,
            labels=labels,
            status="silenced",
            triggered_at=now,
        )

        self.session.add(history)
        await self.session.commit()

        logger.debug(
            "Silenced alert logged to history: rule=%s, rule_name=%s",
            rule.id,
            rule.name,
        )

    def _build_history_entry(
        self,
        *,
        result: EvaluationResult,
        rule: AlertRule,
        labels: Dict[str, str],
        status: str,
        triggered_at: datetime,
        alert_id: str | None = None,
        stacked: bool | None = None,
        occurrence_count: int | None = None,
    ) -> AlertHistory:
        """Build a normalized AlertHistory row for trigger lifecycle events."""
        context: Dict[str, Any] = {}
        if isinstance(result.context, dict):
            context.update(result.context)
        if labels:
            context.setdefault("labels", dict(labels))
        if alert_id:
            context.setdefault("alert_id", alert_id)
        if stacked is not None:
            context.setdefault("stacked", bool(stacked))
        if occurrence_count is not None:
            context.setdefault("occurrence_count", int(occurrence_count))

        return AlertHistory(
            id=uuid.uuid4().hex,
            rule_id=rule.id,
            rule_name=rule.name,
            severity=rule.severity,
            message=result.message or "",
            context=context,
            status=status,
            triggered_at=triggered_at,
            organization_id=rule.organization_id,
        )

    def _build_labels(
        self,
        rule: AlertRule,
        result: EvaluationResult,
    ) -> Dict[str, str]:
        """
        Build alert labels from rule and evaluation context.

        Args:
            rule: The alert rule.
            result: The evaluation result.

        Returns:
            Combined labels dictionary.
        """
        labels: Dict[str, str] = {}

        # Start with rule's static labels
        if rule.labels:
            labels.update(rule.labels)

        # Add standard labels
        labels["rule_name"] = rule.name
        labels["trigger_type"] = rule.trigger_type
        labels["scope_type"] = rule.scope_type

        # Add context from evaluation result
        context = result.context or {}

        raw_container_key = str(context.get("container_key", "") or "")
        raw_container_id = str(context.get("container_id", "") or "")
        host_id = str(context.get("host_id", "") or "")
        container_name = str(context.get("container_name", "") or "")

        composite_source = ""
        if self._is_container_key(raw_container_key):
            composite_source = raw_container_key
        elif self._is_container_key(raw_container_id):
            composite_source = raw_container_id

        if composite_source:
            parsed_host_id, parsed_container_name = composite_source.split(":", 1)
            host_id = host_id or parsed_host_id
            container_name = container_name or parsed_container_name

        container_key = ""
        if host_id and container_name:
            container_key = f"{host_id}:{container_name}"
        elif self._is_container_key(composite_source):
            container_key = composite_source

        if container_key:
            # Canonical identity for alert scope and action routing.
            labels["container_id"] = container_key
            labels["container_key"] = container_key

        if container_name:
            labels["container_name"] = container_name

        if host_id:
            labels["host_id"] = host_id

        # Container IDs from container counts
        if "container_counts" in context and context["container_counts"]:
            containers = list(context["container_counts"].keys())
            if containers:
                labels["containers"] = ",".join(sorted(containers))

        return labels

    def _build_annotations(
        self,
        rule: AlertRule,
        result: EvaluationResult,
    ) -> Dict[str, Any]:
        """
        Build alert annotations from rule and evaluation context.

        Annotations contain additional context for display/notification
        but are not used for deduplication.

        Args:
            rule: The alert rule.
            result: The evaluation result.

        Returns:
            Combined annotations dictionary.
        """
        annotations: Dict[str, Any] = {}

        # Start with rule's static annotations
        if rule.annotations:
            annotations.update(rule.annotations)

        # Add evaluation message
        annotations["message"] = result.message

        # Add rule description if present
        if rule.description:
            annotations["description"] = rule.description

        # Add evaluation context (for debugging/investigation)
        if result.context:
            annotations["evaluation_context"] = result.context

        # Add timing
        annotations["evaluated_at"] = result.evaluated_at.isoformat()

        return annotations

    async def _collect_notification_targets(self, rule_id: str) -> Dict[str, List[str]]:
        """Collect explicit notify targets from rule actions."""
        actions = await action_service.get_actions_for_rule(
            self.session,
            rule_id,
            enabled_only=True,
        )

        targets: Dict[str, List[str]] = {
            "channel_ids": [],
            "group_ids": [],
            "preset_ids": [],
        }
        seen: Dict[str, set[str]] = {key: set() for key in targets}

        def add_targets(target_key: str, values: Any) -> None:
            if not isinstance(values, list):
                return
            for raw_value in values:
                target_id = str(raw_value or "").strip()
                if not target_id or target_id in seen[target_key]:
                    continue
                targets[target_key].append(target_id)
                seen[target_key].add(target_id)

        for action in actions:
            action_type = str(action.action_type or "").strip().lower()
            if action_type != "notify":
                continue

            action_config = action.action_config or {}
            add_targets("channel_ids", action_config.get("channel_ids"))
            add_targets("group_ids", action_config.get("group_ids"))
            add_targets("preset_ids", action_config.get("preset_ids"))

        return targets

    async def _execute_remediation_actions(
        self,
        rule: AlertRule,
        result: EvaluationResult,
        labels: Dict[str, str],
        notification_targets: Optional[Dict[str, List[str]]] = None,
        notification_dispatched: bool = False,
    ) -> None:
        """
        Execute remediation actions for a triggered alert.

        Actions are executed non-blocking - failures are logged but don't
        affect alert creation. Each action goes through gatekeeper preflight.

        Args:
            rule: The alert rule that fired.
            result: The evaluation result.
            labels: Built labels from the alert.
        """
        # Import here to avoid circular imports
        from app.services.action_executor import action_executor
        from app.services.action_service import action_service

        # Get container_id from evaluation context
        context = result.context or {}
        container_id = ""
        context_container_key = str(context.get("container_key", "") or "").strip()
        context_container_id = str(context.get("container_id", "") or "").strip()
        if self._is_container_key(context_container_key):
            container_id = context_container_key
        elif self._is_container_key(context_container_id):
            container_id = context_container_id

        if not container_id:
            # Check if there's a single container in container_counts
            container_counts = context.get("container_counts", {})
            if len(container_counts) == 1:
                candidate = str(list(container_counts.keys())[0])
                if self._is_container_key(candidate):
                    container_id = candidate

        if not container_id:
            label_candidate = str(
                labels.get("container_key") or labels.get("container_id") or ""
            ).strip()
            if self._is_container_key(label_candidate):
                container_id = label_candidate

        if not container_id:
            logger.debug(
                "No canonical container key in context for rule %s, skipping actions",
                rule.id,
            )
            return

        # Check if rule has any actions configured
        actions = await action_service.get_actions_for_rule(
            self.session, rule.id, enabled_only=True
        )
        action_types_by_id = {
            str(action.id): str(action.action_type or "").strip().lower()
            for action in actions
            if getattr(action, "id", None)
        }

        if not actions:
            logger.debug("No actions configured for rule %s", rule.id)
            return

        # Get current container state from Central
        try:
            container_state = await self._get_container_state(container_id)
        except Exception as e:
            logger.error(
                "Failed to get container state for %s: %s",
                container_id,
                str(e),
            )
            # Default to unknown - gatekeeper will handle appropriately
            container_state = "unknown"

        # Build action context from evaluation
        alert_context = {
            **context,
            "container_id": container_id,
            "labels": labels,
            "rule_id": rule.id,
            "rule_name": rule.name,
            "notification_targets": notification_targets or {},
            "notification_dispatched": notification_dispatched,
        }

        # Execute actions
        try:
            action_results = await action_executor.execute_actions(
                session=self.session,
                rule=rule,
                alert_context=alert_context,
                container_id=container_id,
                container_state=container_state,
            )

            # Log summary
            if action_results:
                await self._activate_trigger_suppression(
                    rule=rule,
                    container_id=container_id,
                    action_results=action_results,
                    action_types_by_id=action_types_by_id,
                )

                success_count = sum(1 for r in action_results if r.success)
                blocked_count = sum(1 for r in action_results if r.blocked)
                failed_count = sum(
                    1 for r in action_results if not r.success and not r.blocked
                )
                logger.info(
                    "Action execution for rule %s: %d succeeded, %d blocked, %d failed",
                    rule.id,
                    success_count,
                    blocked_count,
                    failed_count,
                )

        except Exception as e:
            logger.error(
                "Action execution failed for rule %s: %s",
                rule.id,
                str(e),
                exc_info=True,
            )

    async def _get_container_state(self, container_id: str) -> str:
        """
        Get current container state from Central.

        Args:
            container_id: Canonical container key host_id:container_name.

        Returns:
            Container state string (running, stopped, exited, etc.).
            Returns "unknown" on any failure (gatekeeper handles unknown gracefully).
        """
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=15.0,
                headers={"X-Internal-Secret": settings.CENTRAL_INTERNAL_SECRET},
            )

        # URL-encode container_id (composite keys like "local:nginx" contain colons)
        encoded_id = urllib.parse.quote(container_id, safe="")

        try:
            response = await self._http_client.get(
                f"{settings.CENTRAL_URL}/internal/containers/{encoded_id}/state",
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("state", "unknown")
            elif response.status_code == 404:
                logger.warning("Container %s not found in Central", container_id)
                return "unknown"
            else:
                logger.warning(
                    "Unexpected status %d from container state endpoint for %s",
                    response.status_code,
                    container_id,
                )
                return "unknown"
        except Exception as e:
            logger.warning(
                "Failed to get container state for %s: %s",
                container_id,
                str(e),
            )
            return "unknown"


__all__ = ["AlertTriggerService"]
