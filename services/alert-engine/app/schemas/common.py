"""Common Pydantic schemas used across the alert-engine API."""

from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Single error detail."""

    field: Optional[str] = None
    message: str


class ErrorResponse(BaseModel):
    """Standard error response."""

    code: str
    message: str
    details: Optional[List[ErrorDetail]] = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response."""

    items: List[T]
    total: int
    page: int
    page_size: int
    has_more: bool


class SuccessResponse(BaseModel):
    """Generic success response."""

    success: bool = True
    message: Optional[str] = None


__all__ = [
    "ErrorDetail",
    "ErrorResponse",
    "PaginatedResponse",
    "SuccessResponse",
]
