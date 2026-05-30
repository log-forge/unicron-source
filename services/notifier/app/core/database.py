"""PostgreSQL async database connection for notifier service.

Note: This connects to the SAME PostgreSQL database as Central.
The notifications schema was created in Phase 1 migrations - we do NOT
create tables here, they already exist from Central's Alembic migrations.

Connection Resilience:
- Retries with exponential backoff on startup
- pool_pre_ping for connection health checks
- 2-minute timeout before giving up
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.logging import get_logger
from app.core.retry import retry_connection

logger = get_logger("notifier.core.database")

# Build DATABASE_URL from settings
DATABASE_URL = (
    f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
)

# Engine instance (created lazily with retry)
_engine = None
_session_maker = None


def _create_engine():
    """Create async engine with production-ready settings."""
    return create_async_engine(
        DATABASE_URL,
        echo=(settings.ENVIRONMENT != "production"),
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
    )


async def _verify_connection(eng) -> bool:
    """Test that database connection works."""
    async with eng.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True


async def init_database() -> None:
    """
    Initialize database connection with retry logic.

    Called during application startup. Retries with exponential
    backoff if PostgreSQL isn't immediately available.

    Raises:
        ConnectionError: If connection cannot be established after 2 minutes.
    """
    global _engine, _session_maker

    async def connect():
        eng = _create_engine()
        await _verify_connection(eng)
        return eng

    _engine = await retry_connection(connect, "PostgreSQL")
    _session_maker = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    logger.info("Database connection pool initialized")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI routes - yields database session."""
    if _session_maker is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    async with _session_maker() as session:
        yield session


@asynccontextmanager
async def session_ctx() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for non-FastAPI contexts (e.g., Celery tasks)."""
    if _session_maker is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    async with _session_maker() as session:
        yield session


async def close_database() -> None:
    """Close database connection pool gracefully."""
    global _engine, _session_maker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_maker = None
        logger.info("Database connection pool closed")


def get_engine():
    """Get the database engine (must call init_database first for retry-enabled engine)."""
    if _engine is not None:
        return _engine
    # Fallback to backward-compatible engine
    return engine


# For backward compatibility - expose engine directly
# (will be replaced by proper init in main.py lifespan)
engine = create_async_engine(
    DATABASE_URL,
    echo=(settings.ENVIRONMENT != "production"),
    pool_pre_ping=True,
)
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

__all__ = ["engine", "async_session_maker", "get_db", "session_ctx", "init_database", "close_database", "get_engine"]
