"""Notifier FastAPI application.

Main entry point for the Unicron Notifier service.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import ORJSONResponse
from sqlalchemy import text
from starlette.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import close_database, engine, get_engine, init_database
from app.core.encryption import init_encryption
from app.core.logging import get_logger, setup_logging
from app.core.redis import close_redis, get_redis, init_redis
from app.services.stream_metrics import collect_notifier_stream_backpressure
from app.services.stream_consumer import get_stream_consumer

logger = get_logger("notifier")

# Track service start time for uptime calculation
_start_time: datetime = datetime.utcnow()

def _validate_production_security() -> None:
    """Fail closed for insecure Central Auth TLS in production."""
    if settings.ENVIRONMENT != "production":
        return

    if settings.CENTRAL_URL.lower().startswith("https://") and not settings.CENTRAL_VERIFY_TLS:
        raise RuntimeError(
            "CENTRAL_VERIFY_TLS must be true when CENTRAL_URL uses HTTPS in production."
        )


def _runtime_drop_counters() -> dict[str, Any]:
    """Snapshot runtime drop/failure counters from the notifier consumer."""
    stats = get_stream_consumer().get_stats_snapshot()
    return {
        "stream_consumer": stats,
        "totals": {
            "failed_total": stats.get("failed_total", 0),
            "parse_dropped_total": stats.get("parse_dropped_total", 0),
            "dlq_published_total": stats.get("dlq_published_total", 0),
            "max_attempts_exhausted_total": stats.get(
                "max_attempts_exhausted_total", 0
            ),
            "duplicate_suppressed_total": stats.get(
                "duplicate_suppressed_total", 0
            ),
        },
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown hooks."""
    global _start_time
    _start_time = datetime.utcnow()
    setup_logging()
    _validate_production_security()
    logger.info("Starting notifier service")

    # Initialize encryption before any DB operations that touch encrypted data
    init_encryption()
    logger.info("Encryption service initialized")

    # Initialize infrastructure connections with retry
    await init_database()
    await init_redis()

    # Start stream consumer for alert-to-notification pipeline
    consumer = get_stream_consumer()
    await consumer.start()

    yield

    # Stop stream consumer gracefully
    await consumer.stop(timeout=10.0)

    # Cleanup connections
    await close_redis()
    await close_database()
    logger.info("Notifier service stopped")


app = FastAPI(
    title="notifier",
    description="Unicron Notifier Service",
    default_response_class=ORJSONResponse,
    docs_url="/docs",
    openapi_url="/openapi.json",
    redoc_url=None,
    lifespan=lifespan,
    root_path=settings.ROOT_PATH,
)

# CORS configuration
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/ping")
def ping():
    """Simple liveness probe."""
    return {"message": "pong"}


@app.get("/health")
def health():
    """
    Basic health check - service is running.

    Returns:
        JSON with status, service name, version, and uptime (seconds).
    """
    uptime_seconds = (datetime.utcnow() - _start_time).total_seconds()
    return {
        "status": "ok",
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION,
        "uptime": round(uptime_seconds, 2),
    }


@app.get("/healthz")
async def healthz():
    """
    Deep health check - verify database and Redis connectivity.

    Returns:
        JSON with status, service name, version, uptime, and component health.
        Returns 503 if any component is unhealthy.
    """
    uptime_seconds = (datetime.utcnow() - _start_time).total_seconds()
    errors = []
    components = {}

    # Check PostgreSQL
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        components["postgres"] = "ok"
    except Exception as e:
        errors.append(f"PostgreSQL: {e}")
        components["postgres"] = "error"

    # Check Redis
    try:
        redis_client = await get_redis()
        await redis_client.ping()
        components["redis"] = "ok"
    except Exception as e:
        errors.append(f"Redis: {e}")
        components["redis"] = "error"

    stream_backpressure = await collect_notifier_stream_backpressure()
    runtime_drops = _runtime_drop_counters()
    components["stream_backpressure"] = stream_backpressure
    components["runtime_drop_counters"] = runtime_drops

    response = {
        "status": "degraded"
        if errors or stream_backpressure.get("status") in {"warning", "critical"}
        else "ok",
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION,
        "uptime": round(uptime_seconds, 2),
        "components": components,
    }

    if errors:
        raise HTTPException(status_code=503, detail=response)

    return response


# Secure headers middleware
@app.middleware("http")
async def secure_headers(request, call_next):
    """Add security headers to all responses."""
    resp = await call_next(request)
    resp.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
        }
    )
    return resp


# API router with feature routes
from app.routes import (
    channels_router,
    preferences_router,
    groups_router,
    templates_router,
    dispatch_router,
    logs_router,
    ai_settings_router,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(channels_router)
api_router.include_router(preferences_router)
api_router.include_router(groups_router)
api_router.include_router(templates_router)
api_router.include_router(dispatch_router)
api_router.include_router(logs_router)
api_router.include_router(ai_settings_router)


@api_router.get("/metrics/streams")
async def stream_metrics():
    """Detailed stream pressure metrics for notifier pipelines."""
    return {
        "stream_backpressure": await collect_notifier_stream_backpressure(),
        "drop_counters": _runtime_drop_counters(),
        "timestamp": datetime.utcnow().isoformat(),
    }


app.include_router(api_router)
