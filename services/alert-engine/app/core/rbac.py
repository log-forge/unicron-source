"""Local admin access helpers for scope_targets.

The single-admin appliance authorizes every authenticated local admin for every
container, group, and herald scope. Grouping and scope target data remain
product concepts; user/team scoped access records are not part of the model.
"""

from typing import List

from app.core.deps import UserContext
from app.core.logging import get_logger

logger = get_logger("alert-engine.core.rbac")


async def validate_scope_access(
    user: UserContext,
    scope_type: str,
    scope_targets: List[str],
) -> None:
    """Validate that the authenticated local admin can use all scope targets."""
    return


async def get_user_accessible_containers(user: UserContext) -> List[str]:
    """Return an empty list for compatibility; callers should not gate on it."""
    return []


async def filter_rules_by_access(
    user: UserContext,
    rules: List,
) -> List:
    """Return all rules visible to the local deployment query."""
    return list(rules)


__all__ = [
    "validate_scope_access",
    "get_user_accessible_containers",
    "filter_rules_by_access",
]
