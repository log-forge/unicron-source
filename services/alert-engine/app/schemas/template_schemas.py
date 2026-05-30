"""Pydantic schemas for rule template operations."""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class TemplateCategory(str, Enum):
    """Categories for rule templates."""

    STABILITY = "stability"
    PERFORMANCE = "performance"
    LOGS = "logs"
    SECURITY = "security"


class ActionConfig(BaseModel):
    """Action configuration for template."""

    type: str = Field(..., description="Action type (notification, restart_container, etc.)")
    config: Dict[str, Any] = Field(default_factory=dict, description="Action-specific configuration")
    delay_seconds: Optional[int] = Field(default=None, description="Delay before executing action")


class RuleTemplateSchema(BaseModel):
    """Schema for a rule template."""

    id: str = Field(..., description="Template identifier")
    name: str = Field(..., description="Template name")
    description: str = Field(..., description="Template description")
    category: str = Field(..., description="Template category")
    trigger_type: str = Field(..., description="Trigger type (keyword, metric_threshold, container_event)")
    trigger_value: Any = Field(..., description="Trigger value (can be string or dict)")
    timeline_minutes: Optional[int] = Field(default=None, description="Timeline window in minutes")
    timeline_count: Optional[int] = Field(default=None, description="Count threshold within timeline")
    actions: List[ActionConfig] = Field(default_factory=list, description="List of actions to execute")
    customizable_fields: List[str] = Field(default_factory=list, description="Fields that can be customized")
    required_metrics: List[str] = Field(default_factory=list, description="Required metrics for this template")
    tags: List[str] = Field(default_factory=list, description="Template tags")


class TemplatesByCategoryResponse(BaseModel):
    """Response schema for GET /rule-templates."""

    templates: Dict[str, List[RuleTemplateSchema]] = Field(..., description="Templates organized by category")


class TemplateActivationRequest(BaseModel):
    """Request schema for activating a template."""

    rule_name: Optional[str] = Field(default=None, description="Custom name for the rule (defaults to template name)")
    scope_type: Literal["global", "container", "group", "herald"] = Field(..., description="Scope type for the rule")
    scope_targets: List[str] = Field(default_factory=list, description="Scope targets (container IDs, group IDs, or herald names)")
    customizations: Dict[str, Any] = Field(default_factory=dict, description="Field customizations (threshold, keyword, timeline_minutes, etc.)")
    custom_tags: List[str] = Field(default_factory=list, description="Additional custom tags")


class ActivationResponse(BaseModel):
    """Response schema for template activation."""

    status: str = Field(..., description="Operation status")
    message: str = Field(..., description="Human-readable message")
    rule_id: str = Field(..., description="ID of the created rule")


class DuplicateCheckRequest(BaseModel):
    """Request schema for checking duplicate rules."""

    scope_type: Literal["global", "container", "group", "herald"] = Field(..., description="Scope type for the rule")
    scope_targets: List[str] = Field(default_factory=list, description="Scope targets")
    customizations: Dict[str, Any] = Field(default_factory=dict, description="Field customizations")
    rule_name: Optional[str] = Field(default=None, description="Rule name")


class SimilarRuleInfo(BaseModel):
    """Information about a similar rule."""

    id: str = Field(..., description="Rule ID")
    name: str = Field(..., description="Rule name")
    scope_type: str = Field(..., description="Rule scope type")
    scope_targets: List[str] = Field(..., description="Rule scope targets")


class DuplicateCheckResponse(BaseModel):
    """Response schema for duplicate check."""

    is_duplicate: bool = Field(..., description="Whether a duplicate rule exists")
    similar_rule: Optional[SimilarRuleInfo] = Field(default=None, description="Information about similar rule if found")
