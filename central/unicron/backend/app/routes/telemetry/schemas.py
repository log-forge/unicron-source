from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from app.base_schemas import ContainerSelector
from app.telemetry.victoria.schemas import LogRow, VMData
from pydantic import BaseModel, Field

from unicron_shared import HeraldStatus


class LogsQueryPayload(ContainerSelector):
    """
    Range (finite) logs query.
    Either supply a full LogsQL expression in `expr` (we will prepend the container predicate),
    OR provide `where` (boolean-only) + `pipes` (your pipeline, starting w/ or w/o '|').
    """

    expr: Optional[str] = None
    where: Optional[str] = None
    pipes: Optional[str] = None
    start: Optional[str] = None  # RFC3339 or relative ("5m")
    end: Optional[str] = None
    limit: int = 200
    account_id: Optional[int] = None  # multi-tenant headers (optional)
    project_id: Optional[int] = None


class LogsQueryResponse(BaseModel):
    """
    Response for POST /telemetry/victoria/logs/query
    """

    rows: List[LogRow] = Field(description="Finite list of rows returned by VictoriaLogs")
    count: int = Field(description="Convenience count of rows")
    query: str = Field(description="The final LogsQL expression executed (container predicate injected)")


class LogsTailTestResponse(BaseModel):
    """
    Response for POST /telemetry/victoria/logs/tail/test (debug helper).
    Shows the exact boolean-only filter used with /tail.
    """

    tail_expr: str = Field(description="Boolean-only LogsQL filter for /tail")


class MetricsInstantPayload(ContainerSelector):
    expr: str
    time: Optional[float] = None  # unix seconds


class MetricsRangePayload(ContainerSelector):
    expr: str
    start: float  # unix seconds
    end: float
    step: str  # e.g. "15s"


class MetricsLabelNamesPayload(ContainerSelector):
    start: Optional[float] = None  # unix seconds
    end: Optional[float] = None


class MetricsLabelValuesPayload(MetricsLabelNamesPayload):
    label: str


class VMApiSuccess(BaseModel):
    status: Literal["success"] = "success"
    data: VMData
    warnings: Optional[List[str]] = None


class VMApiError(BaseModel):
    status: Literal["error"] = "error"
    errorType: str
    error: str
    warnings: Optional[List[str]] = None


# Union response type for FastAPI response_model
VMApiResponse = Union[VMApiSuccess, VMApiError]


class HeraldInventoryRecord(BaseModel):
    herald_id: str
    herald_name: str
    central_url: str
    registered_at: Optional[datetime] = None
    health_status: HeraldStatus = HeraldStatus.unknown
    last_ping: Optional[datetime] = None
    health_message: Optional[str] = None
    check_in_interval: int
    region: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    socket_online: bool = False
    socket_last_seen: Optional[datetime] = None
    hostname: Optional[str] = None
    herald_os: Optional[str] = None
    os_version: Optional[str] = None
    architecture: Optional[str] = None
    cpu_count: Optional[int] = None
    host_total_memory_bytes: Optional[int] = None
    herald_version: Optional[str] = None


class ContainerInventoryRecord(BaseModel):
    name: str
    container_key: str
    docker_container_id: Optional[str] = None
    status: Optional[str] = None
    started_at: Optional[datetime] = None
    monitoring_enabled: bool = False
    group: Optional[str] = None
    image: Optional[str] = None
    image_id: Optional[str] = None
    labels: Dict[str, str] = Field(default_factory=dict)
    cpu_limit: Optional[float] = None
    memory_limit_bytes: Optional[int] = None
    restart_policy: Optional[str] = None
    created_at: Optional[datetime] = None
    command: Optional[str] = None
    entrypoint: Optional[str] = None
    working_dir: Optional[str] = None
    environment: List[str] = Field(default_factory=list)
    mounts: List[Dict[str, Any]] = Field(default_factory=list)
    ports: Dict[str, List[Dict[str, Optional[str]]]] = Field(default_factory=dict)
    networks: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class InventorySnapshotResponse(BaseModel):
    generated_at: datetime
    heralds: List[HeraldInventoryRecord] = Field(default_factory=list)
    containers: List[ContainerInventoryRecord] = Field(default_factory=list)


__all__ = [
    "HeraldInventoryRecord",
    "ContainerInventoryRecord",
    "InventorySnapshotResponse",
]
