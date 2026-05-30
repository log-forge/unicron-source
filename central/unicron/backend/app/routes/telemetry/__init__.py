from fastapi import APIRouter
from .inventory import router as inventory_router
from .victoria import router as victoria_router

telemetry_router = APIRouter(prefix="/telemetry", tags=["telemetry"])
telemetry_router.include_router(inventory_router)
telemetry_router.include_router(victoria_router)

routers = [telemetry_router]

__all__ = ["telemetry_router", "routers"]
