"""
Unit tests for conversation repository summary interval persistence.

Tests verify that summary intervals are:
1. Persisted to the database
2. Retrieved correctly
3. Updated atomically
4. Handle edge cases (missing conversations)
"""

import pytest
import pytest_asyncio
from uuid import uuid4
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.domain import Base, Conversation
from app.repositories.conversation_repository import ConversationRepository
from app.config import settings


@pytest_asyncio.fixture
async def repository():
    """Create repository instance with in-memory test database."""
    # Create in-memory SQLite database with StaticPool to keep connection alive
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,  # Keep single connection alive
        connect_args={"check_same_thread": False},
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session maker
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Create repository
    repo = ConversationRepository(async_session_maker)

    yield repo

    # Cleanup
    await engine.dispose()


@pytest.mark.asyncio
class TestConversationRepositoryInterval:
    """Test suite for summary interval persistence."""

    async def test_create_conversation_has_default_interval(self, repository):
        """Verify new conversations get config default interval (5 seconds)."""
        # Create conversation without specifying interval
        conversation_id = await repository.create_conversation()

        # Get conversation to verify interval
        conversation = await repository.get_conversation(conversation_id)

        # Should use config default (5 seconds)
        assert conversation.summary_interval == settings.SUMMARY_INTERVAL_SECONDS
        assert conversation.summary_interval == 5

    async def test_create_conversation_with_custom_interval(self, repository):
        """Verify can override default interval at creation time."""
        custom_interval = 15

        # Create conversation with custom interval
        conversation_id = await repository.create_conversation(summary_interval=custom_interval)

        # Get conversation to verify interval
        conversation = await repository.get_conversation(conversation_id)

        # Should use provided value
        assert conversation.summary_interval == custom_interval

    async def test_update_summary_interval(self, repository):
        """Verify update persists to database."""
        # Create conversation with default interval
        conversation_id = await repository.create_conversation()

        conversation = await repository.get_conversation(conversation_id)
        assert conversation.summary_interval == 5

        # Update interval
        new_interval = 20
        await repository.update_summary_interval(conversation_id, new_interval)

        # Verify update persisted
        updated_interval = await repository.get_summary_interval(conversation_id)
        assert updated_interval == new_interval

    async def test_update_summary_interval_nonexistent_conversation(self, repository):
        """Verify graceful handling of missing conversation."""
        nonexistent_id = uuid4()

        # Should not raise exception
        await repository.update_summary_interval(nonexistent_id, 15)

        # Get should return None
        result = await repository.get_summary_interval(nonexistent_id)
        assert result is None

    async def test_get_summary_interval_returns_persisted_value(self, repository):
        """Verify reading from database works."""
        custom_interval = 25

        # Create conversation with custom interval
        conversation_id = await repository.create_conversation(summary_interval=custom_interval)

        # Retrieve interval
        retrieved_interval = await repository.get_summary_interval(conversation_id)
        assert retrieved_interval == custom_interval

    async def test_get_summary_interval_nonexistent_returns_none(self, repository):
        """Verify returns None for missing conversation."""
        nonexistent_id = uuid4()

        result = await repository.get_summary_interval(nonexistent_id)
        assert result is None

    async def test_interval_persists_across_sessions(self, repository):
        """Verify interval survives database session changes."""
        custom_interval = 12

        # Create conversation
        conversation_id = await repository.create_conversation(summary_interval=custom_interval)

        # Retrieve interval (simulates separate request)
        retrieved_interval = await repository.get_summary_interval(conversation_id)

        # Should still have same interval
        assert retrieved_interval == custom_interval
