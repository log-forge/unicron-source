import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import TIMESTAMP, Column, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class Herald_Token(SQLModel, table=True):
    # Auto-generated primary key using uuid4 hex if not explicitly provided
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, primary_key=True, index=True),
        description="Primary key; auto-generated uuid4 hex",
    )
    organization_id: str = Field(
        sa_column=Column(String, index=True),
        description="Organization ID associated with this herald token",
    )
    herald_name: str = Field(default="herald", sa_column=Column(String))
    central_url: str = Field(sa_column=Column(String))
    status: str = Field(default="pending", sa_column=Column(String, index=True))
    reason: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    failure_details: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(TIMESTAMP(timezone=True), nullable=False),
    )
    check_in_interval: int = Field(default=60, description="Expected health check-in interval in seconds")
    # New metadata fields
    region: Optional[str] = Field(default=None, description="Region where the herald is deployed")
    tags: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
        description="Arbitrary classification tags",
    )
