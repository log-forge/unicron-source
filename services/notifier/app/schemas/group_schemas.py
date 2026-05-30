"""Pydantic schemas for notification delivery bundle management."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class GroupTargets(BaseModel):
    """Direct delivery targets for a notification group."""

    channel_ids: List[str] = Field(default_factory=list)
    preset_ids: List[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class NotificationGroupBase(BaseModel):
    """Base schema for notification groups."""

    name: str = Field(
        ..., min_length=1, max_length=255, description="Group display name"
    )
    enabled: bool = Field(default=True, description="Whether the group is active")


class NotificationGroupCreate(NotificationGroupBase):
    """Schema for creating a notification group."""

    target_config: GroupTargets = Field(
        default_factory=GroupTargets,
        description="Target configuration: direct channel IDs and preset IDs",
    )

    model_config = {"extra": "forbid"}


class NotificationGroupUpdate(BaseModel):
    """Schema for updating a notification group. All fields optional."""

    name: Optional[str] = Field(
        default=None, min_length=1, max_length=255, description="Group display name"
    )
    enabled: Optional[bool] = Field(
        default=None, description="Whether the group is active"
    )
    target_config: Optional[GroupTargets] = Field(
        default=None, description="Target configuration"
    )

    model_config = {"extra": "forbid"}


class NotificationGroupResponse(NotificationGroupBase):
    """Schema for notification group in API responses."""

    id: str
    target_config: GroupTargets
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NotificationGroupListResponse(BaseModel):
    """Paginated list of notification groups."""

    items: List[NotificationGroupResponse]
    total: int


__all__ = [
    "GroupTargets",
    "NotificationGroupBase",
    "NotificationGroupCreate",
    "NotificationGroupUpdate",
    "NotificationGroupResponse",
    "NotificationGroupListResponse",
]
