"""Integration test for SummaryGenerator with ConversationRepository.

This test validates that get_recent_transcript_lines returns objects
that summary_generator can consume via attribute access.
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID
from datetime import datetime, timezone, timedelta

from app.services.summary_generator import SummaryGenerator
from app.repositories.conversation_repository import ConversationRepository
from app.services.transcript_parser import TranscriptLine


@pytest.mark.asyncio
async def test_summary_generator_uses_orm_objects_from_repository(tmp_path):
    """Test that summary generator can access line.speaker and line.text.

    This test validates the contract between SummaryGenerator and ConversationRepository.
    SummaryGenerator expects ORM objects with attribute access (line.speaker, line.text).

    This test will FAIL if get_recent_transcript_lines returns dicts instead of ORM objects.
    """
    # Create in-memory test database
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.models.domain import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    repository = ConversationRepository(session_maker)

    # Create conversation and add transcript lines
    conversation_id = await repository.create_conversation()
    now = datetime.now(timezone.utc)
    lines = [
        TranscriptLine(
            timestamp=now - timedelta(seconds=20),
            speaker="agent",
            text="Hello, how can I help?",
            sequence_number=1,
        ),
        TranscriptLine(
            timestamp=now - timedelta(seconds=10),
            speaker="customer",
            text="I need a ladder.",
            sequence_number=2,
        ),
    ]
    await repository.add_transcript_lines(conversation_id, lines)

    # Get recent lines from repository
    recent_lines = await repository.get_recent_transcript_lines(
        conversation_id, seconds=30
    )

    # THIS IS THE CRITICAL TEST: Can we access speaker and text as attributes?
    # If get_recent_transcript_lines returns dicts, this will raise AttributeError
    try:
        transcript_text = "\n".join(
            [f"{line.speaker.upper()}: {line.text}" for line in recent_lines]
        )
        # If we get here, the test passes
        assert "AGENT: Hello, how can I help?" in transcript_text
        assert "CUSTOMER: I need a ladder." in transcript_text
    except AttributeError as e:
        pytest.fail(
            f"get_recent_transcript_lines returned dicts instead of ORM objects. "
            f"SummaryGenerator requires attribute access (line.speaker, line.text). "
            f"Error: {e}"
        )
