import logging
from contextlib import asynccontextmanager
from typing import Any, cast

import socketio
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import ORJSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import text
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from .base_schemas import HealthResponse, PingResponse
from .core.config import settings
from .core.database import engine, session_ctx
from .core.deps import (
    ensure_client_cert,
    require_admin_user,
    require_deployment_organization,
    require_registered_herald,
)
from .core.origin_policy import (
    build_cors_headers,
    is_http_origin_allowed,
    refresh_origin_policy,
)
from .routes.container import actions_router as container_actions_router
from .routes.container import containers_overview_router
from .routes.container import monitoring_router as container_monitoring_router
from .routes.herald import herald_admin, herald_agent, herald_bootstrap, herald_register_failure
from .routes.internal import context_router as internal_context_router
from .routes.internal import actions_router as internal_actions_router
from .routes.internal import actions_state_router as internal_actions_state_router
from .routes.internal import logs_router as internal_logs_router
from .routes.internal import otlp_logs_router as internal_otlp_logs_router
from .routes.internal.logs import start_log_fanout_worker, stop_log_fanout_worker
from .routes.queries import queries_router
from .routes.security.pki import pki_public, pki_mtls
from .routes.settings import settings_router
from .routes.agent import router as agent_router
from .routes.appliance import appliance_update_router
from .routes.alerts import router as alerts_router
from .routes.telemetry import telemetry_router
from .routes.session import session_router
from .socket import bootstrap_socketio
from .tasks import start_scheduler
from .core.redis import close_redis, get_redis, init_redis
from .services.agent_registry import get_agent_registry
from .services.alerting.streams import ensure_consumer_group
from .services.alert_event_relay import start_alert_event_relay, stop_alert_event_relay
from .services.browser_session_registry import get_browser_session_registry
from .services.origin_policy_invalidation import (
    start_origin_policy_invalidation_listener,
    stop_origin_policy_invalidation_listener,
)

logger = logging.getLogger("unicron.backend.main")


_INSECURE_SHARED_SECRET_VALUES = {
    "",
    "auto-bootstrap",
    "changeme",
    "change-me",
    "default",
    "dev-internal-secret",
}


def _is_weak_shared_secret(value: str) -> bool:
    secret = (value or "").strip()
    if secret.lower() in _INSECURE_SHARED_SECRET_VALUES:
        return True
    return len(secret) < 24


def _validate_production_security() -> None:
    """Fail closed when critical service-to-service auth is weak in production."""
    if settings.ENVIRONMENT != "production":
        return

    if _is_weak_shared_secret(settings.INTERNAL_API_SECRET):
        raise RuntimeError(
            "INTERNAL_API_SECRET must be set to a strong secret (>=24 chars, non-default) in production."
        )


