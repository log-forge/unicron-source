import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from app.models.group.group_model import Group
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.herald.herald_model import Herald


class Container(SQLModel, table=True):
    # Auto-generated primary key using uuid4 hex string (32 chars)
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, primary_key=True, index=True),
        description="Primary key for the container record",
    )
    name: str = Field(
        sa_column=Column(String, nullable=False, index=True),
        description="Reported container name (not guaranteed unique)",
    )
    container_key: str = Field(
        sa_column=Column(String, unique=True, nullable=False, index=True),
        description="Canonical durable container identifier derived from herald_id:name",
    )
    docker_container_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True, index=True),
        description="Runtime Docker container identifier used only for correlation",
    )
    started_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Timestamp when the container started",
    )
    status: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="Current runtime status (running, exited, etc.)",
    )
    monitoring_enabled: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
        description="Durable monitoring intent for this container",
    )
    image: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="Container image reported by Docker",
    )
    image_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="Resolved image identifier",
    )
    labels: Dict[str, str] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description="Container label key/value metadata",
    )
    cpu_limit: Optional[float] = Field(
        default=None,
        sa_column=Column(Float, nullable=True),
        description="Configured CPU limit (cores)",
    )
    memory_limit_bytes: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True),
        description="Configured memory limit in bytes",
    )
    restart_policy: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="Restart policy name",
    )
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Timestamp when the container definition was created",
    )
    last_inventory_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Timestamp of the last inventory update that confirmed this container",
    )
    command: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="Full container command",
    )
    entrypoint: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="Resolved container entrypoint",
    )
    working_dir: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="Container working directory",
    )
    environment: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
        description="Environment variables for the container",
    )
    mounts: List[Dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
        description="Sanitized mount metadata",
    )
    ports: Dict[str, List[Dict[str, Optional[str]]]] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description="Published ports and bindings",
    )
    networks: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description="Network attachments and configuration",
    )
    herald_id: Optional[str] = Field(
        default=None,
        foreign_key="herald.id",
        description="Foreign key to the owning herald",
    )
    herald: Optional["Herald"] = Relationship(back_populates="containers")
    group_id: Optional[str] = Field(
        default=None,
        foreign_key="group.id",
        ondelete="SET NULL",
        description="Foreign key to the owning group",
    )
    group: Optional[Group] = Relationship(back_populates="containers")

    __table_args__ = (
        Index("ix_container_name_group_id", "name", "group_id"),
        Index("ix_container_herald_id", "herald_id"),
        Index("ix_container_herald_name", "herald_id", "name"),
    )


__all__ = ["Container"]
