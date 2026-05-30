"""Agent API routes for go-streamer agent connections and enrollment.

Provides:
- WebSocket endpoint for agent connections (ws_handler)
- Enrollment endpoints for generating agent tokens (enrollment)
- Deregistration endpoint for decommissioning agents (deregister)
"""

from fastapi import APIRouter

from .deregister import router as deregister_router
from .enrollment import router as enrollment_router
from .ws_handler import router as agent_ws_router

# Create main agent router
router = APIRouter()

# Include all agent-related routers
router.include_router(agent_ws_router, tags=["agent-websocket"])
router.include_router(enrollment_router, tags=["agent-enrollment"])
router.include_router(deregister_router, tags=["agent-deregister"])

__all__ = ["router"]
