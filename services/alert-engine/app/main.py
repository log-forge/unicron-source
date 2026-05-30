"""Alert-engine FastAPI application.

Main entry point for the Unicron Alert Engine service.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import ORJSONResponse
from sqlalchemy import text
from starlette.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import close_database, engine, get_engine, init_database
from app.core.logging import get_logger, setup_logging
from app.core.redis import close_redis, get_redis, init_redis
from app.core.scheduler import scheduler
from app.services.container_registry import get_container_registry
from app.services.container_stream_consumer import get_container_stream_consumer
from app.services.container_websocket import (
    get_container_websocket_service,
    handle_container_stream_update,
)
from app.services.log_stream_consumer import get_log_stream_consumer
from app.services.container_event_consumer import get_container_event_consumer
from app.services.data_quality_service import data_quality_service
from app.services.rule_matcher import RuleMatcher
from app.services.stream_metrics import (
    collect_central_log_ingest_counters,
    collect_otlp_metrics_path_status,
    collect_stream_backpressure,
)

logger = get_logger("alert-engine")

# Track service start time for uptime calculation
_start_time: datetime = datetime.utcnow()

_INSECURE_SHARED_SECRET_VALUES = {
    "",
    "changeme",
    "change-me",
    "default",
    "dev-internal-secret",
}

_CREATE_PARTITION_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION alerting.create_alerthistory_partition(
    partition_date DATE
) RETURNS VOID AS $$
DECLARE
    partition_name TEXT;
    start_date DATE;
    end_date DATE;
BEGIN
    partition_name := 'alerthistory_y' || to_char(partition_date, 'YYYY') || 'm' || to_char(partition_date, 'MM');
    start_date := date_trunc('month', partition_date)::DATE;
    end_date := (date_trunc('month', partition_date) + interval '1 month')::DATE;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'alerting'
          AND c.relname = partition_name
    ) THEN
        EXECUTE format(
            'CREATE TABLE alerting.%I PARTITION OF alerting.alerthistory FOR VALUES FROM (%L) TO (%L)',
            partition_name, start_date, end_date
        );
    END IF;
END;
$$ LANGUAGE plpgsql;
"""

_DROP_OLD_PARTITIONS_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION alerting.drop_old_alerthistory_partitions(
    retention_months INTEGER DEFAULT 12
) RETURNS VOID AS $$
DECLARE
    cutoff_date DATE;
    partition_record RECORD;
