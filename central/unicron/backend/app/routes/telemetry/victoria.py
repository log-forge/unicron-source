import json
from typing import List, Literal, Union
from urllib.parse import quote

from app.core.access.role_resolver import ActorContext
from app.core.config import settings
from app.core.database import get_session
from app.core.deps import enforce_container_access, get_actor_context, require_permission
from app.routes.telemetry.schemas import (
    LogsQueryPayload,
    LogsQueryResponse,
    LogsTailTestResponse,
    MetricsInstantPayload,
    MetricsLabelNamesPayload,
    MetricsLabelValuesPayload,
    MetricsRangePayload,
    VMApiResponse,
)
from app.socket.listeners.schemas import LogsTailPayload
from app.telemetry.victoria.schemas import LogRow, VMFlatMatrixEntry, VMFlatVectorEntry
from app.utils.container_selector_resolver import resolve_container_selector_to_key
from app.utils.httpx_client import build_async_client
from app.utils.victoria_helpers import (
    build_logs_expr_for_query,
    build_logs_filter_for_tail,
    inject_container_into_metrics,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/victoria", tags=["telemetry:victoria"])

VLOGS = settings.VLOGS_BASE.rstrip("/")
VMX = settings.VMETRICS_BASE.rstrip("/")


def _tenant_headers(acc, proj):
    h = {}
    if acc is not None:
        h["AccountID"] = str(acc)
    if proj is not None:
        h["ProjectID"] = str(proj)
    return h


# -------- Logs: Query (pipes allowed) --------
@router.post(
    "/logs/query",
    response_model=LogsQueryResponse,
    dependencies=[Depends(require_permission({"telemetry": ["query"]}))],
)
async def logs_query(
    body: LogsQueryPayload,
    session: AsyncSession = Depends(get_session),
    actor: ActorContext = Depends(get_actor_context),
) -> LogsQueryResponse:
    try:
        await resolve_container_selector_to_key(session, body)
        expr = build_logs_expr_for_query(body, body.expr, body.where, body.pipes)
    except ValueError as e:
        raise HTTPException(400, str(e))

    container_key = body.container_key
    if not container_key:
        raise HTTPException(400, "container_key is required")
    await enforce_container_access(session, actor, container_key, min_role="read_only")

    form = {"query": expr, "limit": str(body.limit)}
    if body.start:
        form["start"] = body.start
    if body.end:
        form["end"] = body.end

    async with build_async_client() as c:
        r = await c.post(
            f"{VLOGS}/select/logsql/query", data=form, headers=_tenant_headers(body.account_id, body.project_id)
        )
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text)

    lines = [ln for ln in r.text.splitlines() if ln.strip()]
    rows = [LogRow.model_validate(json.loads(ln)) for ln in lines]
    return LogsQueryResponse(rows=rows, count=len(rows), query=expr)


# -------- Logs: Tail (no pipes) – preview only --------
@router.post(
    "/logs/tail/test",
    response_model=LogsTailTestResponse,
    dependencies=[Depends(require_permission({"telemetry": ["tail"]}))],
)
async def logs_tail_test(
    body: LogsTailPayload,
    session: AsyncSession = Depends(get_session),
    actor: ActorContext = Depends(get_actor_context),
) -> LogsTailTestResponse:
    try:
        await resolve_container_selector_to_key(session, body)
        expr = build_logs_filter_for_tail(body, body.filter)
    except ValueError as e:
        raise HTTPException(400, str(e))
    container_key = body.container_key
    if not container_key:
        raise HTTPException(400, "container_key is required")
    await enforce_container_access(session, actor, container_key, min_role="read_only")
    return LogsTailTestResponse(tail_expr=expr)


# -------- Metrics: instant (raw or flat) --------
InstantResponse = Union[VMApiResponse, List[VMFlatVectorEntry]]


