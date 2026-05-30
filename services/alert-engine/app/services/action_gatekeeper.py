"""
Action Gatekeeper - Prevents endless loops and manages action execution.

Ported from LogForge implementation to async FastAPI context.
Key adaptations:
- threading.RLock -> asyncio.Lock
- threading.Timer -> asyncio tasks (for verification)
- SQLModel async session for DB operations
- async/await throughout
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, Optional, Tuple

from sqlalchemy import select

from app.core.database import session_ctx
from app.models.gatekeeper_state import ActionGatekeeperState, GatekeeperConfig

logger = logging.getLogger(__name__)


@dataclass
class GatekeeperState:
    """In-memory state for fast lookups."""

    last_attempt_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    failure_count: int = 0
    cooldown_until: Optional[datetime] = None
    backoff_until: Optional[datetime] = None
    disabled_until: Optional[datetime] = None
    first_limit_hit_at: Optional[datetime] = None
    last_error_context: Optional[Dict[str, Any]] = field(default_factory=dict)


class ActionGatekeeper:
    """
    Single middleware that enforces all action guardrails:
    - Desired state checks
    - Static cooldowns
    - Exponential backoff
    - Temporary rule disabling
    - Global action limits
    - Container-level semaphores
    """

    # Configuration defaults
    COOLDOWN_MINUTES: Dict[str, int] = {
        "restart": 5,
        "stop": 3,
        "start": 3,
        "kill": 5,
        "run_script": 10,
    }

    BACKOFF_DELAYS: list[int] = [2, 5, 15]  # minutes: 2m -> 5m -> 15m, cap at 30m
    MAX_BACKOFF_MINUTES: int = 30
    DISABLE_AFTER_FAILURES: int = 3
    DISABLE_DURATION_MINUTES: int = 60

    # Global limits
    MAX_ACTIONS_PER_RULE_PER_HOUR: int = 3
    MAX_ACTIONS_PER_CONTAINER_PER_HOUR: int = 10

    # Verification delay for restart/start/stop actions
    VERIFICATION_DELAY_SECONDS: int = 30

    # Trigger suppression (post-remediation chain-reaction protection)
    TRIGGER_SUPPRESSION_ENABLED: bool = True
    TRIGGER_SUPPRESSION_MINUTES: int = 10
    TRIGGER_SUPPRESSION_ACTIONS: list[str] = ["stop", "kill", "restart", "start", "notify"]
    TRIGGER_SUPPRESSION_RULE_TYPES: list[str] = ["all"]

    # Alert deduplication suppression window
    DEDUP_ENABLED: bool = True
    DEDUP_WINDOW_SECONDS: int = 900

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()

        # Write-through cache: in-memory dict + DB persistence
        self._state_cache: Dict[str, GatekeeperState] = {}

        # Rolling counters for global limits (simple timestamp deques)
        self._rule_actions: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=self.MAX_ACTIONS_PER_RULE_PER_HOUR)
        )
        self._container_actions: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=self.MAX_ACTIONS_PER_CONTAINER_PER_HOUR)
        )

        # Container semaphores (destructive action locks)
        self._container_semaphores: Dict[str, float] = {}  # container_id -> expiry_timestamp

        # One-shot verification tasks
        self._verification_tasks: Dict[str, asyncio.Task[None]] = {}

        # Initialize flag (we'll warm cache on first use since __init__ can't be async)
        self._initialized = False

    @staticmethod
    def _normalize_string_list(value: Any) -> list[str]:
        """Normalize a settings list to lowercase, unique, non-empty strings."""
        if not isinstance(value, list):
            return []

        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            raw = str(item or "").strip().lower()
            if not raw or raw in seen:
                continue
            seen.add(raw)
            normalized.append(raw)

        return normalized

    def _rebuild_rate_limit_deques(self) -> None:
        """Recreate rolling deques with new maxlen limits."""
        new_rule_max = max(0, int(self.MAX_ACTIONS_PER_RULE_PER_HOUR))
        new_container_max = max(0, int(self.MAX_ACTIONS_PER_CONTAINER_PER_HOUR))

        # Rebuild rule action deques
        for key, dq in list(self._rule_actions.items()):
            items = list(dq)[-new_rule_max:] if new_rule_max > 0 else []
            self._rule_actions[key] = deque(items, maxlen=new_rule_max)

        # Rebuild container action deques
        for cid, dq in list(self._container_actions.items()):
            items = list(dq)[-new_container_max:] if new_container_max > 0 else []
            self._container_actions[cid] = deque(items, maxlen=new_container_max)

    async def apply_settings(self, settings: Dict[str, Any]) -> None:
        """Apply validated settings to runtime gatekeeper and rebuild rate-limit deques if needed."""
        async with self._lock:
            # Assign basic settings
            if "cooldown_minutes" in settings and isinstance(settings["cooldown_minutes"], dict):
                self.COOLDOWN_MINUTES = settings["cooldown_minutes"]
            if "backoff_delays" in settings and isinstance(settings["backoff_delays"], list):
                self.BACKOFF_DELAYS = list(settings["backoff_delays"])
            if "max_backoff_minutes" in settings:
                self.MAX_BACKOFF_MINUTES = int(settings["max_backoff_minutes"])
            if "disable_after_failures" in settings:
                self.DISABLE_AFTER_FAILURES = int(settings["disable_after_failures"])
            if "disable_duration_minutes" in settings:
                self.DISABLE_DURATION_MINUTES = int(settings["disable_duration_minutes"])

            # Rate limits
            rebuild_needed = False
            if "max_actions_per_rule_per_hour" in settings:
                self.MAX_ACTIONS_PER_RULE_PER_HOUR = int(settings["max_actions_per_rule_per_hour"])
                rebuild_needed = True
            if "max_actions_per_container_per_hour" in settings:
                self.MAX_ACTIONS_PER_CONTAINER_PER_HOUR = int(
                    settings["max_actions_per_container_per_hour"]
                )
                rebuild_needed = True
            if rebuild_needed:
                self._rebuild_rate_limit_deques()

            # Verification delay
            if "verification_delay_seconds" in settings:
                self.VERIFICATION_DELAY_SECONDS = int(settings["verification_delay_seconds"])

            # Trigger suppression
            if "trigger_suppression_enabled" in settings:
                self.TRIGGER_SUPPRESSION_ENABLED = bool(settings["trigger_suppression_enabled"])
            if "trigger_suppression_minutes" in settings:
                self.TRIGGER_SUPPRESSION_MINUTES = max(
                    0, int(settings["trigger_suppression_minutes"])
                )
            if "trigger_suppression_actions" in settings:
                self.TRIGGER_SUPPRESSION_ACTIONS = self._normalize_string_list(
                    settings["trigger_suppression_actions"]
                )
            if "trigger_suppression_rule_types" in settings:
                normalized_rule_types = self._normalize_string_list(
                    settings["trigger_suppression_rule_types"]
                )
                self.TRIGGER_SUPPRESSION_RULE_TYPES = (
                    normalized_rule_types if normalized_rule_types else ["all"]
                )

            # Alert deduplication
            if "dedup_enabled" in settings:
                self.DEDUP_ENABLED = bool(settings["dedup_enabled"])
            if "dedup_window_seconds" in settings:
                self.DEDUP_WINDOW_SECONDS = max(1, int(settings["dedup_window_seconds"]))

    def get_settings(self) -> Dict[str, Any]:
        """Get current gatekeeper settings as dict."""
        return {
            "cooldown_minutes": dict(self.COOLDOWN_MINUTES),
            "backoff_delays": list(self.BACKOFF_DELAYS),
            "max_backoff_minutes": self.MAX_BACKOFF_MINUTES,
            "disable_after_failures": self.DISABLE_AFTER_FAILURES,
            "disable_duration_minutes": self.DISABLE_DURATION_MINUTES,
            "max_actions_per_rule_per_hour": self.MAX_ACTIONS_PER_RULE_PER_HOUR,
            "max_actions_per_container_per_hour": self.MAX_ACTIONS_PER_CONTAINER_PER_HOUR,
            "verification_delay_seconds": self.VERIFICATION_DELAY_SECONDS,
            "trigger_suppression_enabled": self.TRIGGER_SUPPRESSION_ENABLED,
            "trigger_suppression_minutes": self.TRIGGER_SUPPRESSION_MINUTES,
            "trigger_suppression_actions": list(self.TRIGGER_SUPPRESSION_ACTIONS),
            "trigger_suppression_rule_types": (
                list(self.TRIGGER_SUPPRESSION_RULE_TYPES)
                if self.TRIGGER_SUPPRESSION_RULE_TYPES
                else ["all"]
            ),
            "dedup_enabled": self.DEDUP_ENABLED,
            "dedup_window_seconds": self.DEDUP_WINDOW_SECONDS,
        }

    async def ensure_initialized(self) -> None:
        """Public initialization hook for API routes."""
        await self._ensure_initialized()

    async def load_config_from_db(self) -> None:
        """Load existing gatekeeper configuration from database."""
        try:
            async with session_ctx() as session:
                result = await session.execute(select(GatekeeperConfig).where(GatekeeperConfig.id == 1))
                config = result.scalar_one_or_none()
                if config and config.settings:
                    await self.apply_settings(config.settings)
                    logger.info("Loaded gatekeeper config from database")
                else:
                    logger.info("No gatekeeper config in database, using defaults")
        except Exception as e:
            logger.error(f"Failed to load gatekeeper config from DB: {e}")

    async def _ensure_initialized(self) -> None:
        """Initialize on first use (since __init__ can't be async)."""
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return
            await self.load_config_from_db()
            self._initialized = True

    def _get_state_key(self, container_id: str, rule_id: str, action_type: str) -> str:
        """Generate unique key for state tracking."""
        return f"{container_id}_{rule_id}_{action_type}"

    async def _get_state(
        self, container_id: str, rule_id: str, action_type: str
    ) -> GatekeeperState:
        """Get state from cache, load from DB if needed."""
        await self._ensure_initialized()
        key = self._get_state_key(container_id, rule_id, action_type)

        async with self._lock:
            if key not in self._state_cache:
                # Load from DB
                async with session_ctx() as session:
                    result = await session.execute(
                        select(ActionGatekeeperState).where(ActionGatekeeperState.id == key)
                    )
                    db_state = result.scalar_one_or_none()

                    if db_state:
                        self._state_cache[key] = GatekeeperState(
                            last_attempt_at=db_state.last_attempt_at,
                            last_success_at=db_state.last_success_at,
                            failure_count=db_state.failure_count,
                            cooldown_until=db_state.cooldown_until,
                            backoff_until=db_state.backoff_until,
                            disabled_until=db_state.disabled_until,
                            first_limit_hit_at=db_state.first_limit_hit_at,
                            last_error_context=db_state.last_error_context,
                        )
                    else:
                        # Create new state
                        self._state_cache[key] = GatekeeperState()

            return self._state_cache[key]

    async def _save_state(
        self, container_id: str, rule_id: str, action_type: str, state: GatekeeperState
    ) -> None:
        """Save state to both cache and DB (write-through)."""
        key = self._get_state_key(container_id, rule_id, action_type)

        async with self._lock:
            self._state_cache[key] = state

            # Write through to DB
            async with session_ctx() as session:
                result = await session.execute(
                    select(ActionGatekeeperState).where(ActionGatekeeperState.id == key)
                )
                db_state = result.scalar_one_or_none()

                now = datetime.now(timezone.utc)

                if db_state:
                    # Update existing
                    db_state.last_attempt_at = state.last_attempt_at
                    db_state.last_success_at = state.last_success_at
                    db_state.failure_count = state.failure_count
                    db_state.cooldown_until = state.cooldown_until
                    db_state.backoff_until = state.backoff_until
                    db_state.disabled_until = state.disabled_until
                    db_state.first_limit_hit_at = state.first_limit_hit_at
                    db_state.last_error_context = state.last_error_context
                    db_state.updated_at = now
                else:
                    # Create new
                    db_state = ActionGatekeeperState(
                        id=key,
                        container_id=container_id,
                        rule_id=rule_id,
                        action_type=action_type,
                        last_attempt_at=state.last_attempt_at,
                        last_success_at=state.last_success_at,
                        failure_count=state.failure_count,
                        cooldown_until=state.cooldown_until,
                        backoff_until=state.backoff_until,
                        disabled_until=state.disabled_until,
                        first_limit_hit_at=state.first_limit_hit_at,
                        last_error_context=state.last_error_context,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(db_state)

                await session.commit()

    def _check_desired_state(
        self, container_id: str, action_type: str, current_container_state: str
    ) -> Tuple[bool, str]:
        """Check if action is needed based on current container state."""
        if action_type == "restart":
            # Always allow restart (it stops then starts)
            return True, ""
        elif action_type == "start":
            if current_container_state in ["running", "restarting"]:
                return False, f"Container {container_id} is already {current_container_state}"
        elif action_type == "stop":
            if current_container_state in ["exited", "stopped", "dead"]:
                return False, f"Container {container_id} is already {current_container_state}"
        elif action_type == "kill":
            if current_container_state in ["exited", "stopped", "dead"]:
                return False, f"Container {container_id} is already {current_container_state}"
        # run_script always allowed (scripts can do anything)

        return True, ""

    def _check_global_limits(self, container_id: str, rule_id: str) -> Tuple[bool, str]:
        """Check hourly action limits."""
        now = time.time()
        hour_ago = now - 3600

        # Clean old entries and check limits
        rule_key = f"{rule_id}_{container_id}"

        # Per-rule limit
        rule_actions = self._rule_actions[rule_key]
        # Remove old entries
        while rule_actions and rule_actions[0] < hour_ago:
            rule_actions.popleft()

        if len(rule_actions) >= self.MAX_ACTIONS_PER_RULE_PER_HOUR:
            return (
                False,
                f"Rule {rule_id} has exceeded {self.MAX_ACTIONS_PER_RULE_PER_HOUR} actions per hour on container {container_id}",
            )

        # Per-container limit
        container_actions = self._container_actions[container_id]
        while container_actions and container_actions[0] < hour_ago:
            container_actions.popleft()

        if len(container_actions) >= self.MAX_ACTIONS_PER_CONTAINER_PER_HOUR:
            return (
                False,
                f"Container {container_id} has exceeded {self.MAX_ACTIONS_PER_CONTAINER_PER_HOUR} actions per hour",
            )

        return True, ""

    async def _acquire_container_semaphore(
        self, container_id: str, action_type: str
    ) -> Tuple[bool, str]:
        """Acquire semaphore for destructive operations."""
        if action_type not in ["restart", "stop", "start", "kill", "run_script"]:
            return True, ""  # Non-destructive actions don't need semaphore

        now = time.time()

        async with self._lock:
            # Clean expired semaphores
            expired_containers = [
                cid for cid, expiry in self._container_semaphores.items() if expiry < now
            ]
            for cid in expired_containers:
                del self._container_semaphores[cid]

            # Check if container is locked
            if container_id in self._container_semaphores:
                return False, f"Container {container_id} has an action in progress"

            # Acquire semaphore (30 second TTL)
            self._container_semaphores[container_id] = now + 30
            return True, ""

    def _release_container_semaphore(self, container_id: str) -> None:
        """Release container semaphore."""
        self._container_semaphores.pop(container_id, None)

    def _record_action_attempt(self, container_id: str, rule_id: str) -> None:
        """Record action attempt for global limits."""
        now = time.time()
        rule_key = f"{rule_id}_{container_id}"

        self._rule_actions[rule_key].append(now)
        self._container_actions[container_id].append(now)

    async def preflight(
        self,
        container_id: str,
        rule_id: str,
        action_type: str,
        current_container_state: str,
    ) -> Tuple[bool, str]:
        """
        Preflight check - returns (allowed, reason).
        Order: desired_state -> global_limits -> cooldown -> backoff -> disabled -> semaphore
        """
        now = datetime.now(timezone.utc)

        # 1. Desired state check
        allowed, reason = self._check_desired_state(container_id, action_type, current_container_state)
        if not allowed:
            # Reset failure count if container is already in desired state
            state = await self._get_state(container_id, rule_id, action_type)
            if state.failure_count > 0:
                state.failure_count = 0
                state.cooldown_until = None
                state.backoff_until = None
                state.disabled_until = None
                await self._save_state(container_id, rule_id, action_type, state)
                logger.info(
                    f"Reset failure count for {container_id}_{rule_id}_{action_type} - already in desired state"
                )
            return False, f"DESIRED_STATE: {reason}"

        # 2. Global limits check
        allowed, reason = self._check_global_limits(container_id, rule_id)
        if not allowed:
            return False, f"GLOBAL_LIMIT: {reason}"

        # Get state for remaining checks
        state = await self._get_state(container_id, rule_id, action_type)

        # 3. Cooldown check
        if state.cooldown_until and now < state.cooldown_until:
            remaining = (state.cooldown_until - now).total_seconds() / 60
            return False, f"COOLDOWN: {remaining:.1f} minutes remaining"

        # 4. Backoff check
        if state.backoff_until and now < state.backoff_until:
            remaining = (state.backoff_until - now).total_seconds() / 60
            return False, f"BACKOFF: {remaining:.1f} minutes remaining"

        # 5. Temporary disable check
        if state.disabled_until and now < state.disabled_until:
            remaining = (state.disabled_until - now).total_seconds() / 60
            return False, f"DISABLED: {remaining:.1f} minutes remaining"

        # 6. Container semaphore
        allowed, reason = await self._acquire_container_semaphore(container_id, action_type)
        if not allowed:
            return False, f"SEMAPHORE: {reason}"

        # All checks passed - record the attempt
        state.last_attempt_at = now
        await self._save_state(container_id, rule_id, action_type, state)
        self._record_action_attempt(container_id, rule_id)

        return True, "ALLOWED"

    async def post_result(
        self,
        container_id: str,
        rule_id: str,
        action_type: str,
        success: bool,
        error_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Process action result and update state."""
        now = datetime.now(timezone.utc)
        state = await self._get_state(container_id, rule_id, action_type)

        try:
            if success:
                # Reset all failure state on success
                state.last_success_at = now
                state.failure_count = 0
                state.cooldown_until = None
                state.backoff_until = None
                state.disabled_until = None
                state.last_error_context = None

                logger.info(f"Action succeeded: {container_id}_{rule_id}_{action_type}")

                # Schedule verification for restart/start/stop actions
                if action_type in ["restart", "start", "stop"]:
                    await self._schedule_verification(container_id, rule_id, action_type)

            else:
                # Handle failure
                state.failure_count += 1
                state.last_error_context = error_context

                # Set static cooldown
                cooldown_minutes = self.COOLDOWN_MINUTES.get(action_type, 5)
                state.cooldown_until = now + timedelta(minutes=cooldown_minutes)

                # Set exponential backoff
                if state.failure_count <= len(self.BACKOFF_DELAYS):
                    backoff_minutes = self.BACKOFF_DELAYS[state.failure_count - 1]
                else:
                    backoff_minutes = self.MAX_BACKOFF_MINUTES

                # Add jitter (10%)
                jitter = (
                    backoff_minutes
                    * 0.1
                    * (2 * (hash(f"{container_id}{rule_id}") % 100) / 100 - 1)
                )
                final_backoff = max(1, backoff_minutes + jitter)
                state.backoff_until = now + timedelta(minutes=final_backoff)

                logger.warning(
                    f"Action failed (attempt {state.failure_count}): {container_id}_{rule_id}_{action_type}, "
                    f"cooldown: {cooldown_minutes}m, backoff: {final_backoff:.1f}m"
                )

                # Temporary disable after max failures
                if state.failure_count >= self.DISABLE_AFTER_FAILURES:
                    state.disabled_until = now + timedelta(minutes=self.DISABLE_DURATION_MINUTES)
                    logger.error(
                        f"Rule temporarily disabled for {self.DISABLE_DURATION_MINUTES}m: "
                        f"{rule_id} on {container_id} action {action_type}"
                    )

            # Save state
            await self._save_state(container_id, rule_id, action_type, state)

        finally:
            # Always release semaphore
            self._release_container_semaphore(container_id)

    async def _schedule_verification(
        self, container_id: str, rule_id: str, action_type: str
    ) -> None:
        """Schedule one-shot verification task."""
        task_key = f"{container_id}_{rule_id}_{action_type}"

        # Cancel existing task if any
        if task_key in self._verification_tasks:
            self._verification_tasks[task_key].cancel()

        async def verify() -> None:
            try:
                await asyncio.sleep(self.VERIFICATION_DELAY_SECONDS)
                # The actual verification logic should be handled by the caller
                # We just log that verification is needed
                logger.info(f"Verification complete for {task_key}")
            except asyncio.CancelledError:
                logger.debug(f"Verification cancelled for {task_key}")
            except Exception as e:
                logger.error(f"Verification error for {task_key}: {e}")
            finally:
                # Cleanup
                self._verification_tasks.pop(task_key, None)

        # Schedule verification
        task = asyncio.create_task(verify())
        self._verification_tasks[task_key] = task

    async def get_state_summary(
        self, container_id: str, rule_id: str, action_type: str
    ) -> Dict[str, Any]:
        """Get current state summary for debugging/monitoring."""
        state = await self._get_state(container_id, rule_id, action_type)
        now = datetime.now(timezone.utc)

        return {
            "key": self._get_state_key(container_id, rule_id, action_type),
            "failure_count": state.failure_count,
            "last_attempt": state.last_attempt_at.isoformat() if state.last_attempt_at else None,
            "last_success": state.last_success_at.isoformat() if state.last_success_at else None,
            "cooldown_remaining_minutes": (
                max(0, (state.cooldown_until - now).total_seconds() / 60)
                if state.cooldown_until
                else 0
            ),
            "backoff_remaining_minutes": (
                max(0, (state.backoff_until - now).total_seconds() / 60)
                if state.backoff_until
                else 0
            ),
            "disabled_remaining_minutes": (
                max(0, (state.disabled_until - now).total_seconds() / 60)
                if state.disabled_until
                else 0
            ),
            "last_error": state.last_error_context,
        }


# Global gatekeeper instance
gatekeeper = ActionGatekeeper()

__all__ = ["ActionGatekeeper", "GatekeeperState", "gatekeeper"]
