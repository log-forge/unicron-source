"""Pydantic schemas for container group management API.

Supports group CRUD operations with mutual exclusivity enforcement.
"""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class GroupCreate(BaseModel):
    """Request schema for creating a new group."""

    name: str = Field(min_length=1, max_length=255, description="Group name")
    container_ids: List[str] = Field(
        min_length=2,
        description="Canonical container keys (host_id:container_name) to add to the group (minimum 2 required)",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate and normalize group name."""
        normalized = v.strip()
        if not normalized:
            raise ValueError("Group name cannot be empty")
        return normalized


class GroupUpdate(BaseModel):
    """Request schema for updating a group."""

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="New group name",
    )
    add_container_ids: Optional[List[str]] = Field(
        default=None,
        description="Canonical container keys (host_id:container_name) to add to the group",
    )
    remove_container_ids: Optional[List[str]] = Field(
        default=None,
        description="Canonical container keys (host_id:container_name) to remove from the group",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate and normalize group name if provided."""
        if v is None:
            return None
        normalized = v.strip()
        if not normalized:
            raise ValueError("Group name cannot be empty")
        return normalized


class GroupMemberInfo(BaseModel):
    """Container member info within a group."""

    container_id: str
    name: str
    host_id: Optional[str] = None


class GroupDetailResponse(BaseModel):
    """Detailed group response for CRUD operations."""

    id: str = Field(description="Group primary key")
    name: str = Field(description="Group name")
    member_count: int = Field(description="Number of containers in group")
    members: List[GroupMemberInfo] = Field(default_factory=list)


class GroupOperationResponse(BaseModel):
    """Response for group operations (create/update/delete)."""

    success: bool
    message: str
    group: Optional[GroupDetailResponse] = None


__all__ = [
    "GroupCreate",
    "GroupUpdate",
    "GroupMemberInfo",
    "GroupDetailResponse",
    "GroupOperationResponse",
]
