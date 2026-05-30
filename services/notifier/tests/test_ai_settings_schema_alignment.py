from pathlib import Path

from sqlalchemy import Boolean, DateTime, Integer, String, Text

from app.models.ai_settings_model import AISettings


def test_ai_settings_model_matches_notifications_table_shape() -> None:
    table = AISettings.__table__
    columns = table.columns

    assert table.schema == "notifications"
    assert set(columns.keys()) == {
        "id",
        "organization_id",
        "ai_enabled",
        "ollama_url",
        "ollama_model",
        "ai_timeout",
        "ai_cache_ttl",
        "ai_default_preprompt",
        "updated_at",
    }
    assert columns["id"].primary_key
    assert isinstance(columns["id"].type, String)
    assert not columns["organization_id"].nullable
    assert columns["organization_id"].unique
    assert isinstance(columns["ai_enabled"].type, Boolean)
    assert isinstance(columns["ollama_url"].type, String)
    assert isinstance(columns["ollama_model"].type, String)
    assert isinstance(columns["ai_timeout"].type, Integer)
    assert isinstance(columns["ai_cache_ttl"].type, Integer)
    assert isinstance(columns["ai_default_preprompt"].type, Text)
    assert isinstance(columns["updated_at"].type, DateTime)
    assert columns["updated_at"].type.timezone
    assert not columns["updated_at"].nullable


def test_central_migration_creates_ai_settings_model_columns() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    migration = repo_root / "central/unicron/backend/alembic/versions/0015_add_notification_ai_settings.py"
    migration_text = migration.read_text()

    assert 'schema="notifications"' in migration_text
    assert '"ai_settings"' in migration_text
    for column in AISettings.__table__.columns:
        assert f'"{column.name}"' in migration_text
