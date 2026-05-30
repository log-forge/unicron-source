"""REST API endpoints for rule template operations."""

import hashlib
import json
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import UserContext, require_authenticated_user
from app.core.logging import get_logger
from app.models.action import RuleAction
from app.schemas.template_schemas import (
    ActivationResponse,
    DuplicateCheckRequest,
    DuplicateCheckResponse,
    SimilarRuleInfo,
    TemplateActivationRequest,
    TemplatesByCategoryResponse,
)
from app.services.action_service import action_service
from app.services.rule_audit_service import RuleAuditService
from app.services.rule_service import (
    AlertRule,
    RuleService,
)
from app.services.template_service import (
    get_template_by_id,
    get_templates_by_category,
)

logger = get_logger("alert-engine.routes.templates")

router = APIRouter(prefix="/rule-templates", tags=["templates"])


async def _invalidate_rule_cache(request: Request, *, reason: str) -> None:
    """Invalidate RuleMatcher cache after template-driven rule mutations."""
    rule_matcher = getattr(request.app.state, "rule_matcher", None)
    if rule_matcher is not None:
        publish = getattr(rule_matcher, "publish_invalidation", None)
        if callable(publish):
            await publish(reason=reason)
        else:
            rule_matcher.invalidate()


# Helper functions for duplicate detection
def normalize_scope(scope_type: str, scope_targets: List[str]) -> str:
    """Normalize scope for fingerprinting."""
    if scope_type == "global":
        return "global"
    # Sort targets for consistent fingerprinting
    sorted_targets = sorted(scope_targets)
    return f"{scope_type}:{','.join(sorted_targets)}"


