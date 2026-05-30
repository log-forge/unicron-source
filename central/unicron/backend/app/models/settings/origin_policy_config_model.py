import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class OriginPolicyConfig(SQLModel, table=True):
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, primary_key=True, index=True),
        description="Primary key for the browser origin policy configuration",
    )
    allowed_origins: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
        description="UI-managed browser origin allowlist additions for HTTP and Socket.IO.",
    )
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Timestamp when the config row was created",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Timestamp when the config row was last updated",
    )


__all__ = ["OriginPolicyConfig"]
