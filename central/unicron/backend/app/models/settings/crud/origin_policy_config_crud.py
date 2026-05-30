from datetime import datetime, timezone
from typing import Optional

from app.models.settings.origin_policy_config_model import OriginPolicyConfig
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_origin_policy_config(session: AsyncSession) -> Optional[OriginPolicyConfig]:
    result = await session.execute(select(OriginPolicyConfig).limit(1))
    return result.scalars().first()


async def ensure_origin_policy_config(session: AsyncSession) -> OriginPolicyConfig:
    existing = await get_origin_policy_config(session)
    if existing:
        return existing

    now = datetime.now(timezone.utc)
    cfg = OriginPolicyConfig(created_at=now, updated_at=now)
    session.add(cfg)
    await session.commit()
    await session.refresh(cfg)
    return cfg


async def update_origin_policy_config(
    session: AsyncSession,
    cfg: OriginPolicyConfig,
    *,
    allowed_origins: list[str],
) -> OriginPolicyConfig:
    cfg.allowed_origins = allowed_origins
    cfg.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(cfg)
    return cfg


__all__ = ["ensure_origin_policy_config", "get_origin_policy_config", "update_origin_policy_config"]
