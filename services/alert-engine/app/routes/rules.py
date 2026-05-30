"""REST API endpoints for alert rule CRUD operations."""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import UserContext, require_authenticated_user
from app.core.logging import get_logger
from app.core.rbac import filter_rules_by_access, validate_scope_access
from app.schemas.action_schemas import ActionResponse
from app.schemas.rule_schemas import (
    BulkToggleRequest,
    BulkToggleResponse,
    ConvertToCustomResponse,
    DryRunRequest,
    DryRunResult,
    RuleCreate,
    RuleListResponse,
    RuleResponse,
    RuleUsageCounts,
    RuleUsageLimits,
    RuleUsageResponse,
    RuleUsageUser,
    RuleUpdate,
    _validate_scope_targets_for_type,
)
from app.services.action_service import action_service
from app.services.evaluator import RuleEvaluator
from app.services.rule_audit_service import RuleAuditService
from app.services.rule_service import (
    AlertRule,
    RuleNotFoundError,
    RuleService,
)

logger = get_logger("alert-engine.routes.rules")


async def _build_rule_response(
    rule: AlertRule, session: AsyncSession
) -> RuleResponse:
    """Build a RuleResponse with actions loaded from the ruleaction table.

    The AlertRule model has no ORM relationship to RuleAction, so we must
    load actions separately and attach them to the response.  We refresh
    the rule first in case a prior commit (e.g. from sync_actions) expired
    its ORM attributes.
    """
    try:
        await session.refresh(rule)
    except Exception:
        pass  # Already detached or fresh — proceed with current attributes
    response = RuleResponse.model_validate(rule)
    try:
        actions = await action_service.get_actions_for_rule(
            session, response.id, enabled_only=False
        )
        response.actions = [ActionResponse.model_validate(a) for a in actions]
    except Exception as exc:
        logger.warning("Failed to load actions for rule %s: %s", response.id, exc)
        # Keep default empty list
    return response


def _build_rule_response_from_actions(
    rule: AlertRule, actions: List[Any]
) -> RuleResponse:
    """Build a RuleResponse from preloaded actions.

    Used by list endpoints to avoid one action query per rule.
    """
    response = RuleResponse.model_validate(rule)
    response.actions = [ActionResponse.model_validate(action) for action in actions]
    return response


