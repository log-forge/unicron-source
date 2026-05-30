"""Pydantic schemas for silence CRUD operations with matcher support."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class MatcherSchema(BaseModel):
    """Label matcher for silence filtering.

    Matchers determine which alerts are silenced. All matchers must match
    for an alert to be silenced (AND logic).
    """

    name: str = Field(..., min_length=1, description="Label name to match")
    value: str = Field(..., description="Value to match against")
    is_regex: bool = Field(default=False, description="True for regex matching")
    is_equal: bool = Field(
        default=True, description="True for equality, False for not-equal"
    )


class SilenceCreateRequest(BaseModel):
    """Schema for creating a new silence."""

    matchers: List[MatcherSchema] = Field(
        ..., min_length=1, description="Label matchers (at least one required)"
    )
    starts_at: datetime = Field(..., description="Silence start time")
    ends_at: datetime = Field(..., description="Silence end time")
    comment: Optional[str] = Field(
        default=None, max_length=1000, description="Reason or context for the silence"
    )
    recurring: bool = Field(default=False, description="Whether this silence recurs")
    recurrence_rule: Optional[str] = Field(
        default=None,
        description="RRULE string for recurring silences (RFC 5545), only if recurring=True",
    )

    @model_validator(mode="after")
    def validate_time_window(self):
        """Validate ends_at is after starts_at."""
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self

    @model_validator(mode="after")
    def validate_recurrence(self):
        """Validate recurrence_rule is only provided if recurring=True."""
        if self.recurrence_rule and not self.recurring:
            raise ValueError("recurrence_rule can only be set when recurring=True")
        return self

    model_config = {"extra": "forbid"}


class SilenceUpdateRequest(BaseModel):
    """Schema for updating an existing silence. All fields optional."""

    ends_at: Optional[datetime] = Field(default=None, description="New end time")
    comment: Optional[str] = Field(
        default=None, max_length=1000, description="Updated comment"
    )

    model_config = {"extra": "forbid"}


class SilenceResponse(BaseModel):
    """Schema for silence in API responses."""

    id: str
    matchers: List[Dict[str, Any]]
    starts_at: datetime
    ends_at: datetime
    created_by: str
    comment: Optional[str]
    recurring: bool
    recurrence_rule: Optional[str]
    expired: bool
    organization_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SilenceListResponse(BaseModel):
    """Paginated list of silences."""

    items: List[SilenceResponse]
    total: int


__all__ = [
    "MatcherSchema",
    "SilenceCreateRequest",
    "SilenceUpdateRequest",
    "SilenceResponse",
    "SilenceListResponse",
]
