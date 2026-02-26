"""Database setup and session management for async SQLite.

Uses SQLAlchemy with aiosqlite for async database operations.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.domain import Base

import structlog

logger = structlog.get_logger(__name__)


def create_engine():
    """Create async database engine.

    Should be called once during application startup.

    Returns:
        Async SQLAlchemy engine
    """
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,  # Set to True for SQL query logging
        poolclass=NullPool,  # SQLite doesn't support connection pooling
    )
    logger.info("database_engine_created", url=settings.DATABASE_URL)
    return engine


def create_session_maker(engine):
    """Create async session maker.

    Should be called once during application startup.

    Args:
        engine: Async SQLAlchemy engine

    Returns:
        Async session maker factory
    """
    session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    logger.info("session_maker_created")
    return session_maker


async def init_db(engine) -> None:
    """Initialize database by creating all tables.

    Should be called during application startup.

    Args:
        engine: Async SQLAlchemy engine
    """
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database_tables_created")


async def close_db(engine) -> None:
    """Close database engine and clean up resources.

    Should be called during application shutdown.

    Args:
        engine: Async SQLAlchemy engine
    """
    if engine is not None:
        await engine.dispose()
        logger.info("database_engine_disposed")



