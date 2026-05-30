"""CRUD operations for ChannelPreset model."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.notifications.channel_preset_model import ChannelPreset


async def create_preset(
    session: AsyncSession,
    *,
    channel_type: str,
    label: str,
    config: Dict[str, Any],
    enabled: bool = True,
) -> ChannelPreset:
    """Create a new channel preset."""
    preset = ChannelPreset(
        channel_type=channel_type,
        label=label,
        config=config,
        enabled=enabled,
    )
    session.add(preset)
    await session.commit()
    await session.refresh(preset)
    return preset


async def get_preset(
    session: AsyncSession, preset_id: str
) -> Optional[ChannelPreset]:
    """Get a channel preset by ID."""
    stmt = select(ChannelPreset).where(ChannelPreset.id == preset_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_presets(
    session: AsyncSession,
    *,
    enabled_only: bool = False,
    channel_type: Optional[str] = None,
) -> List[ChannelPreset]:
    """Get all channel presets."""
    stmt = select(ChannelPreset)

    if enabled_only:
        stmt = stmt.where(ChannelPreset.enabled == True)

    if channel_type:
        stmt = stmt.where(ChannelPreset.channel_type == channel_type)

    stmt = stmt.order_by(ChannelPreset.label.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_preset(
    session: AsyncSession,
    preset: ChannelPreset,
    *,
    label: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    enabled: Optional[bool] = None,
) -> ChannelPreset:
    """Update a channel preset."""
    if label is not None:
        preset.label = label
    if config is not None:
        preset.config = config
    if enabled is not None:
        preset.enabled = enabled

    preset.updated_at = datetime.now(timezone.utc)

    session.add(preset)
    await session.commit()
    await session.refresh(preset)
    return preset


async def delete_preset(session: AsyncSession, preset: ChannelPreset) -> bool:
    """Delete a channel preset."""
    await session.delete(preset)
    await session.commit()
    return True
