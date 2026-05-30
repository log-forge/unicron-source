"""Rule evaluation service for alert-engine.

Evaluates alert rules against log data from VictoriaLogs and returns
match results with context.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.core.redis import get_redis
from app.services.container_registry import get_container_registry
from app.services.rule_service import AlertRule
from app.services.victoria_client import VictoriaLogsClient, victoria_logs_client
from app.services.victoria_metrics_client import (
    VictoriaMetricsClient,
    victoria_metrics_client,
)

logger = get_logger("alert-engine.services.evaluator")


@dataclass
class EvaluationResult:
    """Result of evaluating an alert rule."""

    rule_id: str
    triggered: bool
    value: Optional[str] = None
    message: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class RuleEvaluator:
    """
    Evaluates alert rules against log data.

    Supports all four trigger types:
    - threshold: Compare metric value against threshold
    - keyword: Check for pattern matches in logs
    - rate: Check log rate against limit
    - absence: Check for absence of expected logs
    """

    def __init__(
        self,
        victoria_client: Optional[VictoriaLogsClient] = None,
        metrics_client: Optional[VictoriaMetricsClient] = None,
    ):
        """
        Initialize the evaluator.

        Args:
            victoria_client: VictoriaLogs client instance. Uses singleton if not provided.
            metrics_client: VictoriaMetrics client instance. Uses singleton if not provided.
        """
        self.victoria_client = victoria_client or victoria_logs_client
        self.metrics_client = metrics_client or victoria_metrics_client

    def _window_minutes(self, config: Dict[str, Any], default: int = 5) -> int:
        """Normalize window fields to minutes for VictoriaLogs queries."""
        raw_minutes = config.get("window_minutes")
        if raw_minutes is not None:
            try:
                return max(1, int(raw_minutes))
            except (TypeError, ValueError):
                pass

        raw_seconds = config.get("window_seconds")
        if raw_seconds is None:
            raw_seconds = config.get("duration_seconds")
        if raw_seconds is not None:
            try:
                seconds = max(1, int(raw_seconds))
                return max(1, (seconds + 59) // 60)
            except (TypeError, ValueError):
                pass

        return default

    @staticmethod
    def _is_container_key(value: str) -> bool:
        raw = (value or "").strip()
        if ":" not in raw:
            return False
        host_id, container_name = raw.split(":", 1)
        return bool(host_id.strip()) and bool(container_name.strip())

    @staticmethod
    def _split_container_key(container_key: str) -> tuple[str, str]:
        raw = (container_key or "").strip()
        if ":" not in raw:
            return "", ""
        host_id, container_name = raw.split(":", 1)
        return host_id.strip(), container_name.strip()

    def _container_context(self, container_key: str) -> Dict[str, str]:
        host_id, container_name = self._split_container_key(container_key)
        context: Dict[str, str] = {
            "container_id": container_key,
            "container_key": container_key,
        }
        if host_id:
            context["host_id"] = host_id
        if container_name:
            context["container_name"] = container_name
        return context

    def _container_context_from_log_row(self, row: Any) -> Dict[str, str]:
        """Extract canonical container context from a VictoriaLogs row."""
        container_key = str(getattr(row, "container_key", "") or "").strip()
        host_id = str(getattr(row, "herald_id", "") or "").strip()
        container_name = str(getattr(row, "container_name", "") or "").strip()

        if self._is_container_key(container_key):
            parsed_host, parsed_name = self._split_container_key(container_key)
            host_id = host_id or parsed_host
            container_name = container_name or parsed_name
        elif host_id and container_name:
            container_key = f"{host_id}:{container_name}"

        if not self._is_container_key(container_key):
            return {}
        return self._container_context(container_key)

    def _metrics_scope_labels(self, container_key: str) -> str:
        host_id, container_name = self._split_container_key(container_key)
        esc_host = host_id.replace("\\", "\\\\").replace('"', '\\"')
        esc_name = container_name.replace("\\", "\\\\").replace('"', '\\"')
        esc_key = container_key.replace("\\", "\\\\").replace('"', '\\"')
        if host_id and container_name:
            return f'herald_id="{esc_host}",container_name="{esc_name}"'
        return f'container_key="{esc_key}"'

    async def evaluate_rule(self, rule: AlertRule) -> EvaluationResult:
        """
        Evaluate a single alert rule.

        Args:
            rule: The AlertRule to evaluate.

        Returns:
            EvaluationResult with match status and context.
        """
        try:
            trigger_type = rule.trigger_type.lower()
            trigger_config = rule.trigger_config

            # Resolve scope to container IDs
            container_ids = await self._resolve_scope(rule)

            if trigger_type == "threshold":
                return await self._evaluate_threshold(rule, trigger_config, container_ids)
            elif trigger_type == "keyword":
                return await self._evaluate_keyword(rule, trigger_config, container_ids)
            elif trigger_type == "rate":
                return await self._evaluate_rate(rule, trigger_config, container_ids)
            elif trigger_type == "absence":
                return await self._evaluate_absence(rule, trigger_config, container_ids)
            else:
                return EvaluationResult(
                    rule_id=rule.id,
                    triggered=False,
                    message=f"Unknown trigger type: {trigger_type}",
                )

        except Exception as e:
            logger.exception("Error evaluating rule %s: %s", rule.id, e)
            return EvaluationResult(
                rule_id=rule.id,
                triggered=False,
                message=f"Evaluation error: {str(e)}",
                context={"error": str(e)},
            )

    async def _resolve_scope(self, rule: AlertRule) -> List[str]:
        """
        Resolve rule scope to container IDs.

        Args:
            rule: The alert rule with scope configuration.

        Returns:
            List of container IDs to evaluate against.
            Empty list means evaluate globally (no container filter).
        """
        scope_type = rule.scope_type.lower()
        scope_targets = rule.scope_targets or []

        if scope_type == "global":
            # No container filter - evaluate across all containers
            return []

        elif scope_type == "container":
            # Direct container targets must be canonical host_id:container_name.
            valid_targets = [
                target for target in scope_targets if self._is_container_key(target)
            ]
            if len(valid_targets) != len(scope_targets):
                logger.warning(
                    "Rule %s has invalid container scope targets; ignoring malformed entries",
                    rule.id,
                )
            return valid_targets

        elif scope_type == "group":
            # Expand group to container IDs via Redis cache
            if not scope_targets:
                logger.debug("Group scope has no targets for rule %s", rule.id)
                return []

            group_id = scope_targets[0]
            try:
                redis_client = await get_redis()
                cache_key = f"alert-engine:group-containers:{group_id}"

                # Redis Set contains composite keys like {host_id}:{name}
                container_ids = await redis_client.smembers(cache_key)

                if container_ids:
                    # Convert from bytes to strings if needed
                    decoded = [c.decode() if isinstance(c, bytes) else c for c in container_ids]
                    result = [target for target in decoded if self._is_container_key(target)]
                    logger.debug(
                        "Group scope expanded for rule %s: %d containers",
                        rule.id,
                        len(result),
                    )
                    return result
                else:
                    logger.debug(
                        "Group cache miss for rule %s (group_id=%s), falling back to global scope",
                        rule.id,
                        group_id,
                    )
                    return []

            except Exception as e:
                logger.warning(
                    "Failed to expand group scope for rule %s: %s, falling back to global scope",
                    rule.id,
                    e,
                )
                return []

        elif scope_type == "herald":
            # Get containers from herald host via ContainerRegistry
            if not scope_targets:
                logger.debug("Herald scope has no targets for rule %s", rule.id)
                return []

            herald_id = scope_targets[0]
            try:
                registry = get_container_registry()
                containers = await registry.list_containers(host_id=herald_id)

                if containers:
                    # Build composite keys: {host_id}:{name}
                    container_ids = [
                        f"{c.get('host_id', '')}:{c.get('name', '')}"
                        for c in containers
                        if c.get("host_id") and c.get("name")
                    ]
                    logger.debug(
                        "Herald scope expanded for rule %s: %d containers on host %s",
                        rule.id,
                        len(container_ids),
                        herald_id,
                    )
                    return container_ids
                else:
                    logger.debug(
                        "No containers found for herald %s (rule %s), falling back to global scope",
                        herald_id,
                        rule.id,
                    )
                    return []

            except Exception as e:
                logger.warning(
                    "Failed to expand herald scope for rule %s: %s, falling back to global scope",
                    rule.id,
                    e,
                )
                return []

        else:
            logger.warning("Unknown scope type '%s' for rule %s", scope_type, rule.id)
            return []

    async def _evaluate_threshold(
        self,
        rule: AlertRule,
        config: Dict[str, Any],
        container_ids: List[str],
    ) -> EvaluationResult:
        """
        Evaluate a threshold trigger.

        Config fields:
        - metric_expr: Optional[str] - PromQL expression (queries VictoriaMetrics if provided)
        - metric: str - metric name (used with log count fallback)
        - operator: str - comparison operator (gt, gte, lt, lte, eq)
        - threshold: float - threshold value
        - window_minutes: int - time window
        - for_duration: Optional[int] - seconds value must persist (not yet implemented)
        """
        metric_expr = config.get("metric_expr")
        metric = config.get("metric", "log_count")
        operator = config.get("operator", "gt")
        threshold = float(config.get("threshold", config.get("value", 0)))
        window_minutes = self._window_minutes(config, default=5)

        # Track metric source for context
        metric_source = "victoria_metrics" if metric_expr else "log_count"
        queried_metric_value: Optional[float] = None

        if metric_expr:
            # Query VictoriaMetrics for metric value
            expr = metric_expr

            # Inject container filter if scope resolves to a single target.
            if container_ids and len(container_ids) == 1:
                container_key = container_ids[0]
                scope_labels = self._metrics_scope_labels(container_key)
                # Check if expression already has selectors
                if "{" in expr:
                    expr = expr.replace("}", f", {scope_labels}}}")
                else:
                    # Add selector to metric name (before any aggregation)
                    # Find first non-alphanumeric/underscore character or end
                    import re
                    match = re.match(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)', expr)
                    if match:
                        metric_name = match.group(1)
                        rest = expr[len(metric_name):]
                        expr = f"{metric_name}{{{scope_labels}}}{rest}"

            try:
                response = await self.metrics_client.query_instant(expr)
                queried_metric_value = self.metrics_client.extract_scalar_value(response)

                if queried_metric_value is None:
                    # Try extract_latest_value for multi-series results
                    queried_metric_value = self.metrics_client.extract_latest_value(response)

                if queried_metric_value is not None:
                    triggered = self._compare(queried_metric_value, operator, threshold)
                    context: Dict[str, Any] = {
                        "metric_expr": metric_expr,
                        "queried_expr": expr,
                        "queried_metric_value": queried_metric_value,
                        "operator": operator,
                        "threshold": threshold,
                        "metric_source": metric_source,
                        "container_ids": container_ids if container_ids else None,
                    }
                    if len(container_ids) == 1:
                        context.update(self._container_context(container_ids[0]))
                    return EvaluationResult(
                        rule_id=rule.id,
                        triggered=triggered,
                        value=str(queried_metric_value),
                        message=(
                            f"Metric '{metric_expr}' value {queried_metric_value} {operator} {threshold}: "
                            f"{'triggered' if triggered else 'not triggered'}"
                        ),
                        context=context,
                    )
                else:
                    # No data returned from VictoriaMetrics
                    logger.warning(
                        "VictoriaMetrics query returned no data for rule %s: %s",
                        rule.id,
                        expr,
                    )
                    return EvaluationResult(
                        rule_id=rule.id,
                        triggered=False,
                        message=f"No metric data returned for expression: {expr}",
                        context={
                            "metric_expr": metric_expr,
                            "queried_expr": expr,
                            "queried_metric_value": None,
                            "metric_source": metric_source,
                            "error": "no_data",
                        },
                    )

            except Exception as e:
                logger.error(
                    "VictoriaMetrics query failed for rule %s: %s",
                    rule.id,
                    e,
                )
                return EvaluationResult(
                    rule_id=rule.id,
                    triggered=False,
                    message=f"Metric query failed: {str(e)}",
                    context={
                        "metric_expr": metric_expr,
                        "metric_source": metric_source,
                        "error": str(e),
                    },
                )

        # Fallback: Use log count as the metric (backward compatible)
        total_count = 0
        container_counts: Dict[str, int] = {}

        if container_ids:
            for container_id in container_ids:
                count = await self.victoria_client.count_logs_matching(
                    container_id=container_id,
                    pattern="",  # Count all logs
                    window_minutes=window_minutes,
                )
                container_counts[container_id] = count
                total_count += count
        else:
            # Global scope - query without container filter
            result = await self.victoria_client.query(
                query="*",
                limit=10000,
                start=f"-{window_minutes}m",
            )
            total_count = result.count

        # Compare against threshold
        triggered = self._compare(total_count, operator, threshold)

        context: Dict[str, Any] = {
            "metric": metric,
            "value": total_count,
            "operator": operator,
            "threshold": threshold,
            "window_minutes": window_minutes,
            "metric_source": metric_source,
            "container_counts": container_counts if container_ids else None,
        }
        if len(container_ids) == 1:
            context.update(self._container_context(container_ids[0]))

        return EvaluationResult(
            rule_id=rule.id,
            triggered=triggered,
            value=str(total_count),
            message=(
                f"Metric '{metric}' value {total_count} {operator} {threshold}: "
                f"{'triggered' if triggered else 'not triggered'}"
            ),
            context=context,
        )

    def _compare(self, value: float, operator: str, threshold: float) -> bool:
        """Compare value against threshold using operator."""
        ops = {
            "gt": value > threshold,
            "gte": value >= threshold,
            "lt": value < threshold,
            "lte": value <= threshold,
            "eq": value == threshold,
            "ne": value != threshold,
        }
        return ops.get(operator.lower(), False)

    async def _evaluate_keyword(
        self,
        rule: AlertRule,
        config: Dict[str, Any],
        container_ids: List[str],
    ) -> EvaluationResult:
        """
        Evaluate a keyword trigger.

        Config fields:
        - pattern: str - keyword or regex pattern to match
        - is_regex: bool - whether pattern is a regex
        - case_sensitive: bool - case-sensitive matching
        - window_minutes: int - time window
        """
        pattern = config.get("pattern", "")
        is_regex = config.get("is_regex", False)
        case_sensitive = config.get("case_sensitive", False)
        window_minutes = self._window_minutes(config, default=5)

        if not pattern:
            return EvaluationResult(
                rule_id=rule.id,
                triggered=False,
                message="No pattern specified for keyword trigger",
            )

        matched = False
        matching_log = None
        matched_container = None

        if container_ids:
            # Check each container
            for container_id in container_ids:
                has_match, log_row = await self.victoria_client.check_keyword_match(
                    container_id=container_id,
                    pattern=pattern,
                    is_regex=is_regex,
                    case_sensitive=case_sensitive,
                    window_minutes=window_minutes,
                )
                if has_match:
                    matched = True
                    matching_log = log_row
                    matched_container = container_id
                    break
        else:
            # Global scope - check without container filter
            # Build query similar to victoria_client.check_keyword_match
            if is_regex:
                query = f'_msg:~"{pattern}"'
            elif case_sensitive:
                query = f'_msg:"{pattern}"'
            else:
                query = f'_msg:~"(?i){pattern}"'

            result = await self.victoria_client.query(
                query=query,
                limit=1,
                start=f"-{window_minutes}m",
            )
            if result.count > 0:
                matched = True
                matching_log = result.rows[0]

        context: Dict[str, Any] = {
            "pattern": pattern,
            "is_regex": is_regex,
            "case_sensitive": case_sensitive,
            "window_minutes": window_minutes,
        }

        if matching_log:
            context["matching_log"] = {
                "message": matching_log.msg,
                "timestamp": matching_log.time,
            }
            if matched_container:
                context.update(self._container_context(matched_container))
            else:
                context.update(self._container_context_from_log_row(matching_log))

        return EvaluationResult(
            rule_id=rule.id,
            triggered=matched,
            value=matching_log.msg if matching_log else None,
            message=(
                f"Pattern '{pattern}' {'found' if matched else 'not found'} "
                f"in last {window_minutes} minutes"
            ),
            context=context,
        )

    async def _evaluate_rate(
        self,
        rule: AlertRule,
        config: Dict[str, Any],
        container_ids: List[str],
    ) -> EvaluationResult:
        """
        Evaluate a rate trigger.

        Config fields:
        - pattern: str - pattern to count
        - rate_limit: int - maximum allowed count
        - window_minutes: int - time window
        """
        pattern = config.get("pattern", "")
        rate_limit = int(config.get("threshold", config.get("rate_limit", 100)))
        window_minutes = self._window_minutes(config, default=5)

        total_count = 0
        container_counts: Dict[str, int] = {}

        if container_ids:
            for container_id in container_ids:
                count = await self.victoria_client.count_logs_matching(
                    container_id=container_id,
                    pattern=pattern,
                    window_minutes=window_minutes,
                )
                container_counts[container_id] = count
                total_count += count
        else:
            # Global scope
            if pattern:
                escaped = pattern.replace('"', '\\"')
                query = f'_msg:"{escaped}"'
            else:
                query = "*"

            result = await self.victoria_client.query(
                query=query,
                limit=10000,
                start=f"-{window_minutes}m",
            )
            total_count = result.count

        triggered = total_count > rate_limit

        context: Dict[str, Any] = {
            "pattern": pattern,
            "count": total_count,
            "threshold": rate_limit,
            "rate_limit": rate_limit,
            "window_minutes": window_minutes,
            "container_counts": container_counts if container_ids else None,
        }
        if len(container_ids) == 1:
            context.update(self._container_context(container_ids[0]))

        return EvaluationResult(
            rule_id=rule.id,
            triggered=triggered,
            value=str(total_count),
            message=(
                f"Log rate {total_count}/{window_minutes}min "
                f"{'exceeds' if triggered else 'within'} limit of {rate_limit}"
            ),
            context=context,
        )

    async def _evaluate_absence(
        self,
        rule: AlertRule,
        config: Dict[str, Any],
        container_ids: List[str],
    ) -> EvaluationResult:
        """
        Evaluate an absence trigger.

        Config fields:
        - expected_pattern: Optional[str] - expected log pattern
        - window_minutes: int - time window to check
        """
        expected_pattern = config.get("expected_pattern", config.get("pattern"))
        window_minutes = self._window_minutes(config, default=5)

        absent = False
        absent_container: Optional[str] = None
        checked_containers: List[str] = []

        if container_ids:
            # Check if logs are absent from any specified container
            for container_id in container_ids:
                is_absent = await self.victoria_client.check_absence(
                    container_id=container_id,
                    pattern=expected_pattern,
                    window_minutes=window_minutes,
                )
                checked_containers.append(container_id)
                if is_absent:
                    absent = True
                    absent_container = container_id
                    break
        else:
            # Global scope - check if ANY logs exist
            result = await self.victoria_client.query(
                query=f'_msg:"{expected_pattern}"' if expected_pattern else "*",
                limit=1,
                start=f"-{window_minutes}m",
            )
            absent = result.count == 0

        pattern_desc = f"pattern '{expected_pattern}'" if expected_pattern else "any logs"

        context: Dict[str, Any] = {
            "expected_pattern": expected_pattern,
            "window_minutes": window_minutes,
            "checked_containers": checked_containers if container_ids else None,
            "absent": absent,
        }
        if absent_container:
            context.update(self._container_context(absent_container))
        elif len(container_ids) == 1:
            context.update(self._container_context(container_ids[0]))

        return EvaluationResult(
            rule_id=rule.id,
            triggered=absent,
            value="absent" if absent else "present",
            message=(
                f"Expected {pattern_desc} {'missing' if absent else 'found'} "
                f"in last {window_minutes} minutes"
            ),
            context=context,
        )


__all__ = ["RuleEvaluator", "EvaluationResult"]
