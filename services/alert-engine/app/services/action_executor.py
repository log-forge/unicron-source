"""
Action executor for alert-engine.

Executes remediation actions when alerts fire, integrating with:
- ActionGatekeeper for preflight safety checks
- Central API for actual container operations
- ActionAuditLog for compliance tracking
"""

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import session_ctx
from app.core.logging import get_logger
from app.models.action import ActionAuditLog, RuleAction
from app.services.action_gatekeeper import gatekeeper
from app.services.action_service import action_service
from app.services.rule_service import AlertRule

logger = get_logger("alert-engine.services.action_executor")


@dataclass
class ActionResult:
    """Result of an action execution attempt."""

    success: bool
    blocked: bool = False
    reason: Optional[str] = None
    error: Optional[str] = None
    duration_ms: int = 0
    container_state: Optional[str] = None
    action_id: Optional[str] = None


class ActionExecutor:
    """
    Service to execute actions via Central API with gatekeeper integration.

    Handles the complete action execution flow:
    1. Get actions for rule (ordered by order_index)
    2. For each action:
       a. Call gatekeeper.preflight()
       b. If blocked, log and skip
       c. If allowed, call Central API
       d. Call gatekeeper.post_result()
       e. Log to audit trail
    3. Return results
    """

    def __init__(self) -> None:
        self.central_url = settings.CENTRAL_URL
        self.internal_secret = settings.CENTRAL_INTERNAL_SECRET
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for Central API calls."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=45.0,
                headers={"X-Internal-Secret": self.internal_secret},
            )
        return self._http_client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def execute_actions(
        self,
        session: AsyncSession,
        rule: AlertRule,
        alert_context: Dict[str, Any],
        container_id: str,
        container_state: str,
    ) -> List[ActionResult]:
        """
        Execute all actions for a rule in order.

        Args:
            session: Async database session for querying actions.
            rule: The alert rule that fired.
            alert_context: Context from alert evaluation.
            container_id: Target container ID.
            container_state: Current container state (running, stopped, etc.).

        Returns:
            List of ActionResult for each action attempted.
        """
        # Get actions for rule (ordered by order_index, enabled only)
        actions = await action_service.get_actions_for_rule(
            session, rule.id, enabled_only=True
        )

        if not actions:
            logger.debug("No actions configured for rule %s", rule.id)
            return []

        results: List[ActionResult] = []

        for action in actions:
            try:
                result = await self._execute_single_action(
                    action=action,
                    rule=rule,
                    container_id=container_id,
                    container_state=container_state,
                    alert_context=alert_context,
                )
                results.append(result)

                # Update container_state for subsequent actions if changed
                if result.success and result.container_state:
                    container_state = result.container_state

            except Exception as e:
                logger.error(
                    "Unexpected error executing action %s: %s",
                    action.id,
                    str(e),
                    exc_info=True,
                )
                results.append(
                    ActionResult(
                        success=False,
                        error=str(e),
                        action_id=action.id,
                    )
                )

        logger.info(
            "Executed %d actions for rule %s: %d succeeded, %d blocked, %d failed",
            len(results),
            rule.id,
            sum(1 for r in results if r.success),
            sum(1 for r in results if r.blocked),
            sum(1 for r in results if not r.success and not r.blocked),
        )

        return results

    async def _execute_single_action(
        self,
        action: RuleAction,
        rule: AlertRule,
        container_id: str,
        container_state: str,
        alert_context: Dict[str, Any],
    ) -> ActionResult:
        """
        Execute a single action with gatekeeper checks.

        Args:
            action: The action to execute.
            rule: The alert rule.
            container_id: Target container ID.
            container_state: Current container state.
            alert_context: Context from alert evaluation.

        Returns:
            ActionResult with execution outcome.
        """
        if str(action.action_type or "").strip().lower() == "notify":
            return await self._handle_notify_action(
                action=action,
                rule=rule,
                container_id=container_id,
                alert_context=alert_context,
            )

        # 1. Preflight check with gatekeeper
        allowed, reason = await gatekeeper.preflight(
            container_id=container_id,
            rule_id=rule.id,
            action_type=action.action_type,
            current_container_state=container_state,
        )

        if not allowed:
            logger.info(
                "Action blocked by gatekeeper: rule=%s, action=%s, container=%s, reason=%s",
                rule.id,
                action.action_type,
                container_id,
                reason,
            )

            # Log blocked action to audit
            await self._log_action(
                rule=rule,
                action=action,
                container_id=container_id,
                status="blocked",
                block_reason=reason,
                alert_context=alert_context,
            )

            return ActionResult(
                success=False,
                blocked=True,
                reason=reason,
                action_id=action.id,
            )

        # 2. Execute via Central API
        start_time = time.monotonic()
        try:
            result = await self._call_central_action_api(
                container_id=container_id,
                action_type=action.action_type,
                action_config=action.action_config,
                rule_id=rule.id,
            )

            duration_ms = int((time.monotonic() - start_time) * 1000)
            result.duration_ms = duration_ms
            result.action_id = action.id

            # 3. Post-result to gatekeeper
            await gatekeeper.post_result(
                container_id=container_id,
                rule_id=rule.id,
                action_type=action.action_type,
                success=result.success,
                error_context={"error": result.error} if result.error else None,
            )

            # 4. Log to audit
            await self._log_action(
                rule=rule,
                action=action,
                container_id=container_id,
                status="success" if result.success else "failed",
                error_message=result.error,
                duration_ms=duration_ms,
                alert_context=alert_context,
            )

            return result

        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            error_msg = str(e)

            # Post failure to gatekeeper
            await gatekeeper.post_result(
                container_id=container_id,
                rule_id=rule.id,
                action_type=action.action_type,
                success=False,
                error_context={"error": error_msg},
            )

            # Log to audit
            await self._log_action(
                rule=rule,
                action=action,
                container_id=container_id,
                status="failed",
                error_message=error_msg,
                duration_ms=duration_ms,
                alert_context=alert_context,
            )

            logger.error(
                "Action execution failed: rule=%s, action=%s, container=%s, error=%s",
                rule.id,
                action.action_type,
                container_id,
                error_msg,
            )

            return ActionResult(
                success=False,
                error=error_msg,
                duration_ms=duration_ms,
                action_id=action.id,
            )

    async def _call_central_action_api(
        self,
        container_id: str,
        action_type: str,
        action_config: Dict[str, Any],
        rule_id: str,
    ) -> ActionResult:
        """
        Call Central internal API to execute action.

        Args:
            container_id: Target container ID.
            action_type: Type of action to execute.
            action_config: Action-specific configuration.
            rule_id: Rule ID for tracking.

        Returns:
            ActionResult from Central API response.
        """
        client = await self._get_client()

        # Use longer timeout for run_script actions (agent may take longer)
        request_timeout = 60.0 if action_type == "run_script" else None

        try:
            response = await client.post(
                f"{self.central_url}/internal/actions/execute",
                json={
                    "container_key": container_id,
                    "action_type": action_type,
                    "action_config": action_config,
                    "rule_id": rule_id,
                    "initiated_by": "alert-rule",
                },
                timeout=request_timeout,
            )

            response.raise_for_status()
        except httpx.HTTPStatusError:
            error_detail = f"Central API error: {response.status_code} {response.text}"
            logger.error(
                "Central action API returned error: status=%d, body=%s",
                response.status_code,
                response.text[:500],
            )
            return ActionResult(
                success=False,
                error=error_detail,
            )

        data = response.json()

        return ActionResult(
            success=data.get("success", False),
            error=data.get("error"),
            duration_ms=data.get("duration_ms", 0),
            container_state=data.get("container_state"),
        )

    async def _handle_notify_action(
        self,
        action: RuleAction,
        rule: AlertRule,
        container_id: str,
        alert_context: Dict[str, Any],
    ) -> ActionResult:
        """Treat notify actions as successful once targets are attached to the alert stream."""
        targets = alert_context.get("notification_targets") or {}
        notification_dispatched = bool(
            alert_context.get("notification_dispatched", False)
        )
        target_count = sum(
            len(targets.get(key, []) or [])
            for key in ("channel_ids", "group_ids", "preset_ids")
        )

        if not notification_dispatched:
            error_message = "Notification dispatch was not published for this alert instance"
            await self._log_action(
                rule=rule,
                action=action,
                container_id=container_id,
                status="failed",
                error_message=error_message,
                alert_context=alert_context,
            )
            return ActionResult(
                success=False,
                error=error_message,
                action_id=action.id,
            )

        if target_count <= 0:
            error_message = "No notification targets were attached to the alert payload"
            await self._log_action(
                rule=rule,
                action=action,
                container_id=container_id,
                status="failed",
                error_message=error_message,
                alert_context=alert_context,
            )
            return ActionResult(
                success=False,
                error=error_message,
                action_id=action.id,
            )

        await self._log_action(
            rule=rule,
            action=action,
            container_id=container_id,
            status="success",
            alert_context=alert_context,
        )
        return ActionResult(
            success=True,
            reason=f"Notification dispatched to {target_count} target selector(s)",
            action_id=action.id,
        )

    async def _log_action(
        self,
        rule: AlertRule,
        action: RuleAction,
        container_id: str,
        status: str,
        alert_context: Dict[str, Any],
        block_reason: Optional[str] = None,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        """
        Log action to audit trail.

        Args:
            rule: The alert rule.
            action: The action executed.
            container_id: Target container ID.
            status: Outcome status (blocked, success, failed).
            alert_context: Context from alert evaluation.
            block_reason: Reason for blocking (if blocked).
            error_message: Error message (if failed).
            duration_ms: Execution duration in milliseconds.
        """
        # Keyword/rule contexts use host_id; older paths may still use herald_id.
        herald_id = alert_context.get("host_id") or alert_context.get("herald_id", "")

        audit_log = ActionAuditLog(
            id=uuid.uuid4().hex,
            rule_id=rule.id,
            rule_name=rule.name,
            action_type=action.action_type,
            container_id=container_id,
            herald_id=herald_id,
            status=status,
            block_reason=block_reason,
            error_message=error_message,
            duration_ms=duration_ms,
            initiated_by="rule_evaluation",
            triggered_at=datetime.now(timezone.utc),
        )

        # Use independent session for audit logging to avoid transaction conflicts
        async with session_ctx() as session:
            session.add(audit_log)
            await session.commit()

        logger.debug(
            "Logged action to audit: rule=%s, action=%s, status=%s",
            rule.id,
            action.action_type,
            status,
        )


# Singleton instance
action_executor = ActionExecutor()

__all__ = ["ActionExecutor", "ActionResult", "action_executor"]
