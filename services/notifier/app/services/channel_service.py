"""Channel service layer for notification channel and preset CRUD operations."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import (
    SENSITIVE_FIELDS,
    decrypt_config,
    encrypt_config,
)
from app.models.channel_model import NotificationChannel
from app.models.channel_preset_model import ChannelPreset
from app.schemas import ChannelCreate, ChannelUpdate, PresetCreate, PresetUpdate


class ChannelNotFoundError(Exception):
    """Raised when a channel is not found."""

    pass


class PresetNotFoundError(Exception):
    """Raised when a preset is not found."""

    pass


class ChannelService:
    """Service for deployment-local notification channel operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_channel(
        self,
        data: ChannelCreate,
    ) -> NotificationChannel:
        """Create a new notification channel.

        Sensitive fields in data.config are encrypted before storage.
        """
        encrypted_config = encrypt_config(data.config)
        channel = NotificationChannel(
            id=uuid4().hex,
            label=data.name,
            channel_type=data.channel_type.value,
            config=encrypted_config,
            enabled=data.enabled,
            verified=False,
        )
        self.session.add(channel)
        await self.session.commit()
        await self.session.refresh(channel)
        return channel

    async def get_channel_by_id(
        self,
        channel_id: str,
    ) -> Optional[NotificationChannel]:
        """Get a channel by ID."""
        result = await self.session.execute(
            select(NotificationChannel).where(NotificationChannel.id == channel_id)
        )
        return result.scalar_one_or_none()

    async def get_channel_or_raise(
        self,
        channel_id: str,
    ) -> NotificationChannel:
        """Get a channel by ID or raise ChannelNotFoundError."""
        channel = await self.get_channel_by_id(channel_id)
        if not channel:
            raise ChannelNotFoundError(f"Channel {channel_id} not found")
        return channel

    async def list_channels(
        self,
        channel_type: Optional[str] = None,
        enabled_only: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[NotificationChannel], int]:
        """List channels with optional filtering and pagination."""
        # Build base query
        conditions = []

        if channel_type:
            conditions.append(NotificationChannel.channel_type == channel_type)

        if enabled_only:
            conditions.append(NotificationChannel.enabled == True)

        # Count total
        count_stmt = select(func.count(NotificationChannel.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar_one()

        # Fetch items with pagination
        stmt = select(NotificationChannel).order_by(NotificationChannel.created_at.desc())
        if conditions:
            stmt = stmt.where(and_(*conditions))
        result = await self.session.execute(stmt.offset(offset).limit(limit))
        items = list(result.scalars().all())

        return items, total

    async def update_channel(
        self,
        channel: NotificationChannel,
        data: ChannelUpdate,
    ) -> NotificationChannel:
        """Update a notification channel with provided fields.

        If config is included in the update, placeholder values ('********')
        are replaced with existing credentials before re-encrypting.
        """
        update_data = data.model_dump(exclude_unset=True)
        if "name" in update_data:
            update_data["label"] = update_data.pop("name")

        # Handle config separately for placeholder merge + re-encrypt
        if "config" in update_data and update_data["config"] is not None:
            update_data["config"] = self._merge_config_with_placeholder(
                channel.config, update_data["config"]
            )

        for field, value in update_data.items():
            setattr(channel, field, value)

        channel.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(channel)
        return channel

    @staticmethod
    def _merge_config_with_placeholder(
        existing_encrypted_config: Dict[str, Any],
        new_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge new config with existing encrypted config, handling placeholders.

        For sensitive fields: if the new value is the placeholder '********',
        preserve the existing encrypted value. Otherwise, use the new value.
        The final merged config is encrypted before return.

        Args:
            existing_encrypted_config: Current config from DB (encrypted).
            new_config: Incoming config from API request (may contain placeholders).

        Returns:
            Encrypted config dict ready for storage.
        """
        existing_decrypted = decrypt_config(existing_encrypted_config or {})
        merged = {}

        for key, value in new_config.items():
            if key in SENSITIVE_FIELDS and isinstance(value, str) and value == "********":
                # Preserve existing credential when the UI sends the mask value.
                merged[key] = existing_decrypted.get(key, "")
            else:
                merged[key] = value

        return encrypt_config(merged)

    async def delete_channel(self, channel: NotificationChannel) -> None:
        """Delete a notification channel."""
        await self.session.delete(channel)
        await self.session.commit()

    async def verify_channel(
        self,
        channel: NotificationChannel,
    ) -> NotificationChannel:
        """Mark a channel as verified (e.g., after email confirmation)."""
        channel.verified = True
        channel.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(channel)
        return channel

    async def toggle_channel(
        self,
        channel: NotificationChannel,
        enabled: bool,
    ) -> NotificationChannel:
        """Enable or disable a notification channel."""
        channel.enabled = enabled
        channel.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(channel)
        return channel


class PresetService:
    """Service for deployment-local channel preset operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_preset(
        self,
        data: PresetCreate,
    ) -> ChannelPreset:
        """Create a new channel preset.

        Sensitive fields in data.config are encrypted before storage.
        """
        encrypted_config = encrypt_config(data.config)
        preset = ChannelPreset(
            id=uuid4().hex,
            label=data.name,
            channel_type=data.channel_type.value,
            config=encrypted_config,
            enabled=data.enabled,
        )
        self.session.add(preset)
        await self.session.commit()
        await self.session.refresh(preset)
        return preset

    async def get_preset_by_id(
        self,
        preset_id: str,
    ) -> Optional[ChannelPreset]:
        """Get a preset by ID."""
        result = await self.session.execute(
            select(ChannelPreset).where(ChannelPreset.id == preset_id)
        )
        return result.scalar_one_or_none()

    async def get_preset_or_raise(
        self,
        preset_id: str,
    ) -> ChannelPreset:
        """Get a preset by ID or raise PresetNotFoundError."""
        preset = await self.get_preset_by_id(preset_id)
        if not preset:
            raise PresetNotFoundError(f"Preset {preset_id} not found")
        return preset

    async def list_presets(
        self,
        channel_type: Optional[str] = None,
        enabled_only: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[ChannelPreset], int]:
        """List presets with optional filtering and pagination."""
        # Build base query
        conditions = []

        if channel_type:
            conditions.append(ChannelPreset.channel_type == channel_type)

        if enabled_only:
            conditions.append(ChannelPreset.enabled == True)

        # Count total
        count_stmt = select(func.count(ChannelPreset.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar_one()

        # Fetch items with pagination
        stmt = select(ChannelPreset).order_by(ChannelPreset.created_at.desc())
        if conditions:
            stmt = stmt.where(and_(*conditions))
        result = await self.session.execute(stmt.offset(offset).limit(limit))
        items = list(result.scalars().all())

        return items, total

    async def update_preset(
        self,
        preset: ChannelPreset,
        data: PresetUpdate,
    ) -> ChannelPreset:
        """Update a channel preset with provided fields.

        If config is included in the update, placeholder values ('********')
        are replaced with existing credentials before re-encrypting.
        """
        update_data = data.model_dump(exclude_unset=True)
        if "name" in update_data:
            update_data["label"] = update_data.pop("name")

        # Handle config separately for placeholder merge + re-encrypt
        if "config" in update_data and update_data["config"] is not None:
            update_data["config"] = ChannelService._merge_config_with_placeholder(
                preset.config, update_data["config"]
            )

        for field, value in update_data.items():
            setattr(preset, field, value)

        preset.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(preset)
        return preset

    async def delete_preset(self, preset: ChannelPreset) -> None:
        """Delete a channel preset."""
        await self.session.delete(preset)
        await self.session.commit()

    async def toggle_preset(
        self,
        preset: ChannelPreset,
        enabled: bool,
    ) -> ChannelPreset:
        """Enable or disable a channel preset."""
        preset.enabled = enabled
        preset.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(preset)
        return preset


__all__ = [
    "ChannelService",
    "ChannelNotFoundError",
    "PresetService",
    "PresetNotFoundError",
]
