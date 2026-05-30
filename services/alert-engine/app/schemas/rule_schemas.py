"""Pydantic schemas for alert rule CRUD operations with trigger-specific validation."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.action_schemas import ActionCreate, ActionResponse, ActionUpdate


# Enums for constrained values
class TriggerType(str, Enum):
    """Types of triggers for alert rules."""

    THRESHOLD = "threshold"
    KEYWORD = "keyword"
    RATE = "rate"
    ABSENCE = "absence"
    CONTAINER_EVENT = "container_event"


class ScopeType(str, Enum):
    """Scope types for alert rules."""

    GLOBAL = "global"
    CONTAINER = "container"
    GROUP = "group"
    HERALD = "herald"


class Severity(str, Enum):
    """Alert severity levels."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


def _normalize_scope_targets(raw_targets: List[str]) -> List[str]:
    """Trim, de-duplicate, and drop empty scope target entries."""
    normalized: List[str] = []
    seen = set()
    for target in raw_targets or []:
        value = str(target).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _is_container_key(value: str) -> bool:
    """Return True if value matches canonical container key host_id:container_name."""
    raw = (value or "").strip()
    if ":" not in raw:
        return False
    host_id, container_name = raw.split(":", 1)
    return bool(host_id.strip()) and bool(container_name.strip())


def _validate_scope_targets_for_type(scope_type: "ScopeType | str", scope_targets: List[str]) -> None:
    """Validate scope target shape for the given scope type."""
    resolved_scope: ScopeType
    if isinstance(scope_type, ScopeType):
        resolved_scope = scope_type
    else:
        resolved_scope = ScopeType(str(scope_type).lower())

    if resolved_scope == ScopeType.CONTAINER:
        invalid = [target for target in scope_targets if not _is_container_key(target)]
        if invalid:
            raise ValueError(
                "container scope targets must use host_id:container_name format"
            )
        return

    if resolved_scope == ScopeType.HERALD:
        invalid = [
            target for target in scope_targets
            if not target or ":" in target
        ]
        if invalid:
            raise ValueError(
                "herald scope targets must be host identifiers (no colon)"
            )
        return

    if resolved_scope == ScopeType.GROUP:
        invalid = [target for target in scope_targets if not target]
        if invalid:
            raise ValueError("group scope targets cannot be empty")
        return


# Trigger configuration schemas (discriminated by trigger_type)
class ThresholdConfig(BaseModel):
    """Configuration for threshold trigger."""

    metric: str = Field(
        ..., description="Metric name to monitor (e.g., 'cpu_percent', 'memory_usage')"
    )
    operator: Literal["gt", "gte", "lt", "lte", "eq", "ne"] = Field(
        ..., description="Comparison operator"
    )
    value: float = Field(..., description="Threshold value")
    duration_seconds: int = Field(
        default=60, ge=1, description="Duration the condition must be true"
    )


class KeywordConfig(BaseModel):
    """Configuration for keyword trigger."""

    pattern: str = Field(
        ..., min_length=1, description="Text pattern or regex to match"
    )
    is_regex: bool = Field(default=False, description="Whether pattern is a regex")
    case_sensitive: bool = Field(default=False, description="Case-sensitive matching")


class RateConfig(BaseModel):
    """Configuration for rate trigger."""

    pattern: Optional[str] = Field(
        default=None, description="Optional pattern to count"
    )
    threshold: int = Field(..., gt=0, description="Number of events to trigger")
    window_seconds: int = Field(default=60, ge=1, description="Time window in seconds")


class AbsenceConfig(BaseModel):
    """Configuration for absence trigger."""

    pattern: Optional[str] = Field(
        default=None, description="Expected pattern (optional)"
    )
    window_seconds: int = Field(
        ..., ge=60, description="Time window to expect events"
    )


class ContainerEventConfig(BaseModel):
    """Configuration for container_event trigger."""

    trigger_value: str = Field(
        default="", description="Event type to match (start, stop, restart, die)"
    )
    timeline_minutes: int = Field(
        default=5, ge=1, description="Rolling window size in minutes"
    )
    timeline_count: int = Field(
        default=3, ge=1, description="Minimum matching events required in the window"
    )

    model_config = {"extra": "allow"}


TriggerConfig = Union[
    ThresholdConfig,
    KeywordConfig,
    RateConfig,
    AbsenceConfig,
    ContainerEventConfig,
]