@router.post(
    "/metrics/query",
    response_model=InstantResponse,
    dependencies=[Depends(require_permission({"telemetry": ["query"]}))],
)
async def metrics_query(
    body: MetricsInstantPayload,
    shape: Literal["raw", "flat"] = Query("raw", description='Return "raw" Prom/VM union or "flat" VMUI-like array'),
    session: AsyncSession = Depends(get_session),
    actor: ActorContext = Depends(get_actor_context),
):
    try:
        await resolve_container_selector_to_key(session, body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    container_key = body.container_key
    if not container_key:
        raise HTTPException(400, "container_key is required")
    await enforce_container_access(session, actor, container_key, min_role="read_only")

    try:
        expr = inject_container_into_metrics(body.expr, body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    params = {"query": expr}
    if body.time is not None:
        # changed: ensure query param values are strings
        params["time"] = str(body.time)

    async with build_async_client() as c:
        r = await c.get(f"{VMX}/api/v1/query", params=params)
    data = r.json()

    if shape == "raw" or data.get("status") != "success":
        return data

    d = data.get("data", {})
    if d.get("resultType") != "vector":
        return data

    return [
        VMFlatVectorEntry(metric=s["metric"], value=tuple(s["value"]), group=i)
        for i, s in enumerate(d.get("result", []), start=1)
    ]


# -------- Metrics: range (raw or flat) --------
RangeResponse = Union[VMApiResponse, List[VMFlatMatrixEntry]]


@router.post(
    "/metrics/query_range",
    response_model=RangeResponse,
    dependencies=[Depends(require_permission({"telemetry": ["query"]}))],
)
async def metrics_query_range(
    body: MetricsRangePayload,
    shape: Literal["raw", "flat"] = Query("raw", description='Return "raw" Prom/VM union or "flat" VMUI-like array'),
    session: AsyncSession = Depends(get_session),
    actor: ActorContext = Depends(get_actor_context),
):
    try:
        await resolve_container_selector_to_key(session, body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    container_key = body.container_key
    if not container_key:
        raise HTTPException(400, "container_key is required")
    await enforce_container_access(session, actor, container_key, min_role="read_only")

    try:
        expr = inject_container_into_metrics(body.expr, body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    # changed: build params with stringified numeric values to satisfy typing
    params = {"query": expr}
    if body.start is not None:
        params["start"] = str(body.start)
    if body.end is not None:
        params["end"] = str(body.end)
    if body.step is not None:
        params["step"] = str(body.step)

    async with build_async_client() as c:
        r = await c.get(f"{VMX}/api/v1/query_range", params=params)
    data = r.json()

    if shape == "raw" or data.get("status") != "success":
        return data

    d = data.get("data", {})
    if d.get("resultType") != "matrix":
        return data

    return [
        VMFlatMatrixEntry(metric=s["metric"], values=[tuple(v) for v in s["values"]], group=i)
        for i, s in enumerate(d.get("result", []), start=1)
    ]


@router.post(
    "/metrics/labels/names",
    response_model=List[str],
    dependencies=[Depends(require_permission({"telemetry": ["read"]}))],
)
async def metrics_label_names(
    body: MetricsLabelNamesPayload,
    session: AsyncSession = Depends(get_session),
    actor: ActorContext = Depends(get_actor_context),
) -> List[str]:
    try:
        await resolve_container_selector_to_key(session, body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    container_key = body.container_key
    if not container_key:
        raise HTTPException(400, "container_key is required")
    await enforce_container_access(session, actor, container_key, min_role="read_only")

    params = {"match[]": body.metrics_matcher()}
    if body.start is not None:
        params["start"] = str(body.start)
    if body.end is not None:
        params["end"] = str(body.end)

    async with build_async_client() as c:
        r = await c.get(f"{VMX}/api/v1/labels", params=params)
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)

    payload = r.json()
    if payload.get("status") != "success":
        raise HTTPException(502, payload.get("error", "VictoriaMetrics labels query failed"))

    return payload.get("data", [])


@router.post(
    "/metrics/labels/values",
    response_model=List[str],
    dependencies=[Depends(require_permission({"telemetry": ["read"]}))],
)
async def metrics_label_values(
    body: MetricsLabelValuesPayload,
    session: AsyncSession = Depends(get_session),
    actor: ActorContext = Depends(get_actor_context),
) -> List[str]:
    try:
        await resolve_container_selector_to_key(session, body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    container_key = body.container_key
    if not container_key:
        raise HTTPException(400, "container_key is required")
    await enforce_container_access(session, actor, container_key, min_role="read_only")

    label = (body.label or "").strip()
    if not label:
        raise HTTPException(400, "label must be provided")

    params = {"match[]": body.metrics_matcher()}
    if body.start is not None:
        params["start"] = str(body.start)
    if body.end is not None:
        params["end"] = str(body.end)

    encoded = quote(label, safe="")

    async with build_async_client() as c:
        r = await c.get(f"{VMX}/api/v1/label/{encoded}/values", params=params)
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)

    payload = r.json()
    if payload.get("status") != "success":
        raise HTTPException(502, payload.get("error", "VictoriaMetrics label values query failed"))

    return payload.get("data", [])
