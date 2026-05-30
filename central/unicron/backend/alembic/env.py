import asyncio
import os
import sys
from logging.config import fileConfig
from urllib.parse import quote_plus

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Ensure app is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app")))


from app.models.container import Container
from app.models.group import Group

# Import your models so Alembic sees them
from app.models.herald.herald_model import Herald
from app.models.herald.herald_token_model import Herald_Token

# Settings models
from app.models.settings import OriginPolicyConfig

# Alerting models
from app.models.alerting import AlertRule, AlertHistory, AlertState, Silence

# Notifications models
from app.models.notifications import (
    NotificationChannel,
    ChannelPreset,
    NotificationGroup,
    NotificationPreference,
    NotificationLog,
    AISettings,
)
from sqlmodel import SQLModel

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

def _database_url_from_env() -> str | None:
    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return explicit

    user = os.getenv("POSTGRES_USER", "").strip()
    password = os.getenv("POSTGRES_PASSWORD", "").strip()
    db = os.getenv("POSTGRES_DB", "").strip()
    host = os.getenv("POSTGRES_HOST", "").strip()
    port = os.getenv("POSTGRES_PORT", "").strip() or "5432"
    if not (user and password and db and host):
        return None

    user_q = quote_plus(user)
    password_q = quote_plus(password)
    db_q = quote_plus(db)
    return f"postgresql+asyncpg://{user_q}:{password_q}@{host}:{port}/{db_q}"


database_url = _database_url_from_env()
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = SQLModel.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    section = config.get_section(config.config_ini_section, {})
    url = section.get("sqlalchemy.url", "")
    if "+asyncpg" in url:
        def _do_run_migrations(sync_conn) -> None:
            context.configure(connection=sync_conn, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()

        async def _run_async() -> None:
            connectable = async_engine_from_config(
                section,
                prefix="sqlalchemy.",
                poolclass=pool.NullPool,
            )
            async with connectable.connect() as connection:
                await connection.run_sync(_do_run_migrations)
            await connectable.dispose()

        asyncio.run(_run_async())
        return

    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