# Rule creation schema
class RuleCreate(BaseModel):
    """Schema for creating a new alert rule."""

    name: str = Field(
        ..., min_length=1, max_length=255, description="Rule name"
    )
    description: Optional[str] = Field(
        default=None, max_length=1000, description="Rule description"
    )

    trigger_type: TriggerType = Field(..., description="Type of trigger")
    trigger_config: Dict[str, Any] = Field(
        ..., description="Trigger-specific configuration"
    )

    scope_type: ScopeType = Field(
        default=ScopeType.GLOBAL, description="Scope type"
    )
    scope_targets: List[str] = Field(
        default_factory=list, description="Target IDs for scope"
    )

    severity: Severity = Field(
        default=Severity.WARNING, description="Alert severity"
    )
    labels: Dict[str, str] = Field(
        default_factory=dict, description="Custom labels"
    )
    annotations: Dict[str, str] = Field(
        default_factory=dict, description="Custom annotations"
    )

    enabled: bool = Field(default=True, description="Whether rule is enabled")

    actions: List[ActionCreate] = Field(
        default_factory=list, description="Remediation actions to execute when triggered"
    )

    @model_validator(mode="after")
    def validate_trigger_config(self):
        """Validate trigger_config matches trigger_type."""
        config_classes = {
            TriggerType.THRESHOLD: ThresholdConfig,
            TriggerType.KEYWORD: KeywordConfig,
            TriggerType.RATE: RateConfig,
            TriggerType.ABSENCE: AbsenceConfig,
            TriggerType.CONTAINER_EVENT: ContainerEventConfig,
        }
        config_class = config_classes.get(self.trigger_type)
        if config_class:
            # Validate by parsing - will raise ValidationError if invalid
            config_class.model_validate(self.trigger_config)
        return self

    @field_validator("scope_targets")
    @classmethod
    def validate_scope_targets(cls, v, info):
        """Normalize scope target values."""
        return _normalize_scope_targets(v or [])

    @model_validator(mode="after")
    def validate_scope_consistency(self):
        """Validate scope_targets is non-empty when scope_type is not global."""
        if self.scope_type != ScopeType.GLOBAL and not self.scope_targets:
            raise ValueError(
                f"scope_targets required when scope_type is '{self.scope_type.value}'"
            )
        _validate_scope_targets_for_type(self.scope_type, self.scope_targets)
        return self

    @model_validator(mode="after")
    def validate_actions(self):
        """Validate action order_index values are unique."""
        if self.actions:
            indices = [a.order_index for a in self.actions]
            if len(indices) != len(set(indices)):
                raise ValueError("action order_index values must be unique")
        return self

    model_config = {"extra": "forbid"}


