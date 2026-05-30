import pytest

import app.models as models
from app.models.notification_group_model import NotificationGroup
from app.models.notification_log_model import NotificationLog
from app.models.notification_preference_model import NotificationPreference
from app.schemas import GroupTargets, NotificationGroupCreate, NotificationPreferenceUpdate
from app.services import group_service, preference_service


class ScalarResultStub:
    def __init__(self, value=None) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class AsyncSessionStub:
    def __init__(self, scalar_value=None) -> None:
        self.added = []
        self.scalar_value = scalar_value

    def add(self, obj) -> None:
        self.added.append(obj)

    async def execute(self, stmt):
        return ScalarResultStub(self.scalar_value)

    async def commit(self) -> None:
        return None

    async def refresh(self, obj) -> None:
        return None


def test_removed_group_member_and_user_preference_exports() -> None:
    assert not hasattr(models, "NotificationGroupMember")
    assert not hasattr(models, "UserPreference")
    assert hasattr(models, "NotificationPreference")


def test_group_model_is_delivery_bundle_shape() -> None:
    column_names = set(NotificationGroup.__table__.columns.keys())
    assert {"id", "name", "enabled", "target_config", "created_at", "updated_at"} <= column_names
    assert "owner_id" not in column_names
    assert "organization_id" not in column_names


def test_notification_log_has_no_ownership_columns() -> None:
    column_names = set(NotificationLog.__table__.columns.keys())
    assert "user_id" not in column_names
    assert "organization_id" not in column_names


@pytest.mark.asyncio
async def test_create_group_stores_direct_targets() -> None:
    session = AsyncSessionStub()
    group = await group_service.create_group(
        session,
        NotificationGroupCreate(
            name="Ops Bundle",
            enabled=True,
            target_config=GroupTargets(
                channel_ids=["channel-1"],
                preset_ids=["preset-1"],
            ),
        ),
    )

    assert session.added == [group]
    assert group.target_config == {
        "channel_ids": ["channel-1"],
        "preset_ids": ["preset-1"],
    }


@pytest.mark.asyncio
async def test_global_preference_create_and_update() -> None:
    session = AsyncSessionStub()
    preference = await preference_service.get_or_create_preference(session)

    assert session.added == [preference]
    assert preference.id == "global"
    assert preference.min_severity == "info"

    updated = await preference_service.update_preference(
        session,
        preference,
        NotificationPreferenceUpdate(min_severity="critical"),
    )
    assert updated.min_severity == "critical"


def test_notification_preference_model_is_singleton_shape() -> None:
    column_names = set(NotificationPreference.__table__.columns.keys())
    assert "id" in column_names
    assert "user_id" not in column_names
    assert "organization_id" not in column_names
