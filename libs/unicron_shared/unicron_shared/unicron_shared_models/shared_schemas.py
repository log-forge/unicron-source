from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Literal, Optional, TypeVar, Union

from pydantic import BaseModel, Field

from ..unicron_shared_classes.shared_classes import HeraldStatus

T = TypeVar("T")


class HeraldHealthRequest(BaseModel):
    herald_name: Optional[str]
    status: HeraldStatus = HeraldStatus.unknown
    timestamp: str
    message: Optional[str] = ""


class HeraldHealthResponse(BaseModel):
    success: bool
    herald_name: Optional[str]
    herald_id: str
    status: str


class ContainerStaticMetrics(BaseModel):
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


class ContainerState(BaseModel):
    name: str
    docker_container_id: Optional[str] = None
    status: Optional[str] = None
    started_at: Optional[datetime] = None
    monitoring_enabled: bool = False
    group: Optional[str] = None
    static: Optional[ContainerStaticMetrics] = None


class HeraldStaticMetrics(BaseModel):
    hostname: Optional[str] = None
    os: Optional[str] = None
    os_version: Optional[str] = None
    architecture: Optional[str] = None
    cpu_count: Optional[int] = None
    total_memory_bytes: Optional[int] = None
    herald_version: Optional[str] = None


class HeraldInventoryPayload(BaseModel):
    herald_id: str
    reported_at: datetime
    sequence: Optional[int] = None
    containers: List[ContainerState] = Field(default_factory=list)
    herald_static: Optional[HeraldStaticMetrics] = None


class HeraldInventoryResponse(BaseModel):
    accepted: bool = True
    accepted_sequence: Optional[int] = None
    processed_at: datetime


class InventoryTriggerAck(BaseModel):
    triggered: bool = True
    scheduled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# === Socket.IO ACK schemas (shared) ===
class AckOk(BaseModel, Generic[T]):
    ok: Literal[True] = True
    data: Optional[T] = None


class AckErr(BaseModel, Generic[T]):
    ok: Literal[False] = False
    error: Optional[List[T]] = None


Ack = Union[AckOk, AckErr]


class PongData(BaseModel):
    msg: str


__all__ = [
    "HeraldHealthRequest",
    "HeraldHealthResponse",
    "HeraldStatus",
    "ContainerState",
    "ContainerStaticMetrics",
    "HeraldInventoryPayload",
    "HeraldInventoryResponse",
    "HeraldStaticMetrics",
    "InventoryTriggerAck",
    "Ack",
    "AckOk",
    "AckErr",
    "PongData",
]
