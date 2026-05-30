from datetime import datetime, timezone

import pytest

from app.models.channel_model import NotificationChannel
from app.models.channel_preset_model import ChannelPreset
from app.schemas import ChannelCreate, ChannelType, ChannelUpdate, PresetCreate, PresetUpdate
from app.services.channel_service import ChannelService, PresetService


class AsyncSessionStub:
    def __init__(self) -> None:
        self.added = []

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        return None

    async def refresh(self, obj) -> None:
        return None


@pytest.mark.asyncio
async def test_notification_channel_model_matches_notifications_table_shape() -> None:
    column_names = set(NotificationChannel.__table__.columns.keys())

    assert "label" in column_names
    assert "name" not in column_names
    assert "from_preset_id" not in column_names
    assert "user_id" not in column_names
    assert "organization_id" not in column_names


@pytest.mark.asyncio
async def test_create_channel_persists_label_while_accepting_api_name() -> None:
    session = AsyncSessionStub()
    service = ChannelService(session)

    channel = await service.create_channel(
        data=ChannelCreate(
            name="Discord Webhook",
            channel_type=ChannelType.DISCORD,
            enabled=True,
            config={"webhook_url": "https://discord.com/api/webhooks/1/token"},
        ),
    )

    assert session.added == [channel]
    assert channel.label == "Discord Webhook"


@pytest.mark.asyncio
async def test_update_channel_maps_api_name_to_label() -> None:
    session = AsyncSessionStub()
    service = ChannelService(session)
    channel = NotificationChannel(
        id="channel-1",
        channel_type=ChannelType.DISCORD.value,
        label="Old Name",
        config={"webhook_url": "https://discord.com/api/webhooks/1/token"},
        enabled=True,
        verified=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    updated = await service.update_channel(channel, ChannelUpdate(name="New Name"))

    assert updated.label == "New Name"


@pytest.mark.asyncio
async def test_preset_model_uses_label_and_service_maps_api_name() -> None:
    column_names = set(ChannelPreset.__table__.columns.keys())
    assert "label" in column_names
    assert "name" not in column_names
    assert "owner_id" not in column_names
    assert "organization_id" not in column_names

    session = AsyncSessionStub()
    service = PresetService(session)

    preset = await service.create_preset(
        data=PresetCreate(
            name="Ops Discord",
            channel_type=ChannelType.DISCORD,
            enabled=True,
            config={"webhook_url": "https://discord.com/api/webhooks/1/token"},
        ),
    )

    assert session.added == [preset]
    assert preset.label == "Ops Discord"

    updated = await service.update_preset(preset, PresetUpdate(name="Ops Discord 2"))
    assert updated.label == "Ops Discord 2"