def normalize_trigger_config(
    trigger_type: str,
    trigger_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Normalize trigger configuration for fingerprinting."""
    normalized = {"trigger_type": trigger_type}

    if trigger_type == "keyword":
        # Normalize pattern to lowercase for consistent fingerprinting
        pattern = trigger_config.get("pattern", "")
        normalized["pattern"] = str(pattern).lower().strip()
        normalized["is_regex"] = trigger_config.get("is_regex", False)

    elif trigger_type == "threshold":
        # Extract core threshold parameters
        normalized["metric"] = trigger_config.get("metric", "").lower()
        normalized["operator"] = trigger_config.get("operator", "gt")
        normalized["value"] = float(trigger_config.get("value", 0))
        normalized["duration_seconds"] = trigger_config.get("duration_seconds", 60)

    elif trigger_type == "rate":
        # Extract core rate parameters
        normalized["pattern"] = trigger_config.get("pattern", "")
        normalized["threshold"] = trigger_config.get("threshold", 1)
        normalized["window_seconds"] = trigger_config.get("window_seconds", 60)

    elif trigger_type == "absence":
        # Extract core absence parameters
        normalized["pattern"] = trigger_config.get("pattern", "")
        normalized["window_seconds"] = trigger_config.get("window_seconds", 60)

    return normalized


def normalize_actions(actions: List[RuleAction]) -> List[Dict[str, Any]]:
    """Normalize actions for fingerprinting."""
    if not actions:
        return []

    normalized = []
    for action in actions:
        normalized_action = {"type": action.action_type}
        normalized.append(normalized_action)

    # Sort by type for consistent ordering
    return sorted(normalized, key=lambda x: x["type"])


def _collect_notify_targets(
    action_config: Dict[str, Any] | None,
    customizations: Dict[str, Any] | None,
) -> Dict[str, List[str]]:
    """Collect normalized notification targets from template/config inputs."""
    action_cfg = action_config if isinstance(action_config, dict) else {}
    custom_cfg = customizations if isinstance(customizations, dict) else {}

    targets: Dict[str, List[str]] = {
        "channel_ids": [],
        "group_ids": [],
        "preset_ids": [],
    }
    seen: Dict[str, set[str]] = {key: set() for key in targets}

    def add_target(target_key: str, value: Any) -> None:
        target_id = str(value or "").strip()
        if not target_id or target_id in seen[target_key]:
            return
        seen[target_key].add(target_id)
        targets[target_key].append(target_id)

    def add_many(target_key: str, values: Any) -> None:
        if not isinstance(values, list):
            return
        for item in values:
            add_target(target_key, item)

    for raw_ids in (
        action_cfg.get("channel_ids"),
        custom_cfg.get("channel_ids"),
    ):
        add_many("channel_ids", raw_ids)

    for source in (action_cfg, custom_cfg):
        add_many("group_ids", source.get("group_ids"))
        add_many("preset_ids", source.get("preset_ids"))

    return {key: value for key, value in targets.items() if value}


def generate_rule_fingerprint(
    rule: AlertRule, actions: List[RuleAction]
) -> str:
    """Generate fingerprint for duplicate detection."""
    fingerprint_data = {
        "scope": normalize_scope(rule.scope_type, rule.scope_targets),
        "condition": normalize_trigger_config(rule.trigger_type, rule.trigger_config),
        "actions": normalize_actions(actions),
    }

    # Create consistent JSON representation
    json_str = json.dumps(fingerprint_data, sort_keys=True, separators=(",", ":"))

    # Generate hash
    return hashlib.sha256(json_str.encode()).hexdigest()[:16]  # Short hash


def check_overlapping_scopes(
    scope1_type: str, scope1_targets: List[str], scope2_type: str, scope2_targets: List[str]
) -> bool:
    """Check if two rule scopes overlap."""
    # Global rules overlap with everything
    if scope1_type == "global" or scope2_type == "global":
        return True

    # Same type - check for target overlap
    if scope1_type == scope2_type:
        targets1_set = set(scope1_targets)
        targets2_set = set(scope2_targets)
        return bool(targets1_set & targets2_set)  # Any intersection

    # Different scope types - no overlap (container vs group vs herald)
    return False


async def find_similar_rules(
    session: AsyncSession,
    organization_id: str,
    new_rule: AlertRule,
    new_actions: List[RuleAction],
) -> Optional[AlertRule]:
    """Find existing rule that is similar to the new rule."""
    new_fingerprint = generate_rule_fingerprint(new_rule, new_actions)

    # Get all existing rules for this organization
    rule_service = RuleService(session)
    existing_rules, _ = await rule_service.list_rules(organization_id=organization_id)

    if not existing_rules:
        return None

    # Batch-load actions for ALL rules in a single query (fixes N+1)
    rule_ids = [r.id for r in existing_rules]
    actions_by_rule = await action_service.get_actions_for_rules(session, rule_ids)

    # Check each existing rule
    for existing_rule in existing_rules:
        existing_actions = actions_by_rule.get(existing_rule.id, [])
        existing_fingerprint = generate_rule_fingerprint(existing_rule, existing_actions)

        if new_fingerprint == existing_fingerprint:
            if check_overlapping_scopes(
                new_rule.scope_type,
                new_rule.scope_targets,
                existing_rule.scope_type,
                existing_rule.scope_targets,
            ):
                return existing_rule

    return None


def convert_template_to_trigger_config(template: Dict[str, Any], customizations: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    """
    Convert LogForge template format to Unicron trigger_config format.

    Returns:
        Tuple of (trigger_type, trigger_config)
    """
    template_trigger_type = template["trigger_type"]
    template_trigger_value = template["trigger_value"]

    # KEYWORD triggers - direct translation
    if template_trigger_type == "keyword":
        keyword = customizations.get("keyword", template_trigger_value)
        trigger_type = "keyword"
        trigger_config = {
            "pattern": keyword,
            "is_regex": False,
            "case_sensitive": False,
        }
        return trigger_type, trigger_config

    # METRIC_THRESHOLD triggers - translate to THRESHOLD
    elif template_trigger_type == "metric_threshold":
        # Template has trigger_value as dict with metric_type, threshold, operator
        metric_type = template_trigger_value.get("metric_type", "cpu_percent")
        threshold = customizations.get("threshold", template_trigger_value.get("threshold", 80.0))
        operator_map = {">": "gt", ">=": "gte", "<": "lt", "<=": "lte", "==": "eq", "!=": "ne"}
        operator = operator_map.get(template_trigger_value.get("operator", ">"), "gt")

        # Convert timeline_minutes to duration_seconds
        timeline_minutes = customizations.get("timeline_minutes", template.get("timeline_minutes", 5))
        duration_seconds = timeline_minutes * 60 if timeline_minutes else 60

        trigger_type = "threshold"
        trigger_config = {
            "metric": metric_type,
            "operator": operator,
            "value": float(threshold),
            "duration_seconds": duration_seconds,
        }
        return trigger_type, trigger_config

    # CONTAINER_EVENT triggers - keep as container_event
    elif template_trigger_type == "container_event":
        # Template has trigger_value as event name (start, stop, etc.)
        # Also has timeline_minutes and timeline_count for count-in-window detection
        event_name = customizations.get("trigger_value", template_trigger_value)
        timeline_minutes = customizations.get("timeline_minutes", template.get("timeline_minutes", 5))
        timeline_count = customizations.get("timeline_count", template.get("timeline_count", 3))

        trigger_type = "container_event"
        trigger_config = {
            "trigger_value": event_name,
            "timeline_minutes": timeline_minutes,
            "timeline_count": timeline_count,
        }
        return trigger_type, trigger_config

    else:
        # Unsupported trigger type
        raise ValueError(f"Unsupported template trigger type: {template_trigger_type}")


@router.get(
    "",
    response_model=TemplatesByCategoryResponse,
    summary="Get rule templates",
    description="Get all available rule templates organized by category.",
)
async def get_rule_templates() -> TemplatesByCategoryResponse:
    """Get all available rule templates organized by category."""
    try:
        templates = get_templates_by_category()
        return TemplatesByCategoryResponse(templates=templates)
    except Exception as e:
        logger.error(f"Error getting rule templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{template_id}/activate",
    response_model=ActivationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Activate rule template",
    description="Activate a rule template with customizations.",
)
async def activate_template(
    template_id: str,
    request: Request,
    body: TemplateActivationRequest,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> ActivationResponse:
    """Activate a rule template with customizations."""
    try:
        # Get template definition
        template = get_template_by_id(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        # Determine rule name
        rule_name = body.rule_name if body.rule_name else template["name"]

        # Enforce name length limit
        if len((rule_name or "").strip()) > 255:
            raise HTTPException(status_code=400, detail="Rule name exceeds 255 characters")

        # Convert template to Unicron format
        trigger_type, trigger_config = convert_template_to_trigger_config(
            template, body.customizations
        )

        # Generate unique rule ID with template prefix
        rule_id = f"tpl_{template_id}_{uuid.uuid4().hex[:8]}"

        # Generate auto-tags from template
        auto_tags = set(template.get("tags", []))
        auto_tags.add("Template")
        if template.get("category"):
            auto_tags.add(template["category"].capitalize())

        # Merge with custom tags
        all_tags = sorted(list(auto_tags | set(body.custom_tags)))

        # Create labels with tags
        labels = {"tags": ",".join(all_tags), "template_source": template_id}

        # Create the rule
        rule_service = RuleService(session)
        rule = await rule_service.create_rule(
            name=rule_name,
            description=template["description"],
            trigger_type=trigger_type,
            trigger_config=trigger_config,
            scope_type=body.scope_type,
            scope_targets=body.scope_targets,
            severity="warning",  # Default severity for templates
            labels=labels,
            annotations={},
            enabled=True,
            organization_id=user.organization_id,
            created_by=user.user_id,
        )

        # Create actions from template
        template_actions = template.get("actions", [])

        for order_index, template_action in enumerate(template_actions):
            action_type = template_action["type"]
            template_action_config = (
                template_action.get("config")
                if isinstance(template_action.get("config"), dict)
                else {}
            )

            # Map LogForge action types to Unicron action types
            action_type_map = {
                "restart_container": "restart",
                "stop_container": "stop",
                "start_container": "start",
                "kill_container": "kill",
                "notification": "notify",
                "run_script": "run_script",
            }
            unicron_action_type = action_type_map.get(action_type, action_type)

            # Build action config
            action_config = {}
            if unicron_action_type == "notify":
                notify_targets = _collect_notify_targets(
                    template_action_config,
                    body.customizations,
                )
                if notify_targets:
                    action_config = notify_targets
                message_template = (
                    template_action_config.get("message_template")
                    if isinstance(template_action_config, dict)
                    else None
                )
                if isinstance(message_template, str) and message_template.strip():
                    action_config["message_template"] = message_template.strip()
            elif unicron_action_type in ["restart", "stop", "start", "kill"]:
                # Container actions
                action_config = {
                    "timeout_seconds": int(template_action_config.get("timeout_seconds", 30) or 30),
                    "force": bool(template_action_config.get("force", False)),
                }
            elif unicron_action_type == "run_script":
                # Script actions would need script content
                action_config = {
                    "script": str(template_action_config.get("script") or "# Script content here"),
                    "interpreter": str(template_action_config.get("interpreter") or "/bin/sh"),
                    "timeout_seconds": int(template_action_config.get("timeout_seconds", 60) or 60),
                }

            # Create the action (session as first positional arg)
            await action_service.create_action(
                session,
                rule_id=rule.id,
                action_type=unicron_action_type,
                action_config=action_config,
                order_index=order_index,
                enabled=True,
            )

        # Log the creation in audit trail
        audit_service = RuleAuditService(session)
        await audit_service.log_rule_created(
            rule_id=rule.id,
            rule_name=rule.name,
            user_id=user.user_id,
            user_email=user.email,
            organization_id=user.organization_id,
            rule_snapshot={
                "id": rule.id,
                "name": rule.name,
                "template_source": template_id,
                "scope_type": body.scope_type,
                "scope_targets": body.scope_targets,
            },
        )

        logger.info("Activated template %s as rule %s by user %s", template_id, rule.id, user.user_id)
        await _invalidate_rule_cache(request, reason="template_activated")

        return ActivationResponse(
            status="success",
            message=f"Template '{template['name']}' activated successfully",
            rule_id=rule.id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating template: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{template_id}/check-duplicate",
    response_model=DuplicateCheckResponse,
    summary="Check for duplicate rules",
    description="Check if activating a template would create a duplicate rule.",
)
async def check_duplicate_rule(
    template_id: str,
    body: DuplicateCheckRequest,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> DuplicateCheckResponse:
    """Check if activating a template would create a duplicate rule."""
    try:
        # Get template definition
        template = get_template_by_id(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        # Convert template to Unicron format
        trigger_type, trigger_config = convert_template_to_trigger_config(
            template, body.customizations
        )

        # Create a prospective rule for comparison (not saved to DB)
        prospective_rule = AlertRule(
            id="prospective",
            name=body.rule_name or template["name"],
            description=template["description"],
            trigger_type=trigger_type,
            trigger_config=trigger_config,
            scope_type=body.scope_type,
            scope_targets=body.scope_targets,
            organization_id=user.organization_id,
        )

        # Create prospective actions for comparison
        prospective_actions = []
        template_actions = template.get("actions", [])
        for template_action in template_actions:
            action_type = template_action["type"]
            action_type_map = {
                "restart_container": "restart",
                "stop_container": "stop",
                "start_container": "start",
                "kill_container": "kill",
                "notification": "notify",
                "run_script": "run_script",
            }
            unicron_action_type = action_type_map.get(action_type, action_type)

            prospective_actions.append(
                RuleAction(
                    id="prospective",
                    rule_id="prospective",
                    action_type=unicron_action_type,
                    action_config={},
                    order_index=0,
                )
            )

        # Find similar rules
        similar_rule = await find_similar_rules(
            session, user.organization_id, prospective_rule, prospective_actions
        )

        if similar_rule:
            return DuplicateCheckResponse(
                is_duplicate=True,
                similar_rule=SimilarRuleInfo(
                    id=similar_rule.id,
                    name=similar_rule.name,
                    scope_type=similar_rule.scope_type,
                    scope_targets=similar_rule.scope_targets,
                ),
            )
        else:
            return DuplicateCheckResponse(is_duplicate=False, similar_rule=None)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking duplicate: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
