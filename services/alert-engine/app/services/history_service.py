"""
Alert history service for querying triggered alert records.

Provides comprehensive search capabilities with filtering by time range,
severity, status, rule, and container.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, DateTime, Index, String, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel

from app.core.logging import get_logger
from app.schemas.history_schemas import AlertHistorySearchParams

logger = get_logger("alert-engine.services.history")


class AlertHistory(SQLModel, table=True):
    """
    Historical record of triggered alerts.

    This mirrors the AlertHistory model from Central but is defined here
    to keep alert-engine independent. Both services connect to the same
    PostgreSQL database and share the alerting.alerthistory table.
    """

    __tablename__ = "alerthistory"
    __table_args__ = (
        Index("ix_alerthistory_rule_id", "rule_id"),
        Index("ix_alerthistory_organization_id", "organization_id"),
        Index("ix_alerthistory_status", "status"),
        Index("ix_alerthistory_severity", "severity"),
        Index("ix_alerthistory_triggered_at", "triggered_at"),
        Index(
            "ix_alerthistory_org_triggered_at",
            "organization_id",
            "triggered_at",
        ),
        {
            "schema": "alerting",
            "extend_existing": True,
            "postgresql_partition_by": "RANGE (triggered_at)",
        },
    )

    # Primary key using uuid4 hex string (32 chars)
    # Note: For partitioned tables, PK must include partition key
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, nullable=False),
        description="Primary key; auto-generated uuid4 hex",
    )

    # Alert reference (denormalized for history queries without joins)
    rule_id: str = Field(
        sa_column=Column(String, nullable=False),
        description="Reference to the alert rule that triggered",
    )
    rule_name: str = Field(
        sa_column=Column(String, nullable=False),
        description="Denormalized rule name at time of trigger",
    )

    # Alert details
    severity: str = Field(
        sa_column=Column(String, nullable=False),
        description="Alert severity: critical, warning, info",
    )
    message: str = Field(
        sa_column=Column(Text, nullable=False),
        description="Alert message with template variables expanded",
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description="Alert context: container ID, labels, metric values, log excerpts",
    )

    # State transitions
    status: str = Field(
        default="triggered",
        sa_column=Column(String, nullable=False, server_default="'triggered'"),
        description="Alert status: triggered, acknowledged, silenced",
    )

    # Timestamps (triggered_at is partition key)
    triggered_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, primary_key=True),
        description="Timestamp when the alert was triggered (partition key)",
    )
    acknowledged_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Timestamp when the alert was acknowledged",
    )
    acknowledged_by: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="User ID who acknowledged the alert",
    )

    # Multi-tenancy
    organization_id: str = Field(
        sa_column=Column(String, nullable=False),
        description="Organization ID for multi-tenant isolation",
    )


class AlertHistoryCreate(SQLModel):
    """Schema for creating alert history entries."""

    rule_id: str
    rule_name: str
    severity: str
    message: str
    context: Dict[str, Any] = Field(default_factory=dict)
    status: str = "triggered"
    organization_id: str
    triggered_at: Optional[datetime] = None


class HistoryNotFoundError(Exception):
    """Raised when an alert history entry is not found."""

    pass


class AlertHistoryService:
    """
    Service for querying alert history.

    Provides search capabilities with multiple filter options and pagination.
    All queries are scoped to an organization for multi-tenant isolation.
    """

    def __init__(self, session: AsyncSession):
        """Initialize the service with a database session."""
        self.session = session

    async def search(
        self, org_id: str, params: AlertHistorySearchParams
    ) -> tuple[List[AlertHistory], int]:
        """
        Search alert history with filters.

        Args:
            org_id: Organization ID for scoping.
            params: Search parameters with filters.

        Returns:
            A tuple of (list of history entries, total count).
        """
        conditions = [AlertHistory.organization_id == org_id]

        # Time range filter
        if params.start_time:
            conditions.append(AlertHistory.triggered_at >= params.start_time)
        if params.end_time:
            conditions.append(AlertHistory.triggered_at <= params.end_time)

        # Severity filter
        if params.severity:
            conditions.append(AlertHistory.severity == params.severity)

        # Status filter
        if params.status:
            conditions.append(AlertHistory.status == params.status)

        # Rule filter
        if params.rule_id:
            conditions.append(AlertHistory.rule_id == params.rule_id)

        # Container key filter (JSONB query)
        if params.container_id:
            conditions.append(
                AlertHistory.context["container_id"].astext == params.container_id
            )

        # Fetch page + total in one query to reduce DB round trips.
        paged_stmt = (
            select(AlertHistory, func.count().over().label("full_count"))
            .where(*conditions)
            .order_by(AlertHistory.triggered_at.desc())
            .offset(params.offset)
            .limit(params.limit)
        )
        result = await self.session.execute(paged_stmt)
        rows = result.all()

        items = [row[0] for row in rows]
        total = int(rows[0][1]) if rows else 0

        return items, total

    async def get_by_id(
        self, history_id: str, org_id: str
    ) -> Optional[AlertHistory]:
        """
        Get a single history entry by ID.

        Args:
            history_id: The history entry ID.
            org_id: Organization ID for scoping.

        Returns:
            The AlertHistory if found, None otherwise.
        """
        stmt = select(AlertHistory).where(
            AlertHistory.id == history_id,
            AlertHistory.organization_id == org_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_or_raise(
        self, history_id: str, org_id: str
    ) -> AlertHistory:
        """
        Get a single history entry by ID or raise HistoryNotFoundError.

        Args:
            history_id: The history entry ID.
            org_id: Organization ID for scoping.

        Returns:
            The AlertHistory if found.

        Raises:
            HistoryNotFoundError: If the entry is not found.
        """
        entry = await self.get_by_id(history_id, org_id)
        if not entry:
            raise HistoryNotFoundError(f"History entry {history_id} not found")
        return entry

    async def create(self, data: AlertHistoryCreate) -> AlertHistory:
        """
        Create a new alert history entry.

        Args:
            data: The history entry data.

        Returns:
            The created AlertHistory instance.
        """
        entry = AlertHistory(
            id=uuid.uuid4().hex,
            rule_id=data.rule_id,
            rule_name=data.rule_name,
            severity=data.severity,
            message=data.message,
            context=data.context,
            status=data.status,
            organization_id=data.organization_id,
            triggered_at=data.triggered_at or datetime.now(timezone.utc),
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        logger.info(
            "Created history entry %s for rule %s", entry.id, entry.rule_id
        )
        return entry


__all__ = [
    "AlertHistory",
    "AlertHistoryCreate",
    "AlertHistoryService",
    "HistoryNotFoundError",
]
