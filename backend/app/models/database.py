"""Database setup and session management for async SQLite.

Uses SQLAlchemy with aiosqlite for async database operations.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.domain import Base

import structlog

logger = structlog.get_logger(__name__)

# Global async engine
_engine = None
_async_session_maker = None


def get_engine():
    """Get or create async database engine.

    Returns:
        Async SQLAlchemy engine
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,  # Set to True for SQL query logging
            poolclass=NullPool,  # SQLite doesn't support connection pooling
        )
        logger.info("database_engine_created", url=settings.DATABASE_URL)
    return _engine


def get_session_maker():
    """Get or create async session maker.

    Returns:
        Async session maker factory
    """
    global _async_session_maker
    if _async_session_maker is None:
        engine = get_engine()
        _async_session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        logger.info("session_maker_created")
    return _async_session_maker


async def init_db() -> None:
    """Initialize database by creating all tables.

    Should be called during application startup.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database_tables_created")


async def close_db() -> None:
    """Close database engine and clean up resources.

    Should be called during application shutdown.
    """
    global _engine
    if _engine is not None:
        await _engine.dispose()
        logger.info("database_engine_disposed")
        _engine = None


async def get_session() -> AsyncSession:
    """Get async database session.

    Yields:
        Async database session

    Example:
        async with get_session() as session:
            result = await session.execute(query)
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
