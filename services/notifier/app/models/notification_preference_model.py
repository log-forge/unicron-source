"""NotificationPreference model for global notification delivery preferences."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Time
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class NotificationPreference(Base):
    """Singleton deployment-local notification preferences."""

    __tablename__ = "notificationpreference"
    __table_args__ = {"schema": "notifications", "extend_existing": True}

    id = Column(String, primary_key=True, default="global")

    quiet_hours_start = Column(Time, nullable=True)
    quiet_hours_end = Column(Time, nullable=True)
    quiet_hours_timezone = Column(String, nullable=True)

    min_severity = Column(String, nullable=False, default="info")
    preferred_channels = Column(JSONB, nullable=False, default=list)

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


__all__ = ["NotificationPreference"]
