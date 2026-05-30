"""Alert grouping service for notification batching.

Groups related alerts together to prevent alert storms and enable
efficient notification delivery. Alerts are grouped by configurable
labels and batched based on timing parameters.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger

logger = get_logger("alert-engine.services.grouping")


@dataclass
class AlertGroup:
    """
    A group of related alerts pending notification.

    Alerts are grouped together when they share the same grouping key,
    which is derived from configurable label values.
    """

    key: str
    """Unique grouping key derived from alert labels."""

    alerts: List[Dict[str, Any]] = field(default_factory=list)
    """List of alert data in this group."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    """Timestamp when the first alert joined this group."""

    last_alert_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    """Timestamp when the most recent alert joined this group."""


class AlertGrouper:
    """
    Groups related alerts for notification batching.

    Implements time-based grouping with two configurable parameters:
    - group_wait: How long to wait after first alert before sending (default 30s)
    - group_interval: How long to keep grouping subsequent alerts (default 300s)

    Alerts are grouped by a configurable set of labels (group_by).
    Default grouping is by rule_id and severity.
    """

    # Default labels to group by
    DEFAULT_GROUP_BY = ["rule_id", "severity"]

    def __init__(
        self,
        group_wait_seconds: int = 30,
        group_interval_seconds: int = 300,
    ):
        """
        Initialize the grouper.

        Args:
            group_wait_seconds: Time to wait after first alert before group is ready.
            group_interval_seconds: Time window for grouping subsequent alerts.
        """
        self.group_wait_seconds = group_wait_seconds
        self.group_interval_seconds = group_interval_seconds

        # In-memory group state: key -> AlertGroup
        self._groups: Dict[str, AlertGroup] = {}

    def get_grouping_key(
        self,
        alert_labels: Dict[str, str],
        group_by: Optional[List[str]] = None,
    ) -> str:
        """
        Generate a grouping key from specified labels.

        Args:
            alert_labels: The alert's labels dictionary.
            group_by: List of label names to use for grouping.
                     Defaults to ["rule_id", "severity"].

        Returns:
            A colon-separated string key for grouping.
        """
        if not group_by:
            group_by = self.DEFAULT_GROUP_BY

        # Build key from sorted label names for consistency
        key_parts = []
        for label in sorted(group_by):
            value = alert_labels.get(label, "")
            key_parts.append(f"{label}={value}")

        return ":".join(key_parts)

    def add_alert(
        self,
        alert_id: str,
        labels: Dict[str, str],
        annotations: Optional[Dict[str, Any]] = None,
        group_by: Optional[List[str]] = None,
    ) -> str:
        """
        Add an alert to a pending group.

        If no group exists for the alert's grouping key, a new group is created.
        Otherwise, the alert joins the existing group.

        Args:
            alert_id: Unique identifier for the alert.
            labels: The alert's labels dictionary.
            annotations: Optional alert annotations.
            group_by: Optional custom grouping labels (from rule annotations).

        Returns:
            The grouping key the alert was added to.
        """
        key = self.get_grouping_key(labels, group_by)
        now = datetime.now(timezone.utc)

        # Build alert data
        alert_data = {
            "alert_id": alert_id,
            "labels": labels,
            "annotations": annotations or {},
            "added_at": now.isoformat(),
        }

        if key not in self._groups:
            # Create new group
            self._groups[key] = AlertGroup(
                key=key,
                alerts=[alert_data],
                created_at=now,
                last_alert_at=now,
            )
            logger.debug(
                "Created new alert group: key=%s, alert_id=%s",
                key,
                alert_id,
            )
        else:
            # Add to existing group
            group = self._groups[key]
            group.alerts.append(alert_data)
            group.last_alert_at = now
            logger.debug(
                "Added alert to existing group: key=%s, alert_id=%s, group_size=%d",
                key,
                alert_id,
                len(group.alerts),
            )

        return key

    def get_ready_groups(self) -> List[AlertGroup]:
        """
        Return groups that are ready for notification.

        A group is ready when:
        - At least group_wait_seconds have passed since first alert

        Groups are removed from pending state when returned.

        Returns:
            List of AlertGroup instances ready for notification.
        """
        now = datetime.now(timezone.utc)
        ready: List[AlertGroup] = []
        to_remove: List[str] = []

        for key, group in self._groups.items():
            elapsed = (now - group.created_at).total_seconds()

            if elapsed >= self.group_wait_seconds:
                ready.append(group)
                to_remove.append(key)
                logger.info(
                    "Alert group ready: key=%s, alerts=%d, waited=%.1fs",
                    key,
                    len(group.alerts),
                    elapsed,
                )

        # Remove ready groups from pending
        for key in to_remove:
            del self._groups[key]

        return ready

    def should_start_new_group(
        self,
        key: str,
    ) -> bool:
        """
        Check if a new group should be started for this key.

        A new group should be started if:
        - No existing group for the key, OR
        - Existing group has exceeded group_interval_seconds

        Args:
            key: The grouping key to check.

        Returns:
            True if a new group should be started.
        """
        if key not in self._groups:
            return True

        group = self._groups[key]
        now = datetime.now(timezone.utc)
        elapsed = (now - group.created_at).total_seconds()

        return elapsed >= self.group_interval_seconds

    def get_pending_count(self) -> int:
        """Return the number of pending alert groups."""
        return len(self._groups)

    def get_total_alerts_pending(self) -> int:
        """Return the total number of alerts in pending groups."""
        return sum(len(g.alerts) for g in self._groups.values())

    def clear(self) -> None:
        """Clear all pending groups."""
        self._groups.clear()
        logger.debug("Cleared all pending alert groups")


__all__ = ["AlertGrouper", "AlertGroup"]
