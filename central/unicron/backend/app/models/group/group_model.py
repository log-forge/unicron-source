import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Column, DateTime, String
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.container.container_model import Container


class Group(SQLModel, table=True):
    # Auto-generated primary key using uuid4 hex string (32 chars)
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, primary_key=True, index=True),
        description="Primary key for the group record",
    )
    name: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Timestamp when the group was created",
    )
    containers: List["Container"] = Relationship(back_populates="group")


__all__ = ["Group"]
