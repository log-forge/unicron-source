from dataclasses import dataclass

from app.models.container.container_model import Container
from app.models.herald.herald_model import Herald
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


@dataclass(frozen=True)
class ActorContext:
    user_id: str | None
    team_ids: list[str]
    org_role: str | None


ROLE_DEFS = {
    "read_only": {
        "rank": 0,
        "allows": [
            "list/read containers",
            "view telemetry (logs/metrics)",
            "view alerts + alert history",
            "view read-only resource details",
        ],
        "denies": [
            "exec/operate actions",
            "changing resource controls",
        ],
    },
    "operator": {
        "rank": 1,
        "allows": [
            "everything in read_only",
            "operate actions (restart/stop/start)",
            "acknowledge/silence alerts",
            "manage alert rules/assignments for accessible scopes",
        ],
        "denies": [
            "changing resource controls",
        ],
    },
    "admin": {
        "rank": 2,
        "allows": [
            "everything in operator",
            "manage container and group controls",
        ],
        "denies": [
            "move containers between groups",
            "assign ungrouped containers to a group",
        ],
    },
}

ROLE_ORDER = {role: spec["rank"] for role, spec in ROLE_DEFS.items()}


def max_role(*roles: str | None) -> str | None:
    candidates = [role for role in roles if role in ROLE_ORDER]
    if not candidates:
        return None
    return max(candidates, key=lambda role: ROLE_ORDER[role])


def meets_min_role(role: str | None, min_role: str) -> bool:
    if role not in ROLE_ORDER:
        return False
    if min_role not in ROLE_ORDER:
        return False
    return ROLE_ORDER[role] >= ROLE_ORDER[min_role]


async def resolve_group_role(
    session: AsyncSession,
    actor: ActorContext,
    group_id: str,
) -> str | None:
    return "admin" if actor.org_role in {"owner", "admin"} or actor.user_id else None


async def resolve_container_role(
    session: AsyncSession,
    actor: ActorContext,
    container_key: str,
) -> str | None:
    return "admin" if actor.org_role in {"owner", "admin"} or actor.user_id else None


async def list_accessible_container_keys(
    session: AsyncSession,
    actor: ActorContext,
    min_role: str = "read_only",
) -> list[str]:
    if actor.org_role in {"owner", "admin"} or actor.user_id:
        stmt = (
            select(getattr(Container, "container_key"))
            .join(Herald, getattr(Container, "herald_id") == getattr(Herald, "id"))
            .where(getattr(Herald, "unregistered") == False)  # noqa: E712
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    return []


__all__ = [
    "ActorContext",
    "ROLE_DEFS",
    "ROLE_ORDER",
    "max_role",
    "meets_min_role",
    "resolve_group_role",
    "resolve_container_role",
    "list_accessible_container_keys",
]