BEGIN
    cutoff_date := (date_trunc('month', CURRENT_DATE) - (retention_months || ' months')::INTERVAL)::DATE;

    FOR partition_record IN
        SELECT c.relname AS partition_name
        FROM pg_inherits i
        JOIN pg_class c ON c.oid = i.inhrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE i.inhparent = 'alerting.alerthistory'::regclass
          AND n.nspname = 'alerting'
          AND c.relname ~ '^alerthistory_y[0-9]{4}m[0-9]{2}$'
    LOOP
        IF to_date(
            substring(partition_record.partition_name from 'y([0-9]{4})m([0-9]{2})'),
            'YYYYMM'
        ) < cutoff_date THEN
            EXECUTE format('DROP TABLE alerting.%I', partition_record.partition_name);
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;
"""


def _is_weak_shared_secret(value: str) -> bool:
    secret = (value or "").strip()
    if secret.lower() in _INSECURE_SHARED_SECRET_VALUES:
        return True
    return len(secret) < 24


def _validate_production_security() -> None:
    """Fail closed for weak internal auth in production."""
    if settings.ENVIRONMENT != "production":
        return

    if _is_weak_shared_secret(settings.CENTRAL_INTERNAL_SECRET):
        raise RuntimeError(
            "CENTRAL_INTERNAL_SECRET must be set to a strong secret (>=24 chars, non-default) in production."
        )

    if settings.CENTRAL_URL.lower().startswith("https://") and not settings.CENTRAL_VERIFY_TLS:
        raise RuntimeError(
            "CENTRAL_VERIFY_TLS must be true when CENTRAL_URL uses HTTPS in production."
        )


def _runtime_drop_counters() -> dict[str, Any]:
    """Snapshot runtime drop/failure counters from stream consumers."""
    log_stats = get_log_stream_consumer().get_stats_snapshot()
    container_stats = get_container_stream_consumer().get_stats_snapshot()
    event_stats = get_container_event_consumer().get_stats_snapshot()

    total_failed = (
        log_stats.get("failed_total", 0)
        + container_stats.get("failed_total", 0)
        + event_stats.get("failed_total", 0)
    )
    total_parse_dropped = (
        log_stats.get("parse_dropped_total", 0)
        + container_stats.get("parse_dropped_total", 0)
        + event_stats.get("parse_dropped_total", 0)
    )
    total_dlq_published = (
        log_stats.get("dlq_published_total", 0)
        + container_stats.get("dlq_published_total", 0)
        + event_stats.get("dlq_published_total", 0)
    )

    return {
        "log_consumer": log_stats,
        "container_consumer": container_stats,
        "event_consumer": event_stats,
        "totals": {
            "failed_total": total_failed,
            "parse_dropped_total": total_parse_dropped,
            "dlq_published_total": total_dlq_published,
        },
    }


async def bootstrap_container_registry() -> None:
    """Bootstrap the container registry from Redis monitoring state keys.

    Scans monitoring:* keys in Redis (shared with Central) to populate
    the registry with currently-monitored containers. Each key contains
    the host_id, so registry entries get correct host context.

    Key format: monitoring:{host_id}:{name}|{image}
    Value: "1" (enabled) or "0" (disabled)

    REPLACES the previous httpx-based bootstrap that called Central's
    /api/containers/monitoring-states endpoint (which stripped host_id,
    forcing host_id="local" placeholder). Direct Redis scan extracts
    real host_id from the key itself.
    """
    logger.info("Bootstrapping container registry from Redis monitoring keys...")
    registry = get_container_registry()

    try:
        count = await registry.bootstrap_from_monitoring_keys(clear_existing=True)
        if count == 0:
            logger.info("No monitored containers found during bootstrap")
        else:
            logger.info(
                "Registry bootstrapped with %d monitored containers (host-aware keys from Redis)",
                count,
            )

    except Exception as e:
        logger.warning("Registry bootstrap failed: %s", str(e))


async def bootstrap_group_caches() -> None:
    """Bootstrap Redis group caches from PostgreSQL.

    Populates ``alert-engine:group-containers:{group_id}`` Redis SETs
    for every group in the database so that group-scoped rules can
    resolve their members immediately on startup.

    Must run AFTER ``bootstrap_container_registry()`` since the registry
    determines which containers are considered monitored.
    """
    from app.core.database import get_session
    from app.services.group_cache import sync_all_group_caches

    try:
        async for session in get_session():
            count = await sync_all_group_caches(session)
            if count:
                logger.info("Bootstrapped Redis cache for %d groups", count)
            else:
                logger.info("No groups to bootstrap")
            break
    except Exception as e:
        logger.warning("Group cache bootstrap failed: %s", str(e))


async def ensure_alerting_tables():
    """Create alerting schema tables if they don't exist.

    Runs after init_database() during startup. Creates each table in its
    own transaction so that pre-existing tables (from Central's Alembic
    migrations) don't cause a rollback that prevents new tables from
    being created.
    """
    from sqlmodel import SQLModel
    # Import all table models to register them with SQLModel metadata
    from app.services.rule_service import AlertRule
    from app.services.history_service import AlertHistory
    from app.services.silence_service import Silence
    from app.models.action import RuleAction, ActionAuditLog
    from app.models.rule_audit import RuleAuditLog
    from app.models.gatekeeper_state import ActionGatekeeperState, GatekeeperConfig
    from app.models.alert_state import AlertState
    from app.models.alert_history import AlertHistory as AlertHistoryModel
    from app.models.alert_audit import AlertOperationLog
    from app.models.data_quality_config import AlertDataQualityConfig
    from app.models.keyword_config import KeywordConfig

    eng = get_engine()

    # Create alerting schema
    async with eng.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS alerting"))

    # Create each table individually so pre-existing tables (with their
    # indexes) don't roll back the entire migration. Tables created by
    # Central's Alembic (alertrule, alerthistory, alertstate, silence)
    # will be skipped; new tables (ruleaction, ruleauditlog, etc.) will
    # be created.
    created = []
    skipped = []
    for table in SQLModel.metadata.sorted_tables:
        if table.schema != "alerting":
            continue
        try:
            async with eng.begin() as conn:
                await conn.run_sync(table.create, checkfirst=True)
            created.append(table.name)
        except Exception as exc:
            exc_str = str(exc).lower()
            if "already exists" in exc_str or "duplicate" in exc_str:
                skipped.append(table.name)
            else:
                logger.error("Failed to create table %s: %s", table.name, exc)
                skipped.append(table.name)

    if created:
        logger.info("Created alerting tables: %s", ", ".join(created))
    if skipped:
        logger.info("Skipped existing alerting tables: %s", ", ".join(skipped))

    # Reconcile older alertstate schemas created before stacking fields existed.
    # Central may have created alerting.alertstate already, in which case
    # SQLModel checkfirst skips it and the new columns never appear.
    async with eng.begin() as conn:
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS alerting.alertstate
                ADD COLUMN IF NOT EXISTS count INTEGER DEFAULT 1,
                ADD COLUMN IF NOT EXISTS first_seen TIMESTAMPTZ NULL,
                ADD COLUMN IF NOT EXISTS last_seen TIMESTAMPTZ NULL,
                ADD COLUMN IF NOT EXISTS stacking_key VARCHAR DEFAULT '',
                ADD COLUMN IF NOT EXISTS last_trigger_context JSONB NULL
                """
            )
        )
        await conn.execute(
            text(
                """
                UPDATE alerting.alertstate
                SET
                    count = COALESCE(count, 1),
                    first_seen = COALESCE(first_seen, started_at, updated_at, NOW()),
                    last_seen = COALESCE(last_seen, updated_at, started_at, NOW()),
                    stacking_key = COALESCE(
                        NULLIF(stacking_key, ''),
                        rule_id || ':' || COALESCE(
                            NULLIF(labels->>'container_key', ''),
                            NULLIF(labels->>'container_id', ''),
                            ''
                        )
                    )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_alertstate_stacking_key
                ON alerting.alertstate (stacking_key)
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_alertstate_org_status_updated
                ON alerting.alertstate (organization_id, status, updated_at DESC)
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_alertstate_org_updated
                ON alerting.alertstate (organization_id, updated_at DESC)
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_alertstate_container_key_expr
                ON alerting.alertstate ((COALESCE(labels->>'container_key', labels->>'container_id')))
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_alertstate_host_id_expr
                ON alerting.alertstate ((labels->>'host_id'))
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_alertstate_container_name_expr
                ON alerting.alertstate ((labels->>'container_name'))
                """
            )
        )

    logger.info("Alerting schema tables verified/created")


