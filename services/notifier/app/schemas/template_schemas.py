"""Pydantic schemas for template API."""

from typing import Any, Dict

from pydantic import BaseModel


class TemplatePreviewRequest(BaseModel):
    """Request to preview a template rendering."""

    channel_type: str
    template: str
    context: Dict[str, Any] = {}


class TemplatePreviewResponse(BaseModel):
    """Response with rendered template preview."""

    rendered: str


class DefaultTemplateResponse(BaseModel):
    """Response with default template content."""

    channel_type: str
    template: str
