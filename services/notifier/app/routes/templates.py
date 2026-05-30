"""Template API endpoints for preview and default templates."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import get_current_user
from app.schemas.template_schemas import (
    TemplatePreviewRequest,
    TemplatePreviewResponse,
    DefaultTemplateResponse,
)
from app.services.template_service import template_service

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("/{channel_type}", response_model=DefaultTemplateResponse)
async def get_default_template(
    channel_type: str,
    current_user: dict = Depends(get_current_user),
):
    """Get the default template for a channel type."""
    try:
        content = template_service.get_default_template(channel_type)
        return DefaultTemplateResponse(channel_type=channel_type, template=content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/preview", response_model=TemplatePreviewResponse)
async def preview_template(
    data: TemplatePreviewRequest,
    current_user: dict = Depends(get_current_user),
):
    """Preview a template with sample data or custom context."""
    try:
        if data.context:
            # Use provided context
            rendered = template_service.render(
                data.channel_type,
                data.context,
                custom_template=data.template,
            )
        else:
            # Use sample context
            rendered = template_service.render_preview(
                data.channel_type,
                data.template,
            )
        return TemplatePreviewResponse(rendered=rendered)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Template error: {str(e)}")
