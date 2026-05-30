from fastapi import APIRouter

from .origin_policy import router as origin_policy_router

settings_router = APIRouter(prefix="/settings", tags=["settings"])
settings_router.include_router(origin_policy_router)

__all__ = ["settings_router"]
