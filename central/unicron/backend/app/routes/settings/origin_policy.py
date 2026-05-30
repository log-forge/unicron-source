from pydantic import BaseModel, Field

from app.core.database import get_session
from app.core.origin_policy import (
    derive_request_origin,
    filter_ui_managed_origins,
    normalize_origin_list,
    refresh_origin_policy,
)
from app.models.settings.crud.origin_policy_config_crud import (
    ensure_origin_policy_config,
    update_origin_policy_config,
)
from app.services.origin_policy_invalidation import publish_origin_policy_invalidation
from app.core.deps.permissions import require_permission
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class OriginPolicyUpdateBody(BaseModel):
    allowed_origins: list[str] = Field(default_factory=list)


class OriginPolicyResponse(BaseModel):
    effective_allowed_origins: list[str] = Field(default_factory=list)
    stored_allowed_origins: list[str] = Field(default_factory=list)
    protected_allowed_origins: list[str] = Field(default_factory=list)
    origin_policy_source: str
    origin_policy_managed_by_env: bool
    origin_policy_ui_editable: bool = True
    origin_policy_same_origin_only: bool


@router.get("/origin-policy", response_model=OriginPolicyResponse)
async def get_origin_policy_handler(
    session: AsyncSession = Depends(get_session),
) -> OriginPolicyResponse:
    snapshot = await refresh_origin_policy(session)
    return OriginPolicyResponse.model_validate(snapshot.to_payload())


@router.put("/origin-policy", response_model=OriginPolicyResponse)
async def update_origin_policy_handler(
    body: OriginPolicyUpdateBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _auth=Depends(require_permission({"settings": ["update"]})),
) -> OriginPolicyResponse:
    policy = await refresh_origin_policy(session)
    if not policy.ui_editable:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Origin policy is managed by UNICRON_ALLOWED_ORIGINS/CORS_ORIGINS env",
        )

    allowed_origins, invalid_origins = normalize_origin_list(body.allowed_origins)
    if invalid_origins:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid origin(s): {', '.join(invalid_origins)}",
        )

    ui_managed_origins = filter_ui_managed_origins(allowed_origins, policy.protected_allowed_origins)
    current_request_origin = derive_request_origin(request)
    if current_request_origin and current_request_origin not in policy.protected_allowed_origins:
        if current_request_origin not in ui_managed_origins:
            ui_managed_origins.append(current_request_origin)

    cfg = await ensure_origin_policy_config(session)
    await update_origin_policy_config(session, cfg, allowed_origins=ui_managed_origins)
    updated = await refresh_origin_policy(session)
    await publish_origin_policy_invalidation("origin_policy_update")
    return OriginPolicyResponse.model_validate(updated.to_payload())


__all__ = ["OriginPolicyResponse", "OriginPolicyUpdateBody", "router"]