def _month_start_with_offset(base: datetime, month_offset: int) -> datetime:
    """Return month start for ``base`` shifted by ``month_offset`` months."""
    month_index = (base.month - 1) + month_offset
    year = base.year + (month_index // 12)
    month = (month_index % 12) + 1
    return datetime(year, month, 1)


async def ensure_alert_history_partition_lifecycle() -> None:
    """
    Ensure alert-history partition helper functions exist and are runnable.

    This self-heals dev/test bootstrap paths where Alembic migrations were
    skipped and maintenance SQL functions were never installed.
    """
    if not settings.ALERT_HISTORY_PARTITION_MAINTENANCE_ENABLED:
        return

    lookahead_months = max(0, int(settings.ALERT_HISTORY_PARTITION_LOOKAHEAD_MONTHS))
    retention_months = max(1, int(settings.ALERT_HISTORY_PARTITION_RETENTION_MONTHS))

    try:
        async with engine.begin() as conn:
            is_partitioned_result = await conn.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_partitioned_table pt
                        JOIN pg_class c ON c.oid = pt.partrelid
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname = 'alerting'
                          AND c.relname = 'alerthistory'
                    )
                    """
                )
            )
            is_partitioned = bool(is_partitioned_result.scalar())
            if not is_partitioned:
                logger.warning(
                    "Skipping alert-history partition lifecycle install: "
                    "alerting.alerthistory is missing or not partitioned"
                )
                return

            await conn.execute(text(_CREATE_PARTITION_FUNCTION_SQL))
            await conn.execute(text(_DROP_OLD_PARTITIONS_FUNCTION_SQL))

            base_month = datetime.utcnow().replace(
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            for offset in range(lookahead_months + 1):
                partition_month = _month_start_with_offset(base_month, offset)
                await conn.execute(
                    text(
                        "SELECT alerting.create_alerthistory_partition("
                        "CAST(:partition_date AS DATE)"
                        ")"
                    ),
                    {"partition_date": partition_month.date()},
                )

            await conn.execute(
                text(
                    "SELECT alerting.drop_old_alerthistory_partitions("
                    "CAST(:retention_months AS INTEGER)"
                    ")"
                ),
                {"retention_months": retention_months},
            )

        logger.info(
            "Alert-history partition lifecycle ensured "
            "(lookahead_months=%d retention_months=%d)",
            lookahead_months,
            retention_months,
        )
    except Exception as exc:
        logger.warning("Failed to ensure alert-history partition lifecycle: %s", str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown hooks."""
    global _start_time
    _start_time = datetime.utcnow()
    setup_logging()
    _validate_production_security()
    logger.info("Starting alert-engine service")

    # Initialize infrastructure connections with retry
    await init_database()
    await ensure_alerting_tables()
    await ensure_alert_history_partition_lifecycle()
    await init_redis()

    # Start the evaluation scheduler
    scheduler.start()

    # Start data quality sweep (auto-ack + retention cleanup)
    data_quality_service.start()

    # Create RuleMatcher for real-time log rule evaluation
    # Maintains O(1) container->rules index with 60s auto-refresh
    rule_matcher = RuleMatcher()
    app.state.rule_matcher = rule_matcher

    # Start log stream consumer for real-time rule evaluation
    # This enables parallel log processing across alert-engine workers
    log_consumer = get_log_stream_consumer()
    await log_consumer.start(rule_matcher=rule_matcher)

    # Start container event consumer for stability rule evaluation
    # (restart loop, crash loop, failed start detection)
    event_consumer = get_container_event_consumer()
    await event_consumer.start(rule_matcher=rule_matcher)

    # Start container WebSocket service for broadcasting updates
    container_ws = get_container_websocket_service()
    await container_ws.start()

    # Start container stream consumer and wire to WebSocket for real-time updates
    container_consumer = get_container_stream_consumer()
    container_consumer.set_update_callback(handle_container_stream_update(container_ws))
    await container_consumer.start(rule_matcher=rule_matcher)

    # Bootstrap container registry from Central's current state
    await bootstrap_container_registry()

    # Bootstrap Redis group caches so group-scoped rules work immediately
    await bootstrap_group_caches()

    yield

    # Stop container stream consumer gracefully
    await container_consumer.stop(timeout=10.0)

    # Stop container WebSocket service
    await container_ws.stop()

    # Stop container event consumer gracefully
    await event_consumer.stop(timeout=10.0)

    # Stop log stream consumer gracefully
    await log_consumer.stop(timeout=10.0)

    # Stop data quality sweep
    await data_quality_service.stop()

    # Stop the evaluation scheduler
    await scheduler.stop()

    # Cleanup connections
    await close_redis()
    await close_database()
    logger.info("Alert-engine service stopped")