async def init_redis_infrastructure() -> None:
    """Initialize Redis connections and consumer groups."""
    await init_redis()

    # Ensure consumer groups exist for alert processing
    await ensure_consumer_group(
        settings.REDIS_STREAM_ALERTS,
        settings.REDIS_CONSUMER_GROUP,
    )
    await ensure_consumer_group(
        settings.REDIS_STREAM_NOTIFICATIONS,
        settings.REDIS_CONSUMER_GROUP,
    )
    await ensure_consumer_group(
        settings.REDIS_STREAM_LOG_INGEST,
        settings.REDIS_LOG_INGEST_CONSUMER_GROUP,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_production_security()
    async with session_ctx() as session:
        await refresh_origin_policy(session)
    await init_redis_infrastructure()

    if settings.ENABLE_LOG_FANOUT_WORKER:
        # Start decoupled log fanout worker (ingest queue -> VictoriaLogs + alert stream).
        await start_log_fanout_worker()
    else:
        logger.warning("Log fanout worker disabled by ENABLE_LOG_FANOUT_WORKER")

    # Start agent registry background monitor (heartbeat timeout detection)
    agent_registry = get_agent_registry()
    if settings.ENABLE_AGENT_HEARTBEAT_MONITOR:
        await agent_registry.start_monitor()
    else:
        logger.warning("Agent heartbeat monitor disabled by ENABLE_AGENT_HEARTBEAT_MONITOR")
    browser_session_registry = get_browser_session_registry()
    await browser_session_registry.start_monitor()
    await start_origin_policy_invalidation_listener()
    await start_alert_event_relay()

    if settings.ENABLE_SCHEDULER:
        start_scheduler()
    else:
        logger.warning("Scheduler disabled by ENABLE_SCHEDULER")
    yield
    # graceful shutdown hooks (reverse order)
    if settings.ENABLE_LOG_FANOUT_WORKER:
        await stop_log_fanout_worker()
    if settings.ENABLE_AGENT_HEARTBEAT_MONITOR:
        await agent_registry.stop_monitor()
    await stop_alert_event_relay()
    await stop_origin_policy_invalidation_listener()
    await browser_session_registry.stop_monitor()
    await close_redis()


# Allow running the app behind a reverse-proxy that mounts the service under a path
# (Traefik in ops mounts the API under /unicron). Use ROOT_PATH to tell Starlette/FastAPI
# about the external prefix so generated OpenAPI + docs URLs are correct.
app = FastAPI(
    title="unicron",
    default_response_class=ORJSONResponse,
    docs_url="/fastdocs",
    openapi_url="/fastopenapi.json",
    redoc_url=None,
    lifespan=lifespan,
    root_path=settings.ROOT_PATH,
    redirect_slashes=False,
)

# Ensure the app respects X-Forwarded-* headers set by Traefik (scheme, host, port)
# so generated URLs and redirects won't bounce to :UNICRON_CENTRAL_PORT when served on :UNICRON_CENTRAL_MTLS_PORT.
app.add_middleware(cast(Any, ProxyHeadersMiddleware), trusted_hosts="*")


def _merge_vary(existing: str | None, value: str) -> str:
    if not existing:
        return value
    parts = [part.strip() for part in existing.split(",") if part.strip()]
    if value not in parts:
        parts.append(value)
    return ", ".join(parts)


@app.middleware("http")
async def enforce_origin_policy(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin and not is_http_origin_allowed(origin, request):
        return ORJSONResponse(status_code=403, content={"detail": "Origin not allowed"})

    is_preflight = (
        request.method.upper() == "OPTIONS"
        and bool(origin)
        and bool(request.headers.get("access-control-request-method"))
    )
    if is_preflight and origin:
        headers = build_cors_headers(
            origin,
            request_headers=request.headers.get("access-control-request-headers"),
            preflight=True,
        )
        return Response(status_code=204, headers=headers)

    response = await call_next(request)
    if origin:
        headers = build_cors_headers(origin)
        for key, value in headers.items():
            if key.lower() == "vary":
                response.headers["Vary"] = _merge_vary(response.headers.get("Vary"), value)
            else:
                response.headers[key] = value
    return response

# Create bucket routers with the /api prefix.
public_router = APIRouter(prefix="/api")
admin_router = APIRouter(
    prefix="/api",
    dependencies=[Depends(require_admin_user), Depends(require_deployment_organization)],
)
mtls_router = APIRouter(
    prefix="/api",
    dependencies=[Depends(ensure_client_cert)],
)
herald_mtls_router = APIRouter(
    prefix="/api",
    dependencies=[
        Depends(ensure_client_cert),
        Depends(require_registered_herald),
    ],
)


@public_router.get("/ping", response_model=PingResponse)
def ping() -> PingResponse:
    return PingResponse(message="pong")


@public_router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


class ReadinessResponse(BaseModel):
    status: str
    dependencies: dict[str, str]


# Health probe for DB
@public_router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return HealthResponse(status="ok")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@public_router.get("/readyz", response_model=ReadinessResponse)
async def readyz() -> ReadinessResponse:
    """Readiness probe that checks required runtime dependencies."""
    dependencies: dict[str, str] = {}
    ready = True

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        dependencies["postgres"] = "ok"
    except Exception:
        dependencies["postgres"] = "error"
        ready = False

    try:
        redis = await get_redis()
        pong = await redis.ping()
        dependencies["redis"] = "ok" if bool(pong) else "error"
        if not pong:
            ready = False
    except Exception:
        dependencies["redis"] = "error"
        ready = False

    if not ready:
        raise HTTPException(
            status_code=503,
            detail={"status": "degraded", "dependencies": dependencies},
        )

    return ReadinessResponse(status="ok", dependencies=dependencies)


# Include the routers in your app (bucketed by dependency).
public_router.include_router(pki_public)
public_router.include_router(session_router)

mtls_router.include_router(herald_register_failure)

admin_router.include_router(settings_router)
admin_router.include_router(appliance_update_router)
admin_router.include_router(queries_router)
admin_router.include_router(herald_admin)
admin_router.include_router(telemetry_router)
admin_router.include_router(
    containers_overview_router, prefix="/containers", tags=["containers-overview"]
)
admin_router.include_router(
    container_monitoring_router, prefix="/containers", tags=["container-monitoring"]
)
admin_router.include_router(
    container_actions_router, prefix="/containers", tags=["container-actions"]
)
admin_router.include_router(alerts_router, prefix="/alerts", tags=["alerts"])

mtls_router.include_router(herald_bootstrap)
herald_mtls_router.include_router(herald_agent)
herald_mtls_router.include_router(pki_mtls)

app.include_router(public_router)
app.include_router(admin_router)
app.include_router(mtls_router)
app.include_router(herald_mtls_router)

# Internal API routes (service-to-service, secret-protected)
app.include_router(internal_context_router)
app.include_router(internal_actions_router)
app.include_router(internal_actions_state_router)
app.include_router(internal_logs_router)
app.include_router(internal_otlp_logs_router)

# Agent routes (go-streamer agents: WebSocket, enrollment, deregister)
app.include_router(agent_router, prefix="/api/agent", tags=["agent"])

@app.middleware("http")
async def secure_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
        }
    )
    return resp


# --- Socket.IO bootstrap (after app & routers) ---
# Origin policy is enforced in the connect handler using the same policy as HTTP.
_sio = bootstrap_socketio(None)
# Register socket listeners after the server is built to avoid circular imports.
from app.socket.listeners.register_all_listeners import register_all_events

register_all_events(_sio)

app.state.sio = _sio
asgi_app = socketio.ASGIApp(_sio, other_asgi_app=app, socketio_path="/api/socket.io")
