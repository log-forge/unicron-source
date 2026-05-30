from typing import Optional

from app.models.herald.herald_token_model import Herald_Token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def create_herald_token(
    session: AsyncSession,
    organization_id: str,
    herald_name: str,
    central_url: str,
    herald_id: Optional[str] = None,
    check_in_interval: Optional[int] = None,
    tags: Optional[list] = None,
) -> Herald_Token:
    herald_token = Herald_Token(
        organization_id=organization_id,
        herald_name=herald_name,
        central_url=central_url,
        check_in_interval=check_in_interval or 60,
        tags=tags or [],
    )
    if herald_id is not None:
        herald_token.id = herald_id

    session.add(herald_token)

    await session.commit()
    await session.refresh(herald_token)
    return herald_token


async def get_herald_token(session: AsyncSession, herald_token_id: str) -> Optional[Herald_Token]:
    return await session.get(Herald_Token, herald_token_id)


async def get_latest_herald_token_by_name(session: AsyncSession, herald_name: str) -> Optional[Herald_Token]:
    stmt = (
        select(Herald_Token)
        .where(getattr(Herald_Token, "herald_name") == herald_name)
        .order_by(getattr(Herald_Token, "created_at").desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_latest_bootstrapped_go_streamer_token_by_name(
    session: AsyncSession,
    herald_name: str,
) -> Optional[Herald_Token]:
    stmt = (
        select(Herald_Token)
        .where(
            getattr(Herald_Token, "herald_name") == herald_name,
            getattr(Herald_Token, "status").in_(("consumed", "active")),
            getattr(Herald_Token, "tags").contains(["go-streamer"]),
        )
        .order_by(getattr(Herald_Token, "created_at").desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_latest_pending_go_streamer_token_by_name(
    session: AsyncSession,
    herald_name: str,
) -> Optional[Herald_Token]:
    stmt = (
        select(Herald_Token)
        .where(
            getattr(Herald_Token, "herald_name") == herald_name,
            getattr(Herald_Token, "status") == "pending",
            getattr(Herald_Token, "tags").contains(["go-streamer"]),
        )
        .order_by(getattr(Herald_Token, "created_at").desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_herald_token_status(
    session: AsyncSession, herald_token_id: str, status: str, reason: Optional[str] = None
) -> Optional[Herald_Token]:
    herald_token = await session.get(Herald_Token, herald_token_id)
    if herald_token:
        herald_token.status = status
        if reason is not None:
            herald_token.reason = reason
        await session.commit()
        await session.refresh(herald_token)
    return herald_token


async def clear_herald_token_failure(session: AsyncSession, herald_token_id: str) -> Optional[Herald_Token]:
    herald_token = await session.get(Herald_Token, herald_token_id)
    if herald_token:
        herald_token.failure_details = None
        herald_token.reason = None
        await session.commit()
        await session.refresh(herald_token)
    return herald_token


async def delete_herald_token(session: AsyncSession, herald_token_id: str) -> None:
    herald_token = await session.get(Herald_Token, herald_token_id)
    if herald_token:
        await session.delete(herald_token)
        await session.commit()
