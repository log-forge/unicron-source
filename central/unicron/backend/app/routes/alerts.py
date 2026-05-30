"""Alert REST API endpoints for Central's main UI.

Provides read endpoints for querying alerts directly from the shared PostgreSQL
alerting schema, and write-proxy endpoints that forward acknowledge requests
to alert-engine (which remains the single mutation authority).

Real-time alert updates are pushed via Socket.IO-backed browser fanout.
These REST endpoints serve page loads and queries.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.core.database import get_session
from app.core.deps import require_deployment_organization
from app.core.logging import get_logger
from app.models.alerting.alert_state_model import AlertState

logger = get_logger("routes.alerts")

router = APIRouter(tags=["alerts"])

# ---------------------------------------------------------------------------
# Severity mapping: alert-engine uses critical/warning/info.
# Central UI uses 4-level system: critical, high, medium, low.
# ---------------------------------------------------------------------------
_SEVERITY_MAP = {
    "critical": "critical",
    "high": "high",
    "warning": "medium",
    "info": "low",
}

_REVERSE_SEVERITY_MAP = {
    "critical": "critical",
    "high": "high",
    "medium": "warning",
    "low": "info",
}


def _map_severity(raw: str) -> str:
    """Map alert-engine severity to Central 4-level system."""
    return _SEVERITY_MAP.get(raw, raw)


def _extract_container_identity(labels: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Extract host/container identity from canonical alert labels."""
    raw_container_key = str(labels.get("container_key") or "").strip()
    host_id = str(labels.get("host_id") or "").strip() or None
    container_name = str(labels.get("container_name") or "").strip() or None

    if raw_container_key and ":" in raw_container_key:
        parsed_host_id, parsed_container_name = raw_container_key.split(":", 1)
        host_id = host_id or parsed_host_id
        container_name = container_name or parsed_container_name

    return container_name, host_id


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class AlertItemResponse(BaseModel):
    """Single alert item in the list response."""

    id: str
    rule_id: str
    rule_name: Optional[str] = None
    rule_type: Optional[str] = None
    container_name: Optional[str] = None
    host_id: Optional[str] = None
    status: str
    severity: str
    message: Optional[str] = None
    trigger_value: Optional[str] = None
    threshold: Optional[str] = None
    count: int = 1
    last_seen: datetime
    fingerprint: str
    started_at: datetime
    updated_at: datetime
    labels: Dict[str, Any] = Field(default_factory=dict)
    annotations: Dict[str, Any] = Field(default_factory=dict)


class AlertListResponse(BaseModel):
    """Paginated list of alerts."""

    items: List[AlertItemResponse]
    total: int


class AlertSummaryResponse(BaseModel):
    """Aggregate alert counts for dashboard use."""

    total_active: int
    by_severity: Dict[str, int]
    by_status: Dict[str, int]


class BulkAckResponse(BaseModel):
    """Response for bulk acknowledge operation."""

    acknowledged_count: int


# ---------------------------------------------------------------------------
# Helper: build AlertItemResponse from AlertState row
# ---------------------------------------------------------------------------


def _alert_to_response(alert: AlertState) -> AlertItemResponse:
    """Convert an AlertState DB row to an API response item."""
    labels = alert.labels or {}
    annotations = alert.annotations or {}
    eval_context = annotations.get("evaluation_context", {})
    container_name, host_id = _extract_container_identity(labels)

    return AlertItemResponse(
        id=alert.id,
        rule_id=alert.rule_id,
        rule_name=labels.get("rule_name") or labels.get("alertname"),
        rule_type=labels.get("trigger_type"),
        container_name=container_name,
        host_id=host_id,
        status=alert.status,
        severity=_map_severity(alert.severity),
        message=annotations.get("message"),
        trigger_value=alert.value,
        threshold=str(eval_context.get("threshold")) if eval_context.get("threshold") is not None else None,
        count=max(1, int(getattr(alert, "count", 1) or 1)),
        last_seen=alert.last_seen or alert.updated_at,
        fingerprint=alert.fingerprint,
        started_at=alert.started_at,
        updated_at=alert.updated_at,
        labels=labels,
        annotations=annotations,
    )


