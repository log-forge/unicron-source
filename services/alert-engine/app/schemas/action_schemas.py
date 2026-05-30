"""Pydantic schemas for remediation action configuration and validation."""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class ActionType(str, Enum):
    """Types of remediation actions."""

    RESTART = "restart"
    STOP = "stop"
    START = "start"
    KILL = "kill"
    RUN_SCRIPT = "run_script"
    NOTIFY = "notify"


# Action configuration schemas (discriminated by action_type)
class ContainerActionConfig(BaseModel):
    """Configuration for container actions (restart, stop, start, kill)."""

    timeout_seconds: int = Field(
        default=30, ge=1, le=300, description="Timeout for action completion"
    )
    force: bool = Field(
        default=False, description="Use SIGKILL instead of SIGTERM for stop/kill"
    )

    model_config = {"extra": "forbid"}


class RunScriptConfig(BaseModel):
    """Configuration for run_script action."""

    script: str = Field(
        ..., min_length=1, max_length=10000, description="Script content to execute"
    )
    interpreter: str = Field(
        default="/bin/sh", description="Script interpreter path"
    )
    timeout_seconds: int = Field(
        default=60, ge=1, le=3600, description="Script execution timeout"
    )
    working_dir: Optional[str] = Field(
        default=None, description="Working directory for script execution"
    )
    environment: Dict[str, str] = Field(
        default_factory=dict, description="Environment variables for script"
    )

    model_config = {"extra": "forbid"}


class NotifyActionConfig(BaseModel):
    """Configuration for notify action (in action chains)."""

    channel_ids: List[str] = Field(
        default_factory=list, description="Notification channel IDs to use"
    )
    group_ids: List[str] = Field(
        default_factory=list, description="Notification group IDs to use"
    )
    preset_ids: List[str] = Field(
        default_factory=list, description="Notification preset IDs to use"
    )
    message_template: Optional[str] = Field(
        default=None, max_length=5000, description="Override default message template"
    )

    @model_validator(mode="after")
    def validate_targets(self):
        """Require at least one explicit notification target."""
        if not (self.channel_ids or self.group_ids or self.preset_ids):
            raise ValueError(
                "Notify action requires at least one channel_id, group_id, or preset_id"
            )
        return self

    model_config = {"extra": "forbid"}


# Action CRUD schemas
class ActionCreate(BaseModel):
    """Schema for creating an action within a rule."""

    action_type: ActionType = Field(..., description="Type of action")
    action_config: Dict[str, Any] = Field(
        default_factory=dict, description="Action-specific configuration"
    )
    order_index: int = Field(
        default=0, ge=0, description="Execution order (0 = first)"
    )
    enabled: bool = Field(default=True, description="Whether action is enabled")

    @model_validator(mode="after")
    def validate_action_config(self):
        """Validate action_config matches action_type."""
        config_classes = {
            ActionType.RESTART: ContainerActionConfig,
            ActionType.STOP: ContainerActionConfig,
            ActionType.START: ContainerActionConfig,
            ActionType.KILL: ContainerActionConfig,
            ActionType.RUN_SCRIPT: RunScriptConfig,
            ActionType.NOTIFY: NotifyActionConfig,
        }
        config_class = config_classes.get(self.action_type)
        if config_class:
            # Validate by parsing - will raise ValidationError if invalid
            config_class.model_validate(self.action_config)
        return self

    model_config = {"extra": "forbid"}


class ActionUpdate(BaseModel):
    """Schema for updating an action. All fields optional."""

    action_type: Optional[ActionType] = None
    action_config: Optional[Dict[str, Any]] = None
    order_index: Optional[int] = Field(default=None, ge=0)
    enabled: Optional[bool] = None

    @model_validator(mode="after")
    def validate_action_config(self):
        """Validate action_config if provided with action_type."""
        if self.action_config is not None and self.action_type is not None:
            config_classes = {
                ActionType.RESTART: ContainerActionConfig,
                ActionType.STOP: ContainerActionConfig,
                ActionType.START: ContainerActionConfig,
                ActionType.KILL: ContainerActionConfig,
                ActionType.RUN_SCRIPT: RunScriptConfig,
                ActionType.NOTIFY: NotifyActionConfig,
            }
            config_class = config_classes.get(self.action_type)
            if config_class:
                config_class.model_validate(self.action_config)
        return self

    model_config = {"extra": "forbid"}


class ActionResponse(BaseModel):
    """Schema for action in API responses."""

    id: str
    action_type: ActionType
    action_config: Dict[str, Any]
    order_index: int
    enabled: bool

    model_config = {"from_attributes": True}


__all__ = [
    "ActionType",
    "ContainerActionConfig",
    "RunScriptConfig",
    "NotifyActionConfig",
    "ActionCreate",
    "ActionUpdate",
    "ActionResponse",
]