class RuleUpdate(BaseModel):
    """Schema for updating an existing rule. All fields optional."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1000)
    trigger_type: Optional[TriggerType] = None
    trigger_config: Optional[Dict[str, Any]] = None
    scope_type: Optional[ScopeType] = None
    scope_targets: Optional[List[str]] = None
    severity: Optional[Severity] = None
    labels: Optional[Dict[str, str]] = None
    annotations: Optional[Dict[str, str]] = None
    enabled: Optional[bool] = None
    actions: Optional[List[ActionCreate]] = Field(
        default=None, description="Replace actions list"
    )

    @field_validator("scope_targets")
    @classmethod
    def normalize_scope_targets(cls, v):
        """Normalize scope target values when provided."""
        if v is None:
            return v
        return _normalize_scope_targets(v)

    @model_validator(mode="after")
    def validate_trigger_config(self):
        """Validate trigger_config if provided with trigger_type."""
        if self.trigger_config and self.trigger_type:
            config_classes = {
                TriggerType.THRESHOLD: ThresholdConfig,
                TriggerType.KEYWORD: KeywordConfig,
                TriggerType.RATE: RateConfig,
                TriggerType.ABSENCE: AbsenceConfig,
                TriggerType.CONTAINER_EVENT: ContainerEventConfig,
            }
            config_class = config_classes.get(self.trigger_type)
            if config_class:
                config_class.model_validate(self.trigger_config)
        return self

    @model_validator(mode="after")
    def validate_scope_targets_shape(self):
        """Validate scope target format when both scope fields are provided."""
        if self.scope_type is not None and self.scope_targets is not None:
            _validate_scope_targets_for_type(self.scope_type, self.scope_targets)
        return self

    model_config = {"extra": "forbid"}


class RuleResponse(BaseModel):
    """Schema for rule in API responses."""

    id: str
    name: str
    description: Optional[str]
    trigger_type: TriggerType
    trigger_config: Dict[str, Any]
    scope_type: ScopeType
    scope_targets: List[str]
    severity: Severity
    labels: Dict[str, str]
    annotations: Dict[str, str]
    enabled: bool
    actions: List[ActionResponse] = Field(
        default_factory=list, description="Remediation actions"
    )
    organization_id: str
    created_by: Optional[str]
    updated_by: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RuleListResponse(BaseModel):
    """Paginated list of rules."""

    items: List[RuleResponse]
    total: int
    maxRules: int | None = None
    hostCount: int | None = None
    rulesPerHost: int | None = None


class RuleUsageCounts(BaseModel):
    rules: int
    alertHistory: int = 0


class RuleUsageLimits(BaseModel):
    maxRules: int | None = None
    alertHistoryLimit: int | None = None
    hostCount: int | None = None
    rulesPerHost: int | None = None


class RuleUsageUser(BaseModel):
    id: str
    email: str
    role: str | None = None


class RuleUsageResponse(BaseModel):
    edition: str
    usage: RuleUsageCounts
    limits: RuleUsageLimits
    user: RuleUsageUser | None = None


class DryRunResult(BaseModel):
    """Result of a dry-run rule evaluation."""

    rule_id: str = Field(..., description="Rule ID (temporary for unsaved rules)")
    triggered: bool = Field(..., description="Whether the rule would trigger")
    value: Optional[str] = Field(default=None, description="Evaluated metric value")
    message: str = Field(..., description="Human-readable evaluation message")
    context: Dict[str, Any] = Field(
        default_factory=dict, description="Additional evaluation context"
    )
    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of evaluation",
    )
    logs_checked: int = Field(default=0, description="Number of log entries examined")
    sample_matches: List[Dict[str, Any]] = Field(
        default_factory=list, description="Sample matching logs (if triggered)"
    )


class DryRunRequest(BaseModel):
    """Request to test a rule configuration without saving."""

    name: str = Field(
        ..., min_length=1, max_length=255, description="Rule name for identification"
    )
    trigger_type: TriggerType = Field(..., description="Type of trigger to test")
    trigger_config: Dict[str, Any] = Field(
        ..., description="Trigger-specific configuration"
    )
    scope_type: ScopeType = Field(
        default=ScopeType.GLOBAL, description="Scope type for evaluation"
    )
    scope_targets: List[str] = Field(
        default_factory=list, description="Target IDs for scope"
    )
    severity: Severity = Field(
        default=Severity.WARNING, description="Alert severity (for context)"
    )

    @model_validator(mode="after")
    def validate_trigger_config(self):
        """Validate trigger_config matches trigger_type."""
        config_classes = {
            TriggerType.THRESHOLD: ThresholdConfig,
            TriggerType.KEYWORD: KeywordConfig,
            TriggerType.RATE: RateConfig,
            TriggerType.ABSENCE: AbsenceConfig,
            TriggerType.CONTAINER_EVENT: ContainerEventConfig,
        }
        config_class = config_classes.get(self.trigger_type)
        if config_class:
            # Validate by parsing - will raise ValidationError if invalid
            config_class.model_validate(self.trigger_config)
        return self

    @model_validator(mode="after")
    def validate_scope_consistency(self):
        """Validate scope_targets is non-empty when scope_type is not global."""
        if self.scope_type != ScopeType.GLOBAL and not self.scope_targets:
            raise ValueError(
                f"scope_targets required when scope_type is '{self.scope_type.value}'"
            )
        _validate_scope_targets_for_type(self.scope_type, self.scope_targets)
        return self

    model_config = {"extra": "forbid"}


class BulkToggleRequest(BaseModel):
    """Request to toggle multiple rules at once."""

    rule_ids: List[str] = Field(..., description="List of rule IDs to toggle")
    enabled: bool = Field(..., description="New enabled state for all rules")

    model_config = {"extra": "forbid"}


class BulkToggleResponse(BaseModel):
    """Response from bulk toggle operation."""

    updated: int = Field(..., description="Number of rules successfully updated")
    errors: List[str] = Field(
        default_factory=list, description="Errors encountered during operation"
    )


class ConvertToCustomResponse(BaseModel):
    """Response from convert-to-custom operation."""

    status: str = Field(..., description="Operation status")
    message: str = Field(..., description="Human-readable message")
    rule: RuleResponse = Field(..., description="Updated rule")


__all__ = [
    "TriggerType",
    "ScopeType",
    "Severity",
    "ThresholdConfig",
    "KeywordConfig",
    "RateConfig",
    "AbsenceConfig",
    "ContainerEventConfig",
    "RuleCreate",
    "RuleUpdate",
    "RuleResponse",
    "RuleListResponse",
    "RuleUsageCounts",
    "RuleUsageLimits",
    "RuleUsageResponse",
    "RuleUsageUser",
    "DryRunResult",
    "DryRunRequest",
    "BulkToggleRequest",
    "BulkToggleResponse",
    "ConvertToCustomResponse",
    # Re-export action schemas for convenience
    "ActionCreate",
    "ActionUpdate",
    "ActionResponse",
]
