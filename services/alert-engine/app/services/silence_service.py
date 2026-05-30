"""
Silence service for alert-engine.

Provides business logic for silence CRUD operations and matcher evaluation.
This service is independent of Central and manages its own model definition
that maps to the shared alerting.silence table.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel

from app.core.logging import get_logger
from app.schemas.silence_schemas import SilenceCreateRequest, SilenceUpdateRequest

logger = get_logger("alert-engine.services.silence")


class Silence(SQLModel, table=True):
    """
    Alert silence configuration for maintenance windows.

    This mirrors the Silence model from Central but is defined here
    to keep alert-engine independent. Both services connect to the same
    PostgreSQL database and share the alerting.silence table.
    """

    __tablename__ = "silence"
    __table_args__ = (
        Index("ix_silence_organization_id", "organization_id"),
        Index("ix_silence_starts_at", "starts_at"),
        Index("ix_silence_ends_at", "ends_at"),
        Index(
            "ix_silence_active_window",
            "organization_id",
            "starts_at",
            "ends_at",
        ),
        {"schema": "alerting", "extend_existing": True},
    )

    # Primary key using uuid4 hex string (32 chars)
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, primary_key=True, index=True),
    )

    # Matchers define which alerts are silenced
    matchers: List[Dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
    )

    # Time window
    starts_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    ends_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    # Audit fields
    created_by: str = Field(
        sa_column=Column(String, nullable=False),
    )
    comment: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )

    # Recurrence support
    recurring: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    recurrence_rule: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
    )

    # State
    expired: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )

    # Multi-tenancy
    organization_id: str = Field(
        sa_column=Column(String, nullable=False),
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class SilenceNotFoundError(Exception):
    """Raised when a silence is not found in the database."""

    pass


class SilenceService:
    """
    Service for silence operations.

    Provides CRUD operations with business logic and organization scoping.
    All operations are scoped to an organization for multi-tenant isolation.
    """

    def __init__(self, session: AsyncSession):
        """Initialize the service with a database session."""
        self.session = session

    async def create_silence(
        self,
        data: SilenceCreateRequest,
        org_id: str,
        user_id: str,
    ) -> Silence:
        """
        Create a new silence.

        Args:
            data: Silence creation data.
            org_id: Organization ID for multi-tenant isolation.
            user_id: User ID who created the silence.

        Returns:
            The created Silence instance.
        """
        # Convert matchers to dict format
        matchers_list = [m.model_dump() for m in data.matchers]

        silence = Silence(
            id=uuid.uuid4().hex,
            matchers=matchers_list,
            starts_at=data.starts_at,
            ends_at=data.ends_at,
            created_by=user_id,
            comment=data.comment,
            recurring=data.recurring,
            recurrence_rule=data.recurrence_rule,
            expired=False,
            organization_id=org_id,
        )
        self.session.add(silence)
        await self.session.commit()
        await self.session.refresh(silence)
        logger.info("Created silence %s for org %s", silence.id, org_id)
        return silence

    async def get_silence(
        self, silence_id: str, org_id: str
    ) -> Optional[Silence]:
        """
        Get a silence by ID, scoped to organization.

        Args:
            silence_id: The silence ID to look up.
            org_id: The organization ID for scoping.

        Returns:
            The Silence if found, None otherwise.
        """
        stmt = select(Silence).where(
            Silence.id == silence_id,
            Silence.organization_id == org_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_silence_or_raise(
        self, silence_id: str, org_id: str
    ) -> Silence:
        """
        Get a silence by ID or raise SilenceNotFoundError.

        Args:
            silence_id: The silence ID to look up.
            org_id: The organization ID for scoping.

        Returns:
            The Silence if found.

        Raises:
            SilenceNotFoundError: If the silence is not found.
        """
        silence = await self.get_silence(silence_id, org_id)
        if not silence:
            raise SilenceNotFoundError(f"Silence {silence_id} not found")
        return silence

    async def list_silences(
        self,
        org_id: str,
        *,
        active_only: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[List[Silence], int]:
        """
        List silences for an organization with pagination.

        Args:
            org_id: The organization ID for scoping.
            active_only: If True, only return active (non-expired) silences.
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            A tuple of (list of silences, total count).
        """
        # Build base query
        stmt = select(Silence).where(Silence.organization_id == org_id)

        if active_only:
            now = datetime.now(timezone.utc)
            stmt = stmt.where(
                Silence.expired == False,  # noqa: E712
                Silence.starts_at <= now,
                Silence.ends_at > now,
            )

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar_one()

        # Apply pagination
        stmt = stmt.order_by(Silence.starts_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        silences = list(result.scalars().all())

        return silences, total

    async def update_silence(
        self,
        silence_id: str,
        org_id: str,
        data: SilenceUpdateRequest,
    ) -> Silence:
        """
        Update an existing silence.

        Args:
            silence_id: The silence ID to update.
            org_id: The organization ID for scoping.
            data: The update data.

        Returns:
            The updated Silence.

        Raises:
            SilenceNotFoundError: If the silence is not found.
        """
        silence = await self.get_silence_or_raise(silence_id, org_id)

        if data.ends_at is not None:
            silence.ends_at = data.ends_at
        if data.comment is not None:
            silence.comment = data.comment

        silence.updated_at = datetime.now(timezone.utc)

        self.session.add(silence)
        await self.session.commit()
        await self.session.refresh(silence)
        logger.info("Updated silence %s", silence_id)
        return silence

    async def expire_silence(self, silence_id: str, org_id: str) -> Silence:
        """
        Expire a silence early.

        Args:
            silence_id: The silence ID to expire.
            org_id: The organization ID for scoping.

        Returns:
            The expired Silence.

        Raises:
            SilenceNotFoundError: If the silence is not found.
        """
        silence = await self.get_silence_or_raise(silence_id, org_id)
        silence.expired = True
        silence.updated_at = datetime.now(timezone.utc)

        self.session.add(silence)
        await self.session.commit()
        await self.session.refresh(silence)
        logger.info("Expired silence %s", silence_id)
        return silence

    async def delete_silence(self, silence_id: str, org_id: str) -> bool:
        """
        Delete a silence.

        Args:
            silence_id: The silence ID to delete.
            org_id: The organization ID for scoping.

        Returns:
            True if the silence was deleted.

        Raises:
            SilenceNotFoundError: If the silence is not found.
        """
        silence = await self.get_silence_or_raise(silence_id, org_id)
        await self.session.delete(silence)
        await self.session.commit()
        logger.info("Deleted silence %s", silence_id)
        return True

    async def get_active_silences(self, org_id: str) -> List[Silence]:
        """
        Get all currently active silences for an organization.

        Args:
            org_id: The organization ID for scoping.

        Returns:
            List of active silences.
        """
        now = datetime.now(timezone.utc)
        stmt = select(Silence).where(
            Silence.organization_id == org_id,
            Silence.expired == False,  # noqa: E712
            Silence.starts_at <= now,
            Silence.ends_at > now,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def matches_alert(self, silence: Silence, alert_labels: Dict[str, str]) -> bool:
        """
        Check if all matchers match the alert labels.

        A silence matches an alert if ALL matchers match (AND logic).

        Args:
            silence: The silence to check.
            alert_labels: The alert's labels to match against.

        Returns:
            True if all matchers match, False otherwise.
        """
        for matcher in silence.matchers:
            label_value = alert_labels.get(matcher["name"])
            if not self._match_single(matcher, label_value):
                return False
        return True

    def _match_single(self, matcher: dict, value: Optional[str]) -> bool:
        """
        Check if a single matcher matches the value.

        Args:
            matcher: The matcher configuration.
            value: The value to match against (None if label not present).

        Returns:
            True if the matcher matches, False otherwise.
        """
        if value is None:
            # Not-equal matches missing labels
            return not matcher.get("is_equal", True)

        if matcher.get("is_regex"):
            try:
                matches = bool(re.match(matcher["value"], value))
            except re.error:
                logger.warning(
                    "Invalid regex pattern in matcher: %s", matcher["value"]
                )
                matches = False
        else:
            matches = value == matcher["value"]

        return matches if matcher.get("is_equal", True) else not matches

    async def is_silenced(
        self, org_id: str, alert_labels: Dict[str, str]
    ) -> bool:
        """
        Check if any active silence matches the alert labels.

        Args:
            org_id: The organization ID.
            alert_labels: The alert's labels to check.

        Returns:
            True if the alert should be silenced, False otherwise.
        """
        active_silences = await self.get_active_silences(org_id)
        for silence in active_silences:
            if self.matches_alert(silence, alert_labels):
                logger.debug(
                    "Alert silenced by silence %s (org %s)",
                    silence.id,
                    org_id,
                )
                return True
        return False


__all__ = ["SilenceService", "Silence", "SilenceNotFoundError"]
