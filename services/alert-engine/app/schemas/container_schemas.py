"""Pydantic schemas for container API responses.

These schemas match the frontend's expected ContainerInfo and GroupInfo types
defined in Unicron/central/unicron/frontend/app/features/alert-engine/types/container.ts
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ContainerResponse(BaseModel):
    """Container info matching frontend ContainerInfo type."""

    identifier: str = Field(..., description="Unique identifier (host_id:name:short_id)")
    name: str = Field(..., description="Container name")
    host_id: Optional[str] = Field(default=None, description="Herald ID that owns this container")
    container_id: str = Field(..., description="Docker container ID")
    image_name: str = Field(default="", description="Container image name")
    last_seen: str = Field(..., description="ISO timestamp of last inventory update")
    status: Optional[str] = Field(default=None, description="Container status (running, exited, etc.)")
    labels: Dict[str, str] = Field(default_factory=dict, description="Container labels")


class GroupMember(BaseModel):
    """Group member reference."""

    host_id: str = Field(..., description="Herald ID")
    container_name: str = Field(..., description="Container name")


class GroupResponse(BaseModel):
    """Group info matching frontend GroupInfo type."""

    groupId: str = Field(..., description="Group primary key ID")
    name: str = Field(..., description="Group name")
    containerIds: List[str] = Field(default_factory=list, description="Container identifier keys")
    members: Optional[List[GroupMember]] = Field(default=None, description="Detailed member list")
    monitoredContainerCount: Optional[int] = Field(default=None, description="Count of monitored containers")
    monitoredContainers: Optional[List[str]] = Field(default=None, description="List of monitored container IDs")


class ContainerListResponse(BaseModel):
    """Response schema for GET /containers endpoint."""

    containers: List[ContainerResponse] = Field(default_factory=list)
    groups: List[GroupResponse] = Field(default_factory=list)
    total_containers: Optional[int] = Field(default=None, description="Total monitored containers available")
    total_groups: Optional[int] = Field(default=None, description="Total groups available")
    container_offset: Optional[int] = Field(default=None, description="Applied container offset")
    container_limit: Optional[int] = Field(default=None, description="Applied container page size")
    group_offset: Optional[int] = Field(default=None, description="Applied group offset")
    group_limit: Optional[int] = Field(default=None, description="Applied group page size")
    has_more_containers: Optional[bool] = Field(default=None, description="Whether more container pages are available")
    has_more_groups: Optional[bool] = Field(default=None, description="Whether more group pages are available")


__all__ = [
    "ContainerResponse",
    "GroupMember",
    "GroupResponse",
    "ContainerListResponse",
]