app = FastAPI(
    title="alert-engine",
    description="Unicron Alert Engine Service",
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

    stream_backpressure = await collect_stream_backpressure()
    central_ingest = await collect_central_log_ingest_counters()
    otlp_metrics_path = await collect_otlp_metrics_path_status()
    runtime_drops = _runtime_drop_counters()

    components["stream_backpressure"] = stream_backpressure
    components["central_log_ingest"] = central_ingest
    components["otlp_metrics_path"] = otlp_metrics_path
    components["runtime_drop_counters"] = runtime_drops

    soft_degraded = (
        stream_backpressure.get("status") in {"warning", "critical"}
        or central_ingest.get("status") in {"warning", "critical"}
        or otlp_metrics_path.get("status") in {"warning", "critical"}
    )

    response = {
        "status": "degraded" if errors or soft_degraded else "ok",
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


# Import and register API routes
from fastapi import APIRouter

from app.routes import (
    alert_audit_router,
    alerts_router,
    audit_router,
    containers_router,
    gatekeeper_router,
    groups_router,
    history_router,
    keyword_settings_router,
    notification_targets_router,
    notifications_router,
    rule_audit_router,
    rules_router,
    settings_router,
    silences_router,
    templates_router,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(alert_audit_router)
api_router.include_router(audit_router)
api_router.include_router(containers_router)
api_router.include_router(gatekeeper_router)
api_router.include_router(groups_router)
api_router.include_router(history_router)
api_router.include_router(alerts_router)
api_router.include_router(keyword_settings_router)
api_router.include_router(notification_targets_router)
api_router.include_router(notifications_router)
api_router.include_router(rule_audit_router)
api_router.include_router(rules_router)
api_router.include_router(settings_router)
api_router.include_router(silences_router)
api_router.include_router(templates_router)


@api_router.get("/health")
async def api_health():
    """
    Health check with counts for frontend status display.

    Returns:
        JSON with status, rules_count, alerts_count, containers_count, timestamp.
        Uses 'healthy' status matching frontend HealthStatus type.
    """
    from app.core.database import get_session
    from app.services.container_registry import get_container_registry
    from sqlalchemy import func, select

    rules_count = 0
    alerts_count = 0
    containers_count = 0
    status = "healthy"

    try:
        # Import models here to avoid circular imports
        from app.services.rule_service import AlertRule
        from app.models.alert_state import AlertState

        # Get counts from database
        async for session in get_session():
            # Count rules
            rules_result = await session.execute(
                select(func.count()).select_from(AlertRule)
            )
            rules_count = rules_result.scalar() or 0

            # Count active alerts
            alerts_result = await session.execute(
                select(func.count()).select_from(AlertState).where(
                    AlertState.status.in_(["firing", "acknowledged"])
                )
            )
            alerts_count = alerts_result.scalar() or 0

            break

        # Count monitored containers from the live registry.
        containers_count = await get_container_registry().count()
    except Exception as e:
        logger.warning("API health check failed to get counts: %s", str(e))
        status = "error"

    stream_backpressure = await collect_stream_backpressure()
    central_ingest = await collect_central_log_ingest_counters()
    otlp_metrics_path = await collect_otlp_metrics_path_status()
    runtime_drops = _runtime_drop_counters()

    health_alerts: list[str] = []
    health_alerts.extend(stream_backpressure.get("alerts", []))
    health_alerts.extend(central_ingest.get("alerts", []))
    health_alerts.extend(otlp_metrics_path.get("alerts", []))

    backpressure_status = "ok"
    component_statuses = [
        stream_backpressure.get("status"),
        central_ingest.get("status"),
        otlp_metrics_path.get("status"),
    ]
    if "critical" in component_statuses:
        backpressure_status = "critical"
    elif "warning" in component_statuses:
        backpressure_status = "warning"
    elif "unknown" in component_statuses:
        backpressure_status = "unknown"

    if status != "error":
        if backpressure_status == "critical":
            status = "error"
        elif backpressure_status == "warning":
            status = "degraded"

    return {
        "status": status,
        "rules_count": rules_count,
        "alerts_count": alerts_count,
        "containers_count": containers_count,
        "backpressure": {
            "status": "critical" if status == "error" else backpressure_status,
            "alerts": health_alerts,
            "streams": stream_backpressure,
            "central_log_ingest": central_ingest,
            "otlp_metrics_path": otlp_metrics_path,
            "drop_counters": runtime_drops,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


@api_router.get("/metrics/streams")
async def stream_metrics():
    """Detailed stream and ingest pressure metrics for dashboards and SRE probes."""
    return {
        "stream_backpressure": await collect_stream_backpressure(),
        "central_log_ingest": await collect_central_log_ingest_counters(),
        "otlp_metrics_path": await collect_otlp_metrics_path_status(),
        "drop_counters": _runtime_drop_counters(),
        "timestamp": datetime.utcnow().isoformat(),
    }


app.include_router(api_router)

# Keep root-level test-notification for backward compatibility with older callers.
app.include_router(notifications_router)
