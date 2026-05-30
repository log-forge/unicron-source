"""PyInstaller entrypoint for appliance backend migration/bootstrap."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from scripts.migrate_or_bootstrap import _prepare_schema


def _import_alembic_models() -> None:
    """Force PyInstaller to bundle models imported dynamically by Alembic."""
    from app.models.alerting import AlertHistory, AlertRule, AlertState, Silence
    from app.models.container import Container
    from app.models.group import Group
    from app.models.herald.herald_model import Herald
    from app.models.herald.herald_token_model import Herald_Token
    from app.models.notifications import (
        AISettings,
        ChannelPreset,
        NotificationChannel,
        NotificationGroup,
        NotificationLog,
        NotificationPreference,
    )
    from app.models.settings import OriginPolicyConfig

    _ = (
        AISettings,
        AlertHistory,
        AlertRule,
        AlertState,
        ChannelPreset,
        Container,
        Group,
        Herald,
        Herald_Token,
        NotificationChannel,
        NotificationGroup,
        NotificationLog,
        NotificationPreference,
        OriginPolicyConfig,
        Silence,
    )


def _bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _alembic_config() -> Config:
    root = _bundle_root()
    script_location = Path(
        os.environ.get("ALEMBIC_SCRIPT_LOCATION", root / "backend" / "alembic")
    )
    config = Config()
    config.set_main_option("script_location", str(script_location))
    config.set_main_option("sqlalchemy.url", "driver://user:pass@localhost/dbname")
    return config


def main() -> int:
    try:
        asyncio.run(_prepare_schema())
        _import_alembic_models()
        config = _alembic_config()
        print("Running alembic upgrade head...")
        command.upgrade(config, "head")
        return 0
    except Exception as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
