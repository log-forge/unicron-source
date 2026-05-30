"""Rule matcher service for stream-time real-time evaluation."""

import asyncio
import hashlib
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select

from app.core.config import settings
from app.core.database import session_ctx
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.services.action_gatekeeper import gatekeeper
from app.services.container_registry import get_container_registry
from app.services.dedup import DEFAULT_DEDUP_WINDOW_SECONDS, DeduplicationService
from app.services.evaluator import EvaluationResult
from app.services.rule_service import AlertRule
from app.services.trigger_service import AlertTriggerService

logger = get_logger("alert-engine.services.rule_matcher")

# Index refresh interval fallback (seconds) when no invalidation signal arrives.
REFRESH_INTERVAL_SECONDS = 60
REALTIME_COUNTER_KEY_PREFIX = "alert-engine:realtime:counter"


class RuleMatcher:
    """
    Efficient rule matcher with O(1) container-to-rules lookup.

    Maintains an in-memory index that maps container composite keys
    (host_id:name) to applicable alert rules. Index can refresh from:
    - distributed invalidation version bumps (near-immediate)
    - periodic fallback refresh timer

    Scope expansion:
    - container: Direct mapping from scope_targets
    - herald: Expands to all containers on host via ContainerRegistry
    - group: Expands via Redis Set membership
    - global: Applies to all logs (separate list)
    """

    def __init__(self):
        """Initialize the rule matcher with empty index."""
        self._index: Dict[str, List[AlertRule]] = {}
        self._global_rules: List[AlertRule] = []
        self._last_refresh: float = 0.0
        self._last_seen_index_version: Optional[int] = None
        self._last_version_check: float = 0.0
        self._regex_cache: Dict[str, re.Pattern[str]] = {}

    async def maybe_refresh(self) -> None:
        """
        Refresh the rule index when invalidated or when timer elapses.

        Fast path:
        - poll distributed invalidation version at low frequency
        - rebuild immediately when version changes
        - otherwise rebuild on fallback refresh interval
        """
        version_changed = await self._check_index_version()
        now = time.time()
        if version_changed or (now - self._last_refresh >= REFRESH_INTERVAL_SECONDS):
            await self._refresh_index()

    def invalidate(self) -> None:
        """Mark the rule index as stale so the next maybe_refresh() rebuilds immediately.

        Called by rule CRUD routes after creating, updating, toggling, or deleting
        a rule. This is O(1) -- just resets the timestamp. The actual rebuild happens
        lazily on the next incoming log or container event via maybe_refresh().
        """
        self._last_refresh = 0.0
        logger.info("Rule index invalidated, will rebuild on next evaluation cycle")

    async def publish_invalidation(self, reason: str = "rule_mutation") -> None:
        """
        Publish distributed invalidation so all replicas refresh quickly.

        This keeps rule changes effective without waiting for the fallback
        refresh timer in horizontally scaled deployments.
        """
        self.invalidate()
        try:
            redis = await get_redis()
            version = await redis.incr(settings.REALTIME_RULE_INDEX_VERSION_KEY)
            self._last_seen_index_version = int(version)
            self._last_version_check = time.time()
            logger.info(
                "Published rule index invalidation (version=%s, reason=%s)",
                version,
                reason,
            )
        except Exception as e:
            logger.warning("Failed to publish rule index invalidation: %s", str(e))

    async def _check_index_version(self) -> bool:
        """
        Poll distributed index version and return True when changed.

        Version polling is throttled so hot log streams don't do a Redis read
        on every single message.
        """
        now = time.time()
        interval = max(0.25, float(settings.REALTIME_RULE_INDEX_VERSION_CHECK_SECONDS))
        if now - self._last_version_check < interval:
            return False
        self._last_version_check = now

        try:
            redis = await get_redis()
            raw = await redis.get(settings.REALTIME_RULE_INDEX_VERSION_KEY)
            version = int(raw) if raw is not None else 0
            if self._last_seen_index_version is None:
                self._last_seen_index_version = version
                return False
            if version != self._last_seen_index_version:
                self._last_seen_index_version = version
                self._last_refresh = 0.0
                logger.info(
                    "Detected rule index version change (%s), forcing refresh",
                    version,
                )
                return True
        except Exception as e:
            logger.debug("Rule index version check failed: %s", str(e))
        return False

    async def _refresh_index(self) -> None:
        """
        Rebuild the rule index from database.

        Fetches all enabled real-time rules and builds the container -> rules
        mapping for efficient lookup.
        """
        try:
            # Fetch all enabled stream-evaluated rules from database
            async with session_ctx() as session:
                stmt = select(AlertRule).where(
                    AlertRule.enabled == True,  # noqa: E712
                    AlertRule.trigger_type.in_(
                        ["keyword", "rate", "absence", "container_event"]
                    ),
                )
                result = await session.execute(stmt)
                rules = list(result.scalars().all())

            # Rebuild index
            await self._rebuild_index(rules)
            self._regex_cache = {}
            self._last_refresh = time.time()
            logger.debug("Rule index refreshed: %d rules indexed", len(rules))

        except Exception as e:
            logger.error("Failed to refresh rule index: %s", str(e))

    async def _rebuild_index(self, rules: List[AlertRule]) -> None:
        """
        Build container -> rules index from rule list.

        Args:
            rules: List of AlertRule objects to index.
        """
        # Clear existing index
        self._index = {}
        self._global_rules = []

        registry = get_container_registry()
        redis = await get_redis()

        for rule in rules:
            scope_type = rule.scope_type.lower()
            scope_targets = rule.scope_targets or []

            if scope_type == "global":
                # Global rules apply to all logs
                self._global_rules.append(rule)

            elif scope_type == "container":
                # Direct container targeting
                for target in scope_targets:
                    if target not in self._index:
                        self._index[target] = []
                    self._index[target].append(rule)

            elif scope_type == "herald":
                # Expand to all containers on host
                for herald_id in scope_targets:
                    try:
                        containers = await registry.list_containers(host_id=herald_id)
                        for container in containers:
                            # Build composite key: host_id:name
                            host_id = container.get("host_id", "")
                            name = container.get("name", "")
                            if host_id and name:
                                composite_key = f"{host_id}:{name}"
                                if composite_key not in self._index:
                                    self._index[composite_key] = []
                                self._index[composite_key].append(rule)
                    except Exception as e:
                        logger.warning(
                            "Failed to expand herald scope for rule %s, herald %s: %s",
                            rule.id,
                            herald_id,
                            str(e),
                        )

            elif scope_type == "group":
                # Expand group via Redis Set
                for group_id in scope_targets:
                    try:
                        group_key = f"alert-engine:group-containers:{group_id}"
                        members = await redis.smembers(group_key)
                        for member in members:
                            # Member is already a composite key
                            member_str = member if isinstance(member, str) else member.decode()
                            if member_str not in self._index:
                                self._index[member_str] = []
                            self._index[member_str].append(rule)
                    except Exception as e:
                        logger.warning(
                            "Failed to expand group scope for rule %s, group %s: %s",
                            rule.id,
                            group_id,
                            str(e),
                        )

        logger.info(
            "Rule index rebuilt: %d container mappings, %d global rules",
            len(self._index),
            len(self._global_rules),
        )

    def get_applicable_rules(self, container_key: str) -> List[AlertRule]:
        """
        Get rules that apply to a specific container.

        This is O(1) dictionary lookup + O(g) global rules.

        Args:
            container_key: Canonical key in format host_id:container_name.

        Returns:
            List of applicable AlertRule objects.
        """
        # Container-scoped rules + global rules
        container_rules = self._index.get(container_key, [])
        return container_rules + self._global_rules

    @staticmethod
    def _split_container_id(container_id: str) -> tuple[str, str]:
        if ":" not in container_id:
            return "", ""
        host_id, container_name = container_id.split(":", 1)
        return host_id.strip(), container_name.strip()

    @staticmethod
    def _normalize_container_id(log_data: Dict[str, Any]) -> str:
        container_id = str(log_data.get("container_id", "") or "").strip()
        if ":" in container_id:
            return container_id

        host_id = str(log_data.get("host_id", "") or "").strip()
        container_name = str(log_data.get("container_name", "") or "").strip()
        if host_id and container_name:
            container_id = f"{host_id}:{container_name}"
            log_data["container_id"] = container_id
            return container_id

        return ""

    @staticmethod
    def _normalize_container_key(event_data: Dict[str, Any]) -> str:
        """Resolve canonical container key from event payload shapes.

        Canonical identity is `host_id:container_name` (container_key). For
        resilience across in-flight rollouts, accept compatible shapes and
        normalize to canonical form.
        """
        container_key = str(event_data.get("container_key", "") or "").strip()
        if ":" in container_key:
            return container_key

        container_id = str(event_data.get("container_id", "") or "").strip()
        if ":" in container_id:
            return container_id

        host_id = str(event_data.get("host_id", "") or "").strip()
        container_name = str(event_data.get("container_name", "") or "").strip()
        if host_id and container_name:
            return f"{host_id}:{container_name}"

        return ""

    @staticmethod
    def _config_int(
        config: Dict[str, Any],
        keys: List[str],
        default: int,
        *,
        minimum: int = 1,
    ) -> int:
        for key in keys:
            raw = config.get(key)
            if raw is None:
                continue
            try:
                return max(minimum, int(raw))
            except (TypeError, ValueError):
                continue
        return max(minimum, int(default))

    @staticmethod
    def _parse_timestamp(value: Any) -> float:
        """Parse common timestamp shapes (epoch seconds/ms, ISO8601)."""
        now = time.time()
        if value is None:
            return now

        if isinstance(value, (int, float)):
            ts = float(value)
            # Treat very large values as milliseconds.
            if ts > 1_000_000_000_000:
                ts = ts / 1000.0
            return ts

        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return now
            try:
                return float(raw)
            except ValueError:
                pass
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.timestamp()
            except Exception:
                return now

        return now

    def _window_seconds(self, config: Dict[str, Any], default_seconds: int) -> int:
        raw_seconds = config.get("window_seconds")
        if raw_seconds is None:
            raw_seconds = config.get("duration_seconds")
        if raw_seconds is not None:
            try:
                seconds = int(raw_seconds)
                seconds = max(1, seconds)
                return min(seconds, settings.REALTIME_RULE_WINDOW_MAX_SECONDS)
            except (TypeError, ValueError):
                pass

        raw_minutes = config.get("window_minutes")
        if raw_minutes is not None:
            try:
                seconds = max(1, int(raw_minutes) * 60)
                return min(seconds, settings.REALTIME_RULE_WINDOW_MAX_SECONDS)
            except (TypeError, ValueError):
                pass

        return min(max(1, int(default_seconds)), settings.REALTIME_RULE_WINDOW_MAX_SECONDS)

    @staticmethod
    def _scope_counter_key(rule: AlertRule, container_id: str) -> str:
        scope = str(rule.scope_type or "").strip().lower()
        if scope == "global":
            return "global"
        return container_id or "unknown"

    @staticmethod
    def _counter_scope_hash(scope_key: str) -> str:
        return hashlib.sha1(scope_key.encode("utf-8")).hexdigest()[:16]

    async def _window_count(
        self,
        rule: AlertRule,
        *,
        trigger_type: str,
        counter_scope_key: str,
        event_timestamp: float,
        window_seconds: int,
    ) -> int:
        """
        Increment and read sliding-window count using bucketed Redis counters.
        """
        redis = await get_redis()
        now_ts = time.time()
        grace = max(0, int(settings.REALTIME_RULE_LATE_EVENT_GRACE_SECONDS))

        # Drop stale replay entries that are outside the active rule window.
        if event_timestamp < (now_ts - window_seconds - grace):
            return -1
        # Clamp small future skew to now to avoid future-bucket drift.
        if event_timestamp > (now_ts + grace):
            event_timestamp = now_ts

        bucket_size = max(1, int(settings.REALTIME_RULE_WINDOW_BUCKET_SECONDS))
        bucket_ts = int(event_timestamp // bucket_size) * bucket_size
        scope_hash = self._counter_scope_hash(counter_scope_key)
        counter_key = (
            f"{REALTIME_COUNTER_KEY_PREFIX}:{trigger_type}:{rule.id}:{scope_hash}:{bucket_ts}"
        )
        ttl_seconds = max(window_seconds * 2, bucket_size * 3)

        async with redis.pipeline(transaction=False) as pipe:
            pipe.incr(counter_key, 1)
            pipe.expire(counter_key, ttl_seconds)
            await pipe.execute()

        window_start = now_ts - window_seconds
        first_bucket = int(window_start // bucket_size) * bucket_size
        last_bucket = int(now_ts // bucket_size) * bucket_size
        if last_bucket < first_bucket:
            first_bucket = last_bucket

        bucket_keys: List[str] = []
        cursor = first_bucket
        while cursor <= last_bucket:
            bucket_keys.append(
                f"{REALTIME_COUNTER_KEY_PREFIX}:{trigger_type}:{rule.id}:{scope_hash}:{cursor}"
            )
            cursor += bucket_size

        if not bucket_keys:
            return 0

        values = await redis.mget(bucket_keys)
        total = 0
        for raw in values:
            if raw is None:
                continue
            try:
                total += int(raw)
            except (TypeError, ValueError):
                continue
        return total

    def _compile_regex(
        self,
        *,
        trigger_type: str,
        rule_id: str,
        pattern: str,
        case_sensitive: bool,
    ) -> Optional[re.Pattern[str]]:
        cache_key = f"{trigger_type}:{rule_id}:{int(case_sensitive)}:{pattern}"
        compiled = self._regex_cache.get(cache_key)
        if compiled is not None:
            return compiled

        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            compiled = re.compile(pattern, flags)
        except re.error as exc:
            logger.warning(
                "Invalid regex pattern for rule %s (%s): %s",
                rule_id,
                trigger_type,
                str(exc),
            )
            return None

        self._regex_cache[cache_key] = compiled
        return compiled

    def _message_matches(
        self,
        *,
        trigger_type: str,
        rule_id: str,
        pattern: str,
        message: str,
        is_regex: bool,
        case_sensitive: bool,
    ) -> bool:
        if not pattern:
            return True
        if not message:
            return False

        if is_regex:
            compiled = self._compile_regex(
                trigger_type=trigger_type,
                rule_id=rule_id,
                pattern=pattern,
                case_sensitive=case_sensitive,
            )
            if compiled is None:
                return False
            return compiled.search(message) is not None

        if case_sensitive:
            return pattern in message
        return pattern.lower() in message.lower()

    async def evaluate_log(
        self,
        log_data: Dict[str, Any],
        stream_message_id: Optional[str] = None,
    ) -> None:
        """
        Evaluate a log entry against applicable rules.

        This is called for each log from the Redis Stream. It performs:
        1. Index refresh check (time-gated)
        2. Container ID extraction
        3. Applicable rules lookup (O(1))
        4. Rule evaluation based on trigger_type
        5. Alert triggering via AlertTriggerService

        Args:
            log_data: Parsed log entry with container_id, message, etc.
            stream_message_id: Redis Stream message ID (for diagnostics/replay analysis).
        """
        # Refresh index if needed (time-gated)
        await self.maybe_refresh()

        # Extract container_id from log
        # Stream messages use composite key format: host_id:name
        container_id = self._normalize_container_id(log_data)
        if not container_id:
            logger.debug("Log missing container_id, skipping rule evaluation")
            return

        # Get applicable rules (O(1) lookup)
        rules = self.get_applicable_rules(container_id)
        if not rules:
            # 90%+ of logs skip here - no rules target this container
            return

        logger.debug(
            "Evaluating %d rules for container %s",
            len(rules),
            container_id,
        )

        # Evaluate each rule concurrently
        tasks = []
        for rule in rules:
            tasks.append(
                self._evaluate_rule(
                    rule,
                    log_data,
                    stream_message_id=stream_message_id,
                )
            )

        # Use gather with return_exceptions to prevent one failure from blocking others
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Log any errors
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Rule evaluation failed for rule %s: %s",
                    rules[i].id,
                    str(result),
                )

    async def _evaluate_rule(
        self,
        rule: AlertRule,
        log_data: Dict[str, Any],
        stream_message_id: Optional[str] = None,
    ) -> None:
        """
        Evaluate a single rule against a log entry.

        Args:
            rule: The AlertRule to evaluate.
            log_data: Parsed log entry.
        """
        trigger_type = rule.trigger_type.lower()
        trigger_config = rule.trigger_config

        try:
            if trigger_type == "keyword":
                await self._evaluate_keyword(
                    rule,
                    trigger_config,
                    log_data,
                    stream_message_id=stream_message_id,
                )
            elif trigger_type == "rate":
                await self._evaluate_rate(
                    rule,
                    trigger_config,
                    log_data,
                    stream_message_id=stream_message_id,
                )
            elif trigger_type == "absence":
                await self._evaluate_absence(rule, trigger_config, log_data)
            elif trigger_type == "container_event":
                # Container lifecycle rules are evaluated by event stream consumer,
                # not by per-log stream ingestion.
                return
            else:
                logger.warning("Unknown trigger type '%s' for rule %s", trigger_type, rule.id)

        except Exception as e:
            logger.error(
                "Error evaluating %s rule %s: %s",
                trigger_type,
                rule.id,
                str(e),
            )

    async def _evaluate_keyword(
        self,
        rule: AlertRule,
        config: Dict[str, Any],
        log_data: Dict[str, Any],
        stream_message_id: Optional[str] = None,
    ) -> None:
        """
        Evaluate a keyword rule from stream-time log ingestion.

        Uses sliding-window bucket counters so keyword rules can support
        count-over-window semantics in real-time:
        - threshold/occurrences/count (default 1)
        - window_seconds/window_minutes (default 5m)

        Args:
            rule: The AlertRule being evaluated.
            config: Trigger configuration with pattern, case_sensitive.
            log_data: Parsed log entry with message field.
            stream_message_id: Redis Stream ID for debug traces.
        """
        pattern = str(config.get("pattern", "") or "")
        is_regex = bool(config.get("is_regex", False))
        case_sensitive = bool(config.get("case_sensitive", False))
        message = str(log_data.get("message", "") or "")
        container_id = str(log_data.get("container_id", "") or "")

        if not pattern or not message or not container_id:
            return

        matched = self._message_matches(
            trigger_type="keyword",
            rule_id=rule.id,
            pattern=pattern,
            message=message,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
        )
        if not matched:
            return

        threshold = self._config_int(
            config,
            ["threshold", "occurrences", "count", "rate_limit"],
            default=1,
            minimum=1,
        )
        window_seconds = self._window_seconds(config, default_seconds=300)
        event_ts = self._parse_timestamp(log_data.get("timestamp"))
        counter_scope_key = self._scope_counter_key(rule, container_id)
        count = await self._window_count(
            rule,
            trigger_type="keyword",
            counter_scope_key=counter_scope_key,
            event_timestamp=event_ts,
            window_seconds=window_seconds,
        )

        if count < 0:
            logger.debug(
                "Dropped stale keyword event for rule=%s scope=%s stream_id=%s",
                rule.id,
                counter_scope_key,
                stream_message_id,
            )
            return
        if count < threshold:
            return

        host_id, container_name = self._split_container_id(container_id)
        result = EvaluationResult(
            rule_id=rule.id,
            triggered=True,
            value=message,
            message=(
                f"Pattern '{pattern}' matched {count} times in {window_seconds}s "
                f"(threshold={threshold})"
            ),
            context={
                "pattern": pattern,
                "is_regex": is_regex,
                "case_sensitive": case_sensitive,
                "count": count,
                "threshold": threshold,
                "window_seconds": window_seconds,
                "window_minutes": max(1, (window_seconds + 59) // 60),
                "counter_scope": counter_scope_key,
                "container_id": container_id,
                "host_id": host_id,
                "container_name": container_name,
                "matching_log": {
                    "message": message,
                    "timestamp": log_data.get("timestamp"),
                    "stream_message_id": stream_message_id,
                },
            },
        )

        await self._trigger_alert(rule, result)

    async def _evaluate_rate(
        self,
        rule: AlertRule,
        config: Dict[str, Any],
        log_data: Dict[str, Any],
        stream_message_id: Optional[str] = None,
    ) -> None:
        """
        Evaluate a rate rule with per-scope sliding-window counters.

        Args:
            rule: The AlertRule being evaluated.
            config: Trigger configuration with threshold/rate_limit + window.
            log_data: Parsed log entry.
            stream_message_id: Redis Stream ID for debug traces.
        """
        pattern = str(config.get("pattern", "") or "")
        is_regex = bool(config.get("is_regex", False))
        case_sensitive = bool(config.get("case_sensitive", False))
        rate_limit = self._config_int(
            config,
            ["threshold", "rate_limit", "count"],
            default=100,
            minimum=1,
        )
        window_seconds = self._window_seconds(config, default_seconds=300)
        message = str(log_data.get("message", "") or "")
        container_id = str(log_data.get("container_id", "") or "")

        if not container_id:
            return

        if pattern:
            matched = self._message_matches(
                trigger_type="rate",
                rule_id=rule.id,
                pattern=pattern,
                message=message,
                is_regex=is_regex,
                case_sensitive=case_sensitive,
            )
            if not matched:
                return

        event_ts = self._parse_timestamp(log_data.get("timestamp"))
        counter_scope_key = self._scope_counter_key(rule, container_id)
        count = await self._window_count(
            rule,
            trigger_type="rate",
            counter_scope_key=counter_scope_key,
            event_timestamp=event_ts,
            window_seconds=window_seconds,
        )

        if count < 0:
            logger.debug(
                "Dropped stale rate event for rule=%s scope=%s stream_id=%s",
                rule.id,
                counter_scope_key,
                stream_message_id,
            )
            return
        if count <= rate_limit:
            return

        host_id, container_name = self._split_container_id(container_id)
        result = EvaluationResult(
            rule_id=rule.id,
            triggered=True,
            value=str(count),
            message=(
                f"Log rate {count}/{window_seconds}s exceeds limit of {rate_limit}"
            ),
            context={
                "pattern": pattern,
                "is_regex": is_regex,
                "case_sensitive": case_sensitive,
                "count": count,
                "threshold": rate_limit,
                "rate_limit": rate_limit,
                "window_seconds": window_seconds,
                "window_minutes": max(1, (window_seconds + 59) // 60),
                "counter_scope": counter_scope_key,
                "container_id": container_id,
                "host_id": host_id,
                "container_name": container_name,
                "matching_log": {
                    "message": message,
                    "timestamp": log_data.get("timestamp"),
                    "stream_message_id": stream_message_id,
                },
            },
        )
        await self._trigger_alert(rule, result)

    async def _evaluate_absence(
        self,
        rule: AlertRule,
        config: Dict[str, Any],
        log_data: Dict[str, Any],
    ) -> None:
        """
        Update last-seen timestamp for absence detection.

        Absence rules don't trigger on log arrival - they're checked by
        the periodic scheduler. Here we just update the last-seen timestamp.

        Args:
            rule: The AlertRule being evaluated.
            config: Trigger configuration.
            log_data: Parsed log entry.
        """
        expected_pattern = config.get("expected_pattern")
        message = log_data.get("message", "")
        container_id = log_data.get("container_id")

        # Check if message matches expected pattern (if specified)
        if expected_pattern:
            if expected_pattern.lower() not in message.lower():
                return

        # Update last-seen timestamp in Redis
        redis = await get_redis()
        absence_key = f"alert-engine:absence:{rule.id}:{container_id}"
        now = time.time()

        # Store current timestamp (no expiry - scheduler will check these)
        await redis.set(absence_key, str(now))

        logger.debug(
            "Updated absence last-seen for rule %s, container %s",
            rule.id,
            container_id,
        )

    async def _trigger_alert(
        self,
        rule: AlertRule,
        result: EvaluationResult,
    ) -> None:
        """
        Trigger an alert via AlertTriggerService.

        Args:
            rule: The AlertRule that triggered.
            result: Evaluation result with trigger context.
        """
        try:
            # Create database session and services
            async with session_ctx() as session:
                redis = await get_redis()
                dedup_enabled = True
                dedup_window_seconds = DEFAULT_DEDUP_WINDOW_SECONDS
                try:
                    await gatekeeper.ensure_initialized()
                    gatekeeper_settings = gatekeeper.get_settings()
                    dedup_enabled = bool(gatekeeper_settings.get("dedup_enabled", True))
                    dedup_window_seconds = max(
                        1,
                        int(
                            gatekeeper_settings.get(
                                "dedup_window_seconds",
                                DEFAULT_DEDUP_WINDOW_SECONDS,
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

                dedup = DeduplicationService(
                    redis,
                    window_seconds=dedup_window_seconds,
                    enabled=dedup_enabled,
                )
                trigger_service = AlertTriggerService(session, dedup)

                # Trigger alert (handles deduplication, silencing, etc.)
                alert_id = await trigger_service.trigger_alert(result, rule)

                if alert_id:
                    logger.info(
                        "Alert triggered: rule=%s, alert_id=%s, container=%s",
                        rule.id,
                        alert_id,
                        result.context.get("container_id"),
                    )

        except Exception as e:
            logger.error(
                "Failed to trigger alert for rule %s: %s",
                rule.id,
                str(e),
            )

    async def check_absence_expiry(self) -> List[Tuple[AlertRule, str]]:
        """
        Check absence rules for expired last-seen timestamps.

        This method is called by the scheduler to detect absence conditions.
        It scans Redis for last-seen timestamps and returns container keys
        that have exceeded their window_minutes threshold.

        Returns:
            List of (rule, container_key) tuples for expired absence rules.
        """
        expired_pairs: List[Tuple[AlertRule, str]] = []

        try:
            # Fetch all enabled absence rules
            async with session_ctx() as session:
                stmt = select(AlertRule).where(
                    AlertRule.enabled == True,  # noqa: E712
                    AlertRule.trigger_type == "absence"
                )
                result = await session.execute(stmt)
                absence_rules = list(result.scalars().all())

            if not absence_rules:
                return expired_pairs

            redis = await get_redis()
            registry = get_container_registry()
            now = time.time()

            for rule in absence_rules:
                trigger_config = rule.trigger_config or {}
                window_minutes = int(trigger_config.get("window_minutes", 5))
                window_seconds = window_minutes * 60

                # Resolve scope to container keys
                scope_type = rule.scope_type.lower()
                scope_targets = rule.scope_targets or []
                container_keys: List[str] = []

                if scope_type == "global":
                    # For global scope, scan all absence keys for this rule
                    pattern = f"alert-engine:absence:{rule.id}:*"
                    # Use SCAN to get all keys (more efficient than KEYS)
                    cursor = 0
                    while True:
                        cursor, keys = await redis.scan(cursor, match=pattern, count=100)
                        for key in keys:
                            key_str = key if isinstance(key, str) else key.decode()
                            # Extract container_key from key pattern
                            # Format: alert-engine:absence:{rule.id}:{container_key}
                            parts = key_str.split(":", 3)
                            if len(parts) == 4:
                                container_keys.append(parts[3])
                        if cursor == 0:
                            break

                elif scope_type == "container":
                    # Direct container targeting
                    container_keys = scope_targets

                elif scope_type == "herald":
                    # Expand to all containers on host
                    for herald_id in scope_targets:
                        try:
                            containers = await registry.list_containers(host_id=herald_id)
                            for container in containers:
                                host_id = container.get("host_id", "")
                                name = container.get("name", "")
                                if host_id and name:
                                    container_keys.append(f"{host_id}:{name}")
                        except Exception as e:
                            logger.warning(
                                "Failed to expand herald scope for absence rule %s, herald %s: %s",
                                rule.id,
                                herald_id,
                                str(e),
                            )

                elif scope_type == "group":
                    # Expand group via Redis Set
                    for group_id in scope_targets:
                        try:
                            group_key = f"alert-engine:group-containers:{group_id}"
                            members = await redis.smembers(group_key)
                            for member in members:
                                member_str = member if isinstance(member, str) else member.decode()
                                container_keys.append(member_str)
                        except Exception as e:
                            logger.warning(
                                "Failed to expand group scope for absence rule %s, group %s: %s",
                                rule.id,
                                group_id,
                                str(e),
                            )

                # Check each container for expiry
                for container_key in container_keys:
                    absence_key = f"alert-engine:absence:{rule.id}:{container_key}"
                    last_seen_str = await redis.get(absence_key)

                    if not last_seen_str:
                        # Container never seen - can't detect absence until first log
                        continue

                    last_seen = float(last_seen_str)
                    elapsed = now - last_seen

                    # Check if elapsed time exceeds window
                    if elapsed > window_seconds:
                        expired_pairs.append((rule, container_key))

        except Exception as e:
            logger.error("Failed to check absence expiry: %s", str(e))

        return expired_pairs

    async def evaluate_container_event(self, event_data: Dict[str, Any]) -> None:
        """
        Evaluate a container lifecycle event against applicable stability rules.

        Called for each event from the unicron:events Redis Stream.
        Handles restart loop, crash loop, and failed start detection using
        count-in-window pattern with Redis sorted sets.

        Args:
            event_data: Parsed event with canonical identity fields.
                        Preferred shape includes `container_key`; compatible
                        fallback shape may include `container_id` (host:name)
                        or host/container_name pair.
        """
        # Refresh index if needed (time-gated)
        await self.maybe_refresh()

        container_key = self._normalize_container_key(event_data)
        if not container_key:
            logger.debug("Container event missing container_key, skipping rule evaluation")
            return

        # Ensure downstream evaluation uses a canonical identity field.
        event_data["container_key"] = container_key

        # Get applicable rules (O(1) lookup)
        rules = self.get_applicable_rules(container_key)
        if not rules:
            return

        # Filter to container_event rules only
        event_rules = [r for r in rules if r.trigger_type == "container_event"]
        if not event_rules:
            return

        event_type = event_data.get("event_type", "")
        exit_code = event_data.get("exit_code")

        logger.debug(
            "Evaluating %d container_event rules for %s (event: %s)",
            len(event_rules),
            container_key,
            event_type,
        )

        for rule in event_rules:
            try:
                await self._evaluate_container_event_rule(rule, event_data, event_type, exit_code)
            except Exception as e:
                logger.error(
                    "Error evaluating container_event rule %s: %s",
                    rule.id,
                    str(e),
                )

    async def _evaluate_container_event_rule(
        self,
        rule: AlertRule,
        event_data: Dict[str, Any],
        event_type: str,
        exit_code: Optional[int],
    ) -> None:
        """
        Evaluate a single container_event rule using count-in-window detection.

        Detection patterns (from templates):
        - restart_loop: trigger_value="start", counts start events in window
        - crash_loop: trigger_value="stop", counts stop/die events with non-zero exit
        - failed_start: trigger_value="start", counts quick-exit sequences

        All use count-in-window: N events within X minutes triggers alert.

        Args:
            rule: The container_event AlertRule.
            event_data: Full event payload.
            event_type: Docker event type (start, stop, die, restart, etc.).
            exit_code: Container exit code (None if not available).
        """
        trigger_config = rule.trigger_config or {}

        # Extract trigger_value and thresholds from trigger_config
        # Templates activated via templates.py put these in trigger_config
        # Support fallback to annotations and labels for legacy/manual rules
        trigger_value = trigger_config.get("trigger_value", "")
        if not trigger_value:
            trigger_value = rule.annotations.get("trigger_value", "")
        if not trigger_value and rule.labels:
            trigger_value = rule.labels.get("trigger_value", "")

        timeline_minutes = trigger_config.get("timeline_minutes")
        if timeline_minutes is None:
            timeline_minutes = rule.annotations.get("timeline_minutes", 5)
        timeline_minutes = int(timeline_minutes)

        timeline_count = trigger_config.get("timeline_count")
        if timeline_count is None:
            timeline_count = rule.annotations.get("timeline_count", 3)
        timeline_count = int(timeline_count)

        container_key = str(event_data.get("container_key", "") or "").strip()
        if not container_key:
            logger.debug(
                "Container event rule %s skipped due to missing container_key",
                rule.id,
            )
            return

        # Determine if this event matches the rule's trigger criteria
        if not self._event_matches_trigger(event_type, trigger_value, exit_code):
            return

        # Count-in-window using Redis sorted set
        redis = await get_redis()
        window_key = f"alert-engine:event-window:{rule.id}:{container_key}"
        now_ts = time.time()
        window_seconds = timeline_minutes * 60

        # Add this event to the sorted set (score = timestamp)
        event_id = f"{event_type}:{now_ts}"
        await redis.zadd(window_key, {event_id: now_ts})

        # Remove events outside the window
        cutoff = now_ts - window_seconds
        await redis.zremrangebyscore(window_key, "-inf", cutoff)

        # Count events in window
        count = await redis.zcard(window_key)

        # Set TTL for auto-cleanup (2x window to handle edge cases)
        await redis.expire(window_key, window_seconds * 2)

        logger.debug(
            "Event window for rule %s, container %s: %d/%d in %dmin",
            rule.id,
            container_key,
            count,
            timeline_count,
            timeline_minutes,
        )

        # Check if threshold exceeded
        if count >= timeline_count:
            # Classify the event for alert message
            classification = self._classify_exit_code(exit_code)

            result = EvaluationResult(
                rule_id=rule.id,
                triggered=True,
                value=str(count),
                message=f"Container event threshold: {count} {trigger_value} events in {timeline_minutes} minutes",
                context={
                    "container_key": container_key,
                    "container_name": event_data.get("container_name", ""),
                    "host_id": event_data.get("host_id", ""),
                    "event_type": event_type,
                    "trigger_value": trigger_value,
                    "count": count,
                    "timeline_count": timeline_count,
                    "timeline_minutes": timeline_minutes,
                    "exit_code": exit_code,
                    "exit_classification": classification,
                    "image": event_data.get("image", ""),
                },
            )

            await self._trigger_alert(rule, result)

            # Reset the window after triggering to avoid repeated alerts
            # for the same event burst (dedup handles rapid re-triggers,
            # but clearing the window prevents count accumulation)
            await redis.delete(window_key)

    def _event_matches_trigger(
        self,
        event_type: str,
        trigger_value: str,
        exit_code: Optional[int],
    ) -> bool:
        """
        Check if a Docker event matches the rule's trigger criteria.

        Matching logic:
        - "start": matches start and restart events
        - "stop": matches stop and die events (crash detection)
        - "die": matches die events specifically
        - "restart": matches restart events specifically
        - Empty/missing trigger_value: matches all events

        For crash detection (trigger_value="stop"), only non-zero exit codes
        count. Exit code 0 = graceful stop (not a crash). If exit_code is
        None (not available), we still match to avoid false negatives.

        Args:
            event_type: Docker event type.
            trigger_value: Rule's expected event type.
            exit_code: Container exit code (None if unavailable).

        Returns:
            True if event matches the trigger criteria.
        """
        if not trigger_value:
            return True

        trigger_value = trigger_value.lower()
        event_type = event_type.lower()

        if trigger_value == "start":
            return event_type in ("start", "restart")
        elif trigger_value == "stop":
            # For crash detection: exclude graceful stops (exit_code 0)
            if event_type not in ("stop", "die"):
                return False
            # If exit_code available and is 0, it's a graceful stop
            if exit_code is not None and exit_code == 0:
                return False
            return True
        elif trigger_value == "die":
            return event_type == "die"
        elif trigger_value == "restart":
            return event_type == "restart"
        else:
            return event_type == trigger_value

    @staticmethod
    def _classify_exit_code(exit_code: Optional[int]) -> str:
        """
        Classify container exit code for alert context.

        Args:
            exit_code: Container exit code (None if not available).

        Returns:
            Human-readable classification string.
        """
        if exit_code is None:
            return "unknown"
        if exit_code == 0:
            return "clean_shutdown"
        if exit_code == 1:
            return "application_error"
        if exit_code == 137:
            return "oom_killed"  # SIGKILL, typically OOM
        if exit_code == 143:
            return "sigterm"  # Graceful shutdown signal
        if exit_code > 128:
            return f"signal_{exit_code - 128}"
        return f"error_{exit_code}"


__all__ = ["RuleMatcher"]
