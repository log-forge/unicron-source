from datetime import datetime, timezone

import pytest

from app.models.notification_log_model import NotificationLog
from app.services import log_service


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
async def test_notification_log_model_matches_notifications_table_shape() -> None:
    column_names = set(NotificationLog.__table__.columns.keys())

    assert "channel_type" in column_names
    assert "organization_id" not in column_names
    assert "last_attempt_at" in column_names


@pytest.mark.asyncio
async def test_create_log_populates_required_columns() -> None:
    session = AsyncSessionStub()

    log = await log_service.create_log(
        session,
        alert_id="alert-1",
        channel_id="channel-1",
        channel_type="discord",
        status="pending",
    )

    assert session.added == [log]
    assert log.channel_type == "discord"


@pytest.mark.asyncio
async def test_update_log_status_sets_last_attempt_timestamp() -> None:
    session = AsyncSessionStub()
    log = NotificationLog(
        id="log-1",
        alert_id="alert-1",
        channel_id="channel-1",
        channel_type="discord",
        status="pending",
        attempt_count=0,
        created_at=datetime.now(timezone.utc),
    )

    updated = await log_service.update_log_status(session, log, "sent")

    assert updated.attempt_count == 1
    assert updated.last_attempt_at is not None
    assert updated.sent_at == updated.last_attempt_at
