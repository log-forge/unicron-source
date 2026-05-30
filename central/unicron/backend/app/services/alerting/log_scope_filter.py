"""Scope-aware routing for log fan-out to the alert stream.

This module keeps a short-lived in-memory snapshot of enabled log-rule scopes
so Central can avoid publishing irrelevant logs to `unicron:logs`.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.models.alerting.alert_rule_model import AlertRule
from app.models.container.container_model import Container

logger = get_logger("services.alerting.log_scope_filter")

# Rule types that depend on log entries (stream path / log-based alerting)
LOG_TRIGGER_TYPES = {"keyword", "rate", "absence"}


@dataclass(slots=True)
class ScopeSnapshot:
    """Cached enabled log-rule scope state."""

    refreshed_at: float = 0.0
    has_global: bool = False
    fail_open: bool = False
    herald_ids: set[str] = field(default_factory=set)
    container_keys: set[str] = field(default_factory=set)

    def matches(self, *, host_id: str, container_key: str) -> bool:
        if self.fail_open or self.has_global:
            return True
        if container_key and container_key in self.container_keys:
            return True
        if host_id and host_id in self.herald_ids:
            return True
        return False


class LogScopeFilter:
    """Caches enabled log-rule scopes and evaluates routing relevance."""

    def __init__(self, *, refresh_interval_seconds: int = 60) -> None:
        self._refresh_interval_seconds = max(5, int(refresh_interval_seconds))
        self._snapshot = ScopeSnapshot()
        self._refresh_lock = asyncio.Lock()
        self._last_seen_version: int | None = None
        self._last_version_check_at: float = 0.0

    @staticmethod
    def _normalize_targets(values: Iterable[str] | None) -> list[str]:
        if not values:
            return []
        out: list[str] = []
        for raw in values:
            value = str(raw or "").strip()
            if value:
                out.append(value)
        return out

    @staticmethod
    def _is_container_key(value: str) -> bool:
        if ":" not in value:
            return False
        host_id, container_name = value.split(":", 1)
        return bool(host_id.strip()) and bool(container_name.strip())

    @staticmethod
    def _extract_log_identity(log_data: dict) -> tuple[str, str]:
        container_key = str(log_data.get("container_key", "") or "").strip()
        host_id = str(log_data.get("host_id", "") or "").strip()
        container_name = str(log_data.get("container_name", "") or "").strip()

        if not host_id and ":" in container_key:
            parsed_host, _ = container_key.split(":", 1)
            host_id = parsed_host.strip()

        if (not container_key or ":" not in container_key) and host_id and container_name:
            container_key = f"{host_id}:{container_name}"

        return host_id, container_key

    async def _version_changed(self) -> bool:
        """Check distributed rule-index version and detect invalidation."""
        now = time.time()
        check_interval = max(0.25, float(settings.REALTIME_RULE_INDEX_VERSION_CHECK_SECONDS))
        if now - self._last_version_check_at < check_interval:
            return False
        self._last_version_check_at = now

        try:
            redis = await get_redis()
            raw = await redis.get(settings.REALTIME_RULE_INDEX_VERSION_KEY)
            version = int(raw) if raw is not None else 0
        except Exception:
            logger.debug("Log scope version check failed", exc_info=True)
            return False

        if self._last_seen_version is None:
            self._last_seen_version = version
            return False

        if version != self._last_seen_version:
            self._last_seen_version = version
            return True
        return False

    async def _maybe_refresh(self, session: AsyncSession) -> ScopeSnapshot:
        now = time.time()
        current = self._snapshot
        stale_by_time = (now - current.refreshed_at) >= self._refresh_interval_seconds
        invalidate_by_version = False
        if not stale_by_time:
            invalidate_by_version = await self._version_changed()

        if not stale_by_time and not invalidate_by_version:
            return current

        async with self._refresh_lock:
            # Double-check after lock acquisition.
            now = time.time()
            current = self._snapshot
            stale_by_time = (now - current.refreshed_at) >= self._refresh_interval_seconds
            if not stale_by_time:
                invalidate_by_version = await self._version_changed()
            if not stale_by_time and not invalidate_by_version:
                return current

            stmt = select(AlertRule.scope_type, AlertRule.scope_targets).where(
                AlertRule.enabled == True,  # noqa: E712
                AlertRule.trigger_type.in_(list(LOG_TRIGGER_TYPES)),
            )
            rows = (await session.execute(stmt)).all()

            snapshot = ScopeSnapshot(refreshed_at=now)
            group_ids: set[str] = set()

            for scope_type, scope_targets in rows:
                scope = str(scope_type or "").strip().lower()
                targets = self._normalize_targets(scope_targets)

                if scope == "global":
                    snapshot.has_global = True
                    continue

                if scope == "herald":
                    snapshot.herald_ids.update(targets)
                    continue

                if scope == "container":
                    for target in targets:
                        if self._is_container_key(target):
                            snapshot.container_keys.add(target)
                        else:
                            # Legacy/non-canonical targets cannot be matched here.
                            # Fail open to avoid suppressing valid alerts.
                            snapshot.fail_open = True
                    continue

                if scope == "group":
                    group_ids.update(targets)
                    continue

                # Unknown scope type - fail open defensively.
                snapshot.fail_open = True

            if group_ids:
                group_stmt = select(Container.container_key).where(
                    Container.group_id.in_(list(group_ids))
                )
                group_rows = (await session.execute(group_stmt)).all()
                for (container_key,) in group_rows:
                    key = str(container_key or "").strip()
                    if self._is_container_key(key):
                        snapshot.container_keys.add(key)

            self._snapshot = snapshot
            logger.debug(
                "Refreshed log scope snapshot",
                extra={
                    "reason": "version" if invalidate_by_version else "interval",
                    "has_global": snapshot.has_global,
                    "fail_open": snapshot.fail_open,
                    "herald_scope_count": len(snapshot.herald_ids),
                    "container_scope_count": len(snapshot.container_keys),
                },
            )
            return snapshot

    async def filter_relevant(
        self,
        session: AsyncSession,
        logs: list[dict],
    ) -> list[dict]:
        """Return only logs that are relevant to currently enabled log-rule scopes."""
        if not logs:
            return []

        snapshot = await self._maybe_refresh(session)
        if snapshot.fail_open or snapshot.has_global:
            return logs

        relevant: list[dict] = []
        for item in logs:
            host_id, container_key = self._extract_log_identity(item)
            if snapshot.matches(host_id=host_id, container_key=container_key):
                relevant.append(item)
        return relevant


_scope_filter: LogScopeFilter | None = None


def get_log_scope_filter() -> LogScopeFilter:
    global _scope_filter
    if _scope_filter is None:
        _scope_filter = LogScopeFilter()
    return _scope_filter


__all__ = ["LogScopeFilter", "get_log_scope_filter"]