def _compute_changes(
    old_rule: AlertRule, updates: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """Compute changes between old rule and updates for audit logging."""
    changes = {}
    for field, new_value in updates.items():
        old_value = getattr(old_rule, field, None)
        if old_value != new_value:
            changes[field] = {"old": old_value, "new": new_value}
    return changes

async def _invalidate_rule_cache(request: Request, *, reason: str) -> None:
    """Invalidate the RuleMatcher cache so rule changes take effect immediately.

    Called after any rule mutation (create, update, delete, toggle).
    Safe to call even if rule_matcher is not on app.state (e.g., during testing).
    """
    rule_matcher = getattr(request.app.state, "rule_matcher", None)
    if rule_matcher is not None:
        publish = getattr(rule_matcher, "publish_invalidation", None)
        if callable(publish):
            await publish(reason=reason)
        else:
            rule_matcher.invalidate()


router = APIRouter(prefix="/rules", tags=["rules"])


@router.post(
    "",
    response_model=RuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create alert rule",
    description="Create a new alert rule for the authenticated user's organization.",
)
async def create_rule(
    request: Request,
    body: RuleCreate,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> RuleResponse:
    """Create a new alert rule."""
    try:
        _validate_scope_targets_for_type(body.scope_type, body.scope_targets)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    service = RuleService(session)
    rule = await service.create_rule(
        name=body.name,
        description=body.description,
        trigger_type=body.trigger_type.value,
        trigger_config=body.trigger_config,
        scope_type=body.scope_type.value,
        scope_targets=body.scope_targets,
        severity=body.severity.value,
        labels=body.labels,
        annotations=body.annotations,
        enabled=body.enabled,
        organization_id=user.organization_id,
        created_by=user.user_id,
    )

    # Capture key fields immediately while rule attributes are fresh.
    # After subsequent commits or rollbacks the ORM object's attributes
    # expire, and accessing them in a sync context triggers MissingGreenlet
    # with async drivers (asyncpg).
    rule_id = rule.id
    rule_name = rule.name

    # Save actions if provided (best-effort: rule creation succeeds even
    # if action table is unavailable)
    if body.actions:
        try:
            actions_data = [
                {
                    "action_type": a.action_type.value,
                    "action_config": a.action_config,
                    "order_index": a.order_index,
                    "enabled": a.enabled,
                }
                for a in body.actions
            ]
            await action_service.sync_actions(session, rule_id, actions_data)
        except Exception as exc:
            await session.rollback()
            logger.warning(
                "Failed to save actions for rule %s: %s", rule_id, exc
            )

    # Build response AFTER actions are saved so they're included
    response = await _build_rule_response(rule, session)

    # Log the creation in audit trail (best-effort: don't fail the request
    # if the audit table is unavailable or the insert fails)
    try:
        audit_service = RuleAuditService(session)
        rule_snapshot = response.model_dump(mode="json")
        await audit_service.log_rule_created(
            rule_id=rule_id,
            rule_name=rule_name,
            user_id=user.user_id,
            user_email=user.email,
            organization_id=user.organization_id,
            rule_snapshot=rule_snapshot,
        )
    except Exception as exc:
        await session.rollback()
        logger.warning(
            "Failed to write audit log for rule %s: %s", rule_id, exc
        )

    await _invalidate_rule_cache(request, reason="rule_created")
    logger.info("Created rule %s by user %s", rule_id, user.user_id)
    return response


@router.get(
    "",
    response_model=RuleListResponse,
    summary="List alert rules",
    description="List all alert rules for the authenticated user's organization.",
)
async def list_rules(
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
    enabled_only: bool = Query(False, description="Filter to enabled rules only"),
    scope_type: Optional[str] = Query(None, description="Filter by scope type"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=500, description="Pagination limit"),
) -> RuleListResponse:
    """List alert rules for the user's organization."""
    service = RuleService(session)
    rules, total = await service.list_rules(
        user.organization_id,
        enabled_only=enabled_only,
        scope_type=scope_type,
        offset=offset,
        limit=limit,
    )
    # Filter rules to only those the user can access
    filtered_rules = await filter_rules_by_access(user, list(rules))
    actions_by_rule: Dict[str, List[Any]] = {}
    if filtered_rules:
        try:
            actions_by_rule = await action_service.get_actions_for_rules(
                session,
                [rule.id for rule in filtered_rules],
                enabled_only=False,
            )
        except Exception as exc:
            logger.warning("Failed to batch load actions for rules list: %s", exc)

    items = [
        _build_rule_response_from_actions(rule, actions_by_rule.get(rule.id, []))
        for rule in filtered_rules
    ]
    return RuleListResponse(
        items=items,
        total=len(filtered_rules),
        maxRules=None,
        hostCount=None,
        rulesPerHost=None,
    )


@router.get(
    "/usage",
    response_model=RuleUsageResponse,
    summary="Get rule usage",
    description="Get current rule usage and runtime rule limits for the authenticated user's organization.",
)
async def get_rule_usage(
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> RuleUsageResponse:
    """Get current rule usage and limits."""
    service = RuleService(session)
    current_rules = await service.count_rules(user.organization_id)
    role = user.roles[0] if user.roles else None

    return RuleUsageResponse(
        edition="source_available",
        usage=RuleUsageCounts(rules=current_rules, alertHistory=0),
        limits=RuleUsageLimits(
            maxRules=None,
            alertHistoryLimit=None,
            hostCount=None,
            rulesPerHost=None,
        ),
        user=RuleUsageUser(id=user.user_id, email=user.email, role=role),
    )


@router.post(
    "/bulk-toggle",
    response_model=BulkToggleResponse,
    summary="Bulk toggle rules",
    description="Toggle enabled state for multiple rules at once.",
)
async def bulk_toggle_rules(
    request: Request,
    body: BulkToggleRequest,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> BulkToggleResponse:
    """Toggle enabled state for multiple rules in a single transaction."""
    service = RuleService(session)
    audit_service = RuleAuditService(session)

    updated_count = 0
    errors = []

    for rule_id in body.rule_ids:
        try:
            # Fetch rule to verify ownership and access
            rule = await service.get_rule_or_raise(rule_id, user.organization_id)
            rule_name = rule.name  # capture before commits expire ORM object

            # Toggle the rule
            await service.toggle_rule(
                rule_id,
                user.organization_id,
                enabled=body.enabled,
                updated_by=user.user_id,
            )

            updated_count += 1

            # Log audit event (best-effort)
            try:
                await audit_service.log_rule_toggled(
                    rule_id=rule_id,
                    rule_name=rule_name,
                    user_id=user.user_id,
                    user_email=user.email,
                    organization_id=user.organization_id,
                    enabled=body.enabled,
                )
            except Exception as exc:
                await session.rollback()
                logger.warning(
                    "Failed to write audit log for rule %s toggle: %s",
                    rule_id, exc,
                )
        except RuleNotFoundError:
            errors.append(f"Rule {rule_id} not found")
        except Exception as e:
            errors.append(f"Rule {rule_id}: {str(e)}")

    await _invalidate_rule_cache(request, reason="rule_bulk_toggle")
    logger.info(
        "Bulk toggle by user %s: %d updated, %d errors",
        user.user_id,
        updated_count,
        len(errors),
    )

    return BulkToggleResponse(updated=updated_count, errors=errors)


@router.get(
    "/{rule_id}",
    response_model=RuleResponse,
    summary="Get alert rule",
    description="Get a specific alert rule by ID.",
)
async def get_rule(
    rule_id: str,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> RuleResponse:
    """Get a single alert rule by ID."""
    service = RuleService(session)
    try:
        rule = await service.get_rule_or_raise(rule_id, user.organization_id)
    except RuleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {rule_id} not found",
        )
    # Verify user has access to this rule's scope_targets
    await validate_scope_access(user, rule.scope_type, rule.scope_targets or [])
    return await _build_rule_response(rule, session)


@router.patch(
    "/{rule_id}",
    response_model=RuleResponse,
    summary="Update alert rule",
    description="Update an existing alert rule.",
)
async def update_rule(
    rule_id: str,
    body: RuleUpdate,
    request: Request,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> RuleResponse:
    """Update an existing alert rule."""
    service = RuleService(session)

    # Fetch current rule first to check access and determine new scope values
    try:
        current_rule = await service.get_rule_or_raise(rule_id, user.organization_id)
    except RuleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {rule_id} not found",
        )

    # Validate access to current rule's scope
    await validate_scope_access(
        user, current_rule.scope_type, current_rule.scope_targets or []
    )

    # Build update kwargs from non-None values
    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    if body.trigger_type is not None:
        updates["trigger_type"] = body.trigger_type.value
    if body.trigger_config is not None:
        updates["trigger_config"] = body.trigger_config
    if body.scope_type is not None:
        updates["scope_type"] = body.scope_type.value
    if body.scope_targets is not None:
        updates["scope_targets"] = body.scope_targets
    if body.severity is not None:
        updates["severity"] = body.severity.value
    if body.labels is not None:
        updates["labels"] = body.labels
    if body.annotations is not None:
        updates["annotations"] = body.annotations
    if body.enabled is not None:
        updates["enabled"] = body.enabled

    # If scope is being changed, validate access to the NEW scope values
    if body.scope_type is not None or body.scope_targets is not None:
        new_scope_type = body.scope_type.value if body.scope_type else current_rule.scope_type
        new_scope_targets = body.scope_targets if body.scope_targets is not None else current_rule.scope_targets or []
        try:
            _validate_scope_targets_for_type(new_scope_type, new_scope_targets)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        await validate_scope_access(user, new_scope_type, new_scope_targets)

    # Compute changes for audit logging
    changes = _compute_changes(current_rule, updates)

    try:
        rule = await service.update_rule(
            rule_id,
            user.organization_id,
            **updates,
            updated_by=user.user_id,
        )
    except RuleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {rule_id} not found",
        )

    # Sync actions if provided in the update (best-effort)
    if body.actions is not None:
        try:
            actions_data = [
                {
                    "action_type": a.action_type.value,
                    "action_config": a.action_config,
                    "order_index": a.order_index,
                    "enabled": a.enabled,
                }
                for a in body.actions
            ]
            await action_service.sync_actions(session, rule_id, actions_data)
        except Exception as exc:
            await session.rollback()
            logger.warning(
                "Failed to sync actions for rule %s: %s", rule_id, exc
            )

    # Build response AFTER actions are synced so they're included
    response = await _build_rule_response(rule, session)

    # Log the update in audit trail (best-effort)
    if changes:
        try:
            audit_service = RuleAuditService(session)
            await audit_service.log_rule_updated(
                rule_id=response.id,
                rule_name=response.name,
                user_id=user.user_id,
                user_email=user.email,
                organization_id=user.organization_id,
                changes=changes,
            )
        except Exception as exc:
            await session.rollback()
            logger.warning(
                "Failed to write audit log for rule %s update: %s",
                rule_id, exc,
            )

    await _invalidate_rule_cache(request, reason="rule_updated")
    logger.info("Updated rule %s by user %s", rule_id, user.user_id)
    return response


@router.post(
    "/{rule_id}/convert-to-custom",
    response_model=ConvertToCustomResponse,
    summary="Convert template rule to custom",
    description="Remove template_source label from a template-based rule to make it editable.",
)
async def convert_to_custom(
    rule_id: str,
    request: Request,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> ConvertToCustomResponse:
    """Convert a template-based rule to a custom rule by removing template_source."""
    service = RuleService(session)

    try:
        # Fetch current rule
        rule = await service.get_rule_or_raise(rule_id, user.organization_id)
    except RuleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {rule_id} not found",
        )

    # Validate access to rule's scope
    await validate_scope_access(user, rule.scope_type, rule.scope_targets or [])

    # Check if rule has template_source
    if "template_source" not in (rule.labels or {}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rule is not a template rule",
        )

    # Remove template_source from labels
    updated_labels = dict(rule.labels or {})
    del updated_labels["template_source"]

    # Update rule
    rule = await service.update_rule(
        rule_id,
        user.organization_id,
        labels=updated_labels,
        updated_by=user.user_id,
    )

    # Build response with actions loaded
    rule_response = await _build_rule_response(rule, session)

    # Log audit event (best-effort)
    try:
        audit_service = RuleAuditService(session)
        await audit_service.log_rule_updated(
            rule_id=rule_response.id,
            rule_name=rule_response.name,
            user_id=user.user_id,
            user_email=user.email,
            organization_id=user.organization_id,
            changes={
                "labels": {
                    "old": {**updated_labels, "template_source": "removed"},
                    "new": updated_labels,
                }
            },
        )
    except Exception as exc:
        await session.rollback()
        logger.warning(
            "Failed to write audit log for rule %s convert-to-custom: %s",
            rule_id, exc,
        )

    await _invalidate_rule_cache(request, reason="rule_converted_to_custom")
    logger.info("Converted rule %s to custom by user %s", rule_id, user.user_id)
    return ConvertToCustomResponse(
        status="success",
        message="Rule converted to custom successfully",
        rule=rule_response,
    )


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete alert rule",
    description="Delete an alert rule.",
)
async def delete_rule(
    rule_id: str,
    request: Request,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete an alert rule."""
    service = RuleService(session)
    try:
        # Defense-in-depth: fetch rule first to verify org ownership
        rule = await service.get_rule_or_raise(rule_id, user.organization_id)
        # Defense-in-depth: explicit org check (service already checks, but this is belt-and-suspenders)
        if rule.organization_id != user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Rule {rule_id} not found",
            )

        # Capture snapshot before deletion with actions included
        rule_snapshot = (await _build_rule_response(rule, session)).model_dump(mode="json")
        rule_name = rule.name

        await service.delete_rule(rule_id, user.organization_id)

        # Log the deletion in audit trail (best-effort)
        try:
            audit_service = RuleAuditService(session)
            await audit_service.log_rule_deleted(
                rule_id=rule_id,
                rule_name=rule_name,
                user_id=user.user_id,
                user_email=user.email,
                organization_id=user.organization_id,
                rule_snapshot=rule_snapshot,
            )
        except Exception as exc:
            await session.rollback()
            logger.warning(
                "Failed to write audit log for rule %s deletion: %s",
                rule_id, exc,
            )
    except RuleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {rule_id} not found",
        )
    await _invalidate_rule_cache(request, reason="rule_deleted")
    logger.info("Deleted rule %s by user %s", rule_id, user.user_id)


@router.post(
    "/{rule_id}/enable",
    response_model=RuleResponse,
    summary="Enable alert rule",
    description="Enable a disabled alert rule.",
)
async def enable_rule(
    rule_id: str,
    request: Request,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> RuleResponse:
    """Enable an alert rule."""
    service = RuleService(session)
    try:
        # Defense-in-depth: fetch rule first to verify org ownership
        existing_rule = await service.get_rule_or_raise(rule_id, user.organization_id)
        # Defense-in-depth: explicit org check
        if existing_rule.organization_id != user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Rule {rule_id} not found",
            )
        rule = await service.toggle_rule(
            rule_id, user.organization_id, enabled=True, updated_by=user.user_id
        )

        # Build response with actions loaded
        response = await _build_rule_response(rule, session)

        # Log the enable action in audit trail (best-effort)
        try:
            audit_service = RuleAuditService(session)
            await audit_service.log_rule_toggled(
                rule_id=response.id,
                rule_name=response.name,
                user_id=user.user_id,
                user_email=user.email,
                organization_id=user.organization_id,
                enabled=True,
            )
        except Exception as exc:
            await session.rollback()
            logger.warning(
                "Failed to write audit log for rule %s enable: %s",
                rule_id, exc,
            )
    except RuleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {rule_id} not found",
        )
    await _invalidate_rule_cache(request, reason="rule_toggle_enable")
    logger.info("Enabled rule %s by user %s", rule_id, user.user_id)
    return response


@router.post(
    "/{rule_id}/disable",
    response_model=RuleResponse,
    summary="Disable alert rule",
    description="Disable an enabled alert rule.",
)
async def disable_rule(
    rule_id: str,
    request: Request,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> RuleResponse:
    """Disable an alert rule."""
    service = RuleService(session)
    try:
        # Defense-in-depth: fetch rule first to verify org ownership
        existing_rule = await service.get_rule_or_raise(rule_id, user.organization_id)
        # Defense-in-depth: explicit org check
        if existing_rule.organization_id != user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Rule {rule_id} not found",
            )
        rule = await service.toggle_rule(
            rule_id, user.organization_id, enabled=False, updated_by=user.user_id
        )

        # Build response with actions loaded
        response = await _build_rule_response(rule, session)

        # Log the disable action in audit trail (best-effort)
        try:
            audit_service = RuleAuditService(session)
            await audit_service.log_rule_toggled(
                rule_id=response.id,
                rule_name=response.name,
                user_id=user.user_id,
                user_email=user.email,
                organization_id=user.organization_id,
                enabled=False,
            )
        except Exception as exc:
            await session.rollback()
            logger.warning(
                "Failed to write audit log for rule %s disable: %s",
                rule_id, exc,
            )
    except RuleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {rule_id} not found",
        )
    await _invalidate_rule_cache(request, reason="rule_toggle_disable")
    logger.info("Disabled rule %s by user %s", rule_id, user.user_id)
    return response


@router.post(
    "/test",
    response_model=DryRunResult,
    summary="Test rule configuration",
    description="Test a rule configuration in dry-run mode without saving.",
)
async def test_rule_config(
    body: DryRunRequest,
    user: UserContext = Depends(require_authenticated_user),
) -> DryRunResult:
    """
    Test a rule configuration in dry-run mode without saving.

    This endpoint allows users to validate rule configurations before creating
    or updating rules. No database writes occur, no alerts are created.
    """
    # Create temporary rule object for evaluation
    temp_rule = AlertRule(
        id=f"dryrun-{uuid.uuid4().hex[:8]}",
        name=body.name,
        trigger_type=body.trigger_type.value,
        trigger_config=body.trigger_config,
        scope_type=body.scope_type.value,
        scope_targets=body.scope_targets,
        severity=body.severity.value,
        labels={},
        annotations={},
        organization_id=user.organization_id,
        enabled=True,
    )

    # Evaluate without triggering real alerts
    evaluator = RuleEvaluator()
    result = await evaluator.evaluate_rule(temp_rule)

    # Extract sample matches from context if available
    sample_matches = []
    if result.context.get("matching_log"):
        sample_matches.append(result.context["matching_log"])

    logger.info(
        "Dry-run test by user %s: rule='%s', triggered=%s",
        user.user_id,
        body.name,
        result.triggered,
    )

    return DryRunResult(
        rule_id=temp_rule.id,
        triggered=result.triggered,
        value=result.value,
        message=result.message,
        context=result.context,
        evaluated_at=result.evaluated_at,
        logs_checked=result.context.get("count", 0),
        sample_matches=sample_matches,
    )


@router.post(
    "/{rule_id}/test",
    response_model=DryRunResult,
    summary="Test existing rule",
    description="Test an existing rule in dry-run mode without creating alerts.",
)
async def test_existing_rule(
    rule_id: str,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> DryRunResult:
    """
    Test an existing rule in dry-run mode without creating alerts.

    This endpoint allows users to verify how an existing rule would evaluate
    against current data. No alerts are created, no state is modified.
    """
    # Fetch the rule
    service = RuleService(session)
    try:
        rule = await service.get_rule_or_raise(rule_id, user.organization_id)
    except RuleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {rule_id} not found",
        )

    # Evaluate without triggering real alerts
    evaluator = RuleEvaluator()
    result = await evaluator.evaluate_rule(rule)

    # Extract sample matches from context if available
    sample_matches = []
    if result.context.get("matching_log"):
        sample_matches.append(result.context["matching_log"])

    logger.info(
        "Dry-run test by user %s: rule_id=%s, triggered=%s",
        user.user_id,
        rule_id,
        result.triggered,
    )

    return DryRunResult(
        rule_id=rule.id,
        triggered=result.triggered,
        value=result.value,
        message=result.message,
        context=result.context,
        evaluated_at=result.evaluated_at,
        logs_checked=result.context.get("count", 0),
        sample_matches=sample_matches,
    )


__all__ = ["router"]
