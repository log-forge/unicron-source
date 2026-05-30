from contextlib import asynccontextmanager
from typing import AsyncGenerator

from app.core.config import settings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# -------------------------------------------------------------------------
# Build DATABASE_URL from settings
DATABASE_URL = (
    f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
)

# echo is False in production, True otherwise
engine = create_async_engine(
    DATABASE_URL,
    echo=(settings.ENVIRONMENT != "production"),
    pool_pre_ping=True,
    pool_size=settings.POSTGRES_POOL_SIZE,
    max_overflow=settings.POSTGRES_MAX_OVERFLOW,
    pool_timeout=settings.POSTGRES_POOL_TIMEOUT,
    pool_recycle=settings.POSTGRES_POOL_RECYCLE,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


# Convenience context manager for non-FastAPI contexts (e.g., Socket.IO handlers)
# Usage:
#   async with session_ctx() as session:
#       ...
@asynccontextmanager
async def session_ctx() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
