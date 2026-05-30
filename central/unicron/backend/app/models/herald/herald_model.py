import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import TIMESTAMP, BigInteger, Boolean, Column, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel
from unicron_shared import HeraldStatus

if TYPE_CHECKING:
    from app.models.container.container_model import Container


class Herald(SQLModel, table=True):
    # Auto-generated primary key using uuid4 hex string (32 chars)
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, primary_key=True, index=True),
        description="Primary key; auto-generated uuid4 hex",
    )
    herald_name: str = Field(sa_column=Column(String))
    central_url: str = Field(sa_column=Column(String))
    registered_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(TIMESTAMP(timezone=True), nullable=False),
    )
    health_status: HeraldStatus = Field(default=HeraldStatus.unknown, sa_column=Column(String, index=True))
    last_ping: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(TIMESTAMP(timezone=True), nullable=True),
    )
    health_message: str = Field(default="", sa_column=Column(String))
    check_in_interval: int = Field(default=60, description="Expected health check-in interval in seconds")
    # New metadata fields
    region: Optional[str] = Field(default=None, description="Region where the herald is deployed")
    tags: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
        description="Arbitrary classification tags",
    )
    hostname: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    herald_os: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    os_version: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    architecture: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    cpu_count: Optional[int] = Field(default=None, sa_column=Column(Integer, nullable=True))
    host_total_memory_bytes: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True),
    )
    herald_version: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    containers: List["Container"] = Relationship(back_populates="herald")
    # Socket presence tracking
    socket_online: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default="false"))
    socket_last_seen: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP(timezone=True), nullable=True),
        description="Last time a socket event (connect/ping/disconnect) was observed",
    )
    # Lifecycle tracking: mark a herald explicitly unregistered/uninstalled
    unregistered: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default="false"))
    unregistered_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP(timezone=True), nullable=True),
        description="Timestamp when the herald was explicitly unregistered",
    )
    unregistered_reason: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="Reason for deregistration (self/admin/cleanup)",
    )
    unregistered_by: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="Who initiated deregistration (e.g., self/admin)",
    )
