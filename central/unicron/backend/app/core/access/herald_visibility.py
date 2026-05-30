from app.models.herald.herald_model import Herald
from sqlmodel import select


async def list_visible_herald_ids(session, actor) -> list[str]:
    if not (getattr(actor, "org_role", None) in {"owner", "admin"} or getattr(actor, "user_id", None)):
        return []

    stmt = (
        select(getattr(Herald, "id"))
        .where(getattr(Herald, "unregistered") == False)  # noqa: E712
        .order_by(getattr(Herald, "registered_at").asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


__all__ = ["list_visible_herald_ids"]