# ---------------------------------------------------------------------------
# GET /alerts -- List alerts with filters
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=AlertListResponse,
    summary="List alerts",
    description="Query alerts with optional status, severity, and container name filters.",
)
async def list_alerts(
    request: Request,
    status_filter: Optional[str] = None,
    severity: Optional[str] = None,
    container_name: Optional[str] = None,
    host_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    org_id: str = Depends(require_deployment_organization),
) -> AlertListResponse:
    """Return a paginated list of alerts for the organization."""
    # Clamp limit
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    # Base query scoped to organization
    query = select(AlertState).where(AlertState.organization_id == org_id)

    # Apply filters
    if status_filter:
        query = query.where(AlertState.status == status_filter)
    if severity:
        # Map from Central 4-level severity back to alert-engine severity for DB query
        db_severity = _REVERSE_SEVERITY_MAP.get(severity, severity)
        query = query.where(AlertState.severity == db_severity)
    if container_name and host_id:
        container_key = f"{host_id}:{container_name}"
        query = query.where(
            text(
                "labels->>'container_key' = :container_key"
            ).bindparams(container_key=container_key)
        )
    elif container_name:
        suffix_pattern = f"%:{container_name}"
        query = query.where(
            text(
                "("
                "labels->>'container_name' = :container_name "
                "OR labels->>'container_key' LIKE :suffix_pattern"
                ")"
            ).bindparams(
                container_name=container_name,
                suffix_pattern=suffix_pattern,
            )
        )
    elif host_id:
        prefix_pattern = f"{host_id}:%"
        query = query.where(
            text(
                "("
                "labels->>'host_id' = :host_id "
                "OR labels->>'container_key' LIKE :prefix_pattern"
                ")"
            ).bindparams(
                host_id=host_id,
                prefix_pattern=prefix_pattern,
            )
        )

    # Fetch page + total in one query to reduce DB round trips.
    paged_query = (
        query.add_columns(func.count().over().label("full_count"))
        .order_by(AlertState.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(paged_query)
    rows = result.all()

    alerts = [row[0] for row in rows]
    total = int(rows[0][1]) if rows else 0

    items = [_alert_to_response(a) for a in alerts]
    return AlertListResponse(items=items, total=total)


# ---------------------------------------------------------------------------
# GET /alerts/summary -- Aggregate counts
# ---------------------------------------------------------------------------


@router.get(
    "/summary",
    response_model=AlertSummaryResponse,
    summary="Alert summary",
    description="Aggregate alert counts by severity and status for the dashboard.",
)
async def alert_summary(
    request: Request,
    session: AsyncSession = Depends(get_session),
    org_id: str = Depends(require_deployment_organization),
) -> AlertSummaryResponse:
    """Return aggregate alert counts for active alerts."""
    query = (
        select(
            AlertState.severity,
            AlertState.status,
            func.count(AlertState.id).label("count"),
        )
        .where(
            AlertState.organization_id == org_id,
            AlertState.status.in_(["firing", "acknowledged"]),
        )
        .group_by(AlertState.severity, AlertState.status)
    )

    result = await session.execute(query)
    rows = result.all()

    # Initialize counts
    by_severity: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    by_status: Dict[str, int] = {"firing": 0, "acknowledged": 0}
    total_active = 0

    for row in rows:
        raw_severity, row_status, count = row
        mapped = _map_severity(raw_severity)
        by_severity[mapped] = by_severity.get(mapped, 0) + count
        by_status[row_status] = by_status.get(row_status, 0) + count
        total_active += count

    return AlertSummaryResponse(
        total_active=total_active,
        by_severity=by_severity,
        by_status=by_status,
    )


# ---------------------------------------------------------------------------
# POST /alerts/{alert_id}/ack -- Proxy acknowledge to alert-engine
# ---------------------------------------------------------------------------


@router.post(
    "/{alert_id}/ack",
    summary="Acknowledge alert",
    description="Proxy acknowledge request to alert-engine. Central does not mutate alert state directly.",
)
async def acknowledge_alert(
    alert_id: str,
    request: Request,
    org_id: str = Depends(require_deployment_organization),
) -> Dict[str, Any]:
    """Acknowledge an alert by proxying to alert-engine."""
    cookie_header = request.headers.get("cookie", "")

    url = f"{settings.ALERT_ENGINE_URL}/alert-engine/api/alerts/{alert_id}/acknowledge"

    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
            resp = await client.post(
                url,
                headers={
                    "Cookie": cookie_header,
                    "Content-Type": "application/json",
                },
            )
    except httpx.RequestError as exc:
        logger.error("Failed to proxy ack to alert-engine: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Alert-engine service unavailable",
        )

    if resp.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )
    if resp.status_code == 409:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=resp.json().get("detail", "Cannot acknowledge alert"),
        )
    if resp.status_code >= 400:
        logger.warning(
            "Alert-engine returned %d for ack on %s: %s",
            resp.status_code,
            alert_id,
            resp.text,
        )
        raise HTTPException(
            status_code=resp.status_code,
            detail=resp.json().get("detail", "Acknowledge failed"),
        )

    return resp.json()


# ---------------------------------------------------------------------------
# POST /alerts/container/{container_name}/ack -- Bulk ack per container
# ---------------------------------------------------------------------------


@router.post(
    "/container/{container_name}/ack",
    response_model=BulkAckResponse,
    summary="Bulk acknowledge alerts for a container",
    description="Acknowledge all firing alerts for a given container by proxying each to alert-engine.",
)
async def bulk_acknowledge_container(
    container_name: str,
    request: Request,
    host_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    org_id: str = Depends(require_deployment_organization),
) -> BulkAckResponse:
    """Bulk-acknowledge all firing alerts for a container."""
    # Find all firing alerts for this container (host-aware when provided).
    if host_id:
        container_key = f"{host_id}:{container_name}"
        container_clause = text(
            "labels->>'container_key' = :container_key"
        ).bindparams(container_key=container_key)
    else:
        container_clause = text(
            "("
            "labels->>'container_name' = :container_name "
            "OR labels->>'container_key' LIKE :suffix_pattern"
            ")"
        ).bindparams(
            container_name=container_name,
            suffix_pattern=f"%:{container_name}",
        )

    query = select(AlertState).where(
        AlertState.organization_id == org_id,
        AlertState.status == "firing",
        container_clause,
    )
    result = await session.execute(query)
    alerts = result.scalars().all()

    if not alerts:
        return BulkAckResponse(acknowledged_count=0)

    cookie_header = request.headers.get("cookie", "")
    acknowledged_count = 0

    async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
        for alert in alerts:
            url = f"{settings.ALERT_ENGINE_URL}/alert-engine/api/alerts/{alert.id}/acknowledge"
            try:
                resp = await client.post(
                    url,
                    headers={
                        "Cookie": cookie_header,
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code < 400:
                    acknowledged_count += 1
                else:
                    logger.warning(
                        "Bulk ack failed for alert %s: %d %s",
                        alert.id,
                        resp.status_code,
                        resp.text,
                    )
            except httpx.RequestError as exc:
                logger.warning("Bulk ack request failed for alert %s: %s", alert.id, exc)

    return BulkAckResponse(acknowledged_count=acknowledged_count)
