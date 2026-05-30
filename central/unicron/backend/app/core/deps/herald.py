from app.core.database import get_session
from app.core.deps.spiffe import require_spiffe_id
from app.core.logging import get_logger
from app.models.herald.crud.herald_crud import get_herald
from app.models.herald.herald_model import Herald
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("backend.deps.herald")


async def require_registered_herald(
    herald_id: str = Depends(require_spiffe_id),
    session: AsyncSession = Depends(get_session),
) -> Herald:
    """Ensure the caller herald exists and is not unregistered."""
    herald = await get_herald(session, herald_id)
    if not herald or getattr(herald, "unregistered", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Herald not registered")

    return herald


__all__ = ["require_registered_herald"]
