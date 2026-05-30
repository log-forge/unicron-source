"""NotificationGroup model for notification delivery bundles.

Uses extend_existing=True to share table with Central's migrations.
Groups route alerts to named bundles of direct channels and presets.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class NotificationGroup(Base):
    """Named deployment-local delivery bundle."""

    __tablename__ = "notificationgroup"
    __table_args__ = {"schema": "notifications", "extend_existing": True}

    # Primary key using uuid4 hex string (32 chars)
    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)

    # Group identification
    name = Column(String, nullable=False)

    # Target configuration
    target_config = Column(JSONB, nullable=False, default=dict)

    # State
    enabled = Column(Boolean, nullable=False, default=True)

    # Audit fields
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


__all__ = ["NotificationGroup"]
