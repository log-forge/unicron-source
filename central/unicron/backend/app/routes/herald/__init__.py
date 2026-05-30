from fastapi import APIRouter

from .deregister import admin_router as deregister_admin_router
from .deregister import router as deregister_router
from .herald_health import router as health_router
from .inventory_ingest import admin_router as inventory_admin_router
from .inventory_ingest import router as inventory_router
from .register import router as register_router
from .register_exception import exception_router as register_exception_router

# Machine endpoint for agents that need to report registration failure state.
herald_register_failure = APIRouter(prefix="/herald", tags=["herald", "bootstrap"])
herald_register_failure.include_router(register_exception_router)

# Admin/control-plane endpoints.
herald_admin = APIRouter(prefix="/herald", tags=["herald", "admin"])
herald_admin.include_router(inventory_admin_router)
herald_admin.include_router(deregister_admin_router)

# Herald bootstrap endpoints (mTLS).
herald_bootstrap = APIRouter(prefix="/herald", tags=["herald", "bootstrap"])
herald_bootstrap.include_router(register_router)

# Herald agent endpoints (mTLS, requires registered herald in handlers).
herald_agent = APIRouter(prefix="/herald", tags=["herald", "agent"])
herald_agent.include_router(health_router)
herald_agent.include_router(inventory_router)
herald_agent.include_router(deregister_router)


# Export all routers for inclusion in main app
routers = [herald_register_failure, herald_admin, herald_bootstrap, herald_agent]
