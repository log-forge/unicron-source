from typing import Iterable, List, Optional, Sequence

from app.models.group.group_model import Group
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


async def get_group(session: AsyncSession, group_id: str) -> Optional[Group]:
    return await session.get(Group, group_id)


async def get_group_by_name(session: AsyncSession, name: str) -> Optional[Group]:
    normalized = (name or "").strip()
    if not normalized:
        return None

    stmt = select(Group).where(getattr(Group, "name") == normalized)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_groups(session: AsyncSession) -> List[Group]:
    stmt = select(Group).order_by(getattr(Group, "name").asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def ensure_group(session: AsyncSession, name: str, *, commit: bool = True) -> Group:
    normalized = (name or "").strip()
    if not normalized:
        raise ValueError("Group name must be non-empty")

    existing = await get_group_by_name(session, normalized)
    if existing is not None:
        return existing

    group = Group(name=normalized)
    session.add(group)
    if commit:
        await session.commit()
        await session.refresh(group)
    else:
        await session.flush()
    return group


async def ensure_groups(session: AsyncSession, names: Iterable[str]) -> List[Group]:
    normalized = sorted({(name or "").strip() for name in names if name and name.strip()})
    if not normalized:
        return []

    name_column = getattr(Group, "name")
    stmt = select(Group).where(name_column.in_(normalized))
    result = await session.execute(stmt)
    existing = {group.name: group for group in result.scalars().all()}

    groups: List[Group] = []
    created: List[Group] = []

    for name in normalized:
        group = existing.get(name)
        if group is not None:
            groups.append(group)
            continue

        group = Group(name=name)
        session.add(group)
        groups.append(group)
        created.append(group)

    if created:
        await session.commit()
        for group in created:
            await session.refresh(group)

    return groups


async def delete_group(session: AsyncSession, group_id: str) -> bool:
    group = await session.get(Group, group_id)
    if group is None:
        return False

    await session.delete(group)
    await session.commit()
    return True


async def delete_group_by_name(session: AsyncSession, name: str) -> bool:
    normalized = (name or "").strip()
    if not normalized:
        return False

    group = await get_group_by_name(session, normalized)
    if group is None:
        return False

    await session.delete(group)
    await session.commit()
    return True


async def fetch_groups_by_ids(session: AsyncSession, group_ids: Sequence[str]) -> List[Group]:
    if not group_ids:
        return []

    id_column = getattr(Group, "id")
    stmt = select(Group).where(id_column.in_(group_ids))
    result = await session.execute(stmt)
    return list(result.scalars().all())
