"""Unit tests for ConversationRepository.

Following TDD: Tests written FIRST, then implementation.
"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.repositories.conversation_repository import ConversationRepository
from app.services.transcript_parser import TranscriptLine


@pytest.mark.asyncio
class TestConversationRepository:
    """Test suite for ConversationRepository."""

    async def test_create_conversation(self, repository):
        """Test creating a new conversation."""
        conversation_id = await repository.create_conversation()

        assert conversation_id is not None
        assert isinstance(conversation_id, UUID)

    async def test_get_conversation_returns_created(self, repository):
        """Test retrieving a created conversation."""
        conversation_id = await repository.create_conversation()

        conversation = await repository.get_conversation(conversation_id)

        assert conversation is not None
        assert conversation.id == str(conversation_id)
        assert conversation.status == "active"
        assert conversation.started_at is not None

    async def test_get_conversation_nonexistent_returns_none(self, repository):
        """Test that getting non-existent conversation returns None."""
        fake_id = UUID("00000000-0000-0000-0000-000000000000")

        conversation = await repository.get_conversation(fake_id)

        assert conversation is None

    async def test_add_transcript_lines(self, repository):
        """Test adding transcript lines to conversation."""
        conversation_id = await repository.create_conversation()
        lines = [
            TranscriptLine(
                timestamp=datetime(2026, 2, 1, 11, 39, 0),
                speaker="agent",
                text="Hello",
                sequence_number=1,
            ),
            TranscriptLine(
                timestamp=datetime(2026, 2, 1, 11, 39, 1),
                speaker="customer",
                text="Hi",
                sequence_number=2,
            ),
        ]

        await repository.add_transcript_lines(conversation_id, lines)

        # Verify lines were added
        conversation = await repository.get_conversation(conversation_id)
        assert len(conversation.transcript_lines) == 2

    async def test_get_all_transcript_lines(self, repository):
        """Test retrieving all transcript lines for conversation."""
        conversation_id = await repository.create_conversation()
        lines = [
            TranscriptLine(
                timestamp=datetime(2026, 2, 1, 11, 39, i),
                speaker="agent" if i % 2 == 0 else "customer",
                text=f"Message {i}",
                sequence_number=i,
            )
            for i in range(1, 6)
        ]
        await repository.add_transcript_lines(conversation_id, lines)

        retrieved_lines = await repository.get_all_transcript_lines(conversation_id)

        assert len(retrieved_lines) == 5
        assert retrieved_lines[0].text == "Message 1"
        assert retrieved_lines[4].text == "Message 5"

    async def test_get_recent_transcript_lines(self, repository):
        """Test retrieving recent final transcript lines as ORM objects.

        get_recent_transcript_lines uses added_at (DB insertion time) and
        filters for is_final=True only. Returns ORM objects for SummaryGenerator.
        """
        conversation_id = await repository.create_conversation()

        # Add lines via add_transcript_lines (all added "now", all is_final=True)
        now = datetime.now(timezone.utc)
        lines = [
            TranscriptLine(
                timestamp=now - timedelta(seconds=50),
                speaker="agent",
                text="Message 1",
                sequence_number=1,
            ),
            TranscriptLine(
                timestamp=now - timedelta(seconds=20),
                speaker="customer",
                text="Message 2",
                sequence_number=2,
            ),
            TranscriptLine(
                timestamp=now - timedelta(seconds=10),
                speaker="agent",
                text="Message 3",
                sequence_number=3,
            ),
        ]
        await repository.add_transcript_lines(conversation_id, lines)

        # All lines were just inserted, so added_at is "now" for all.
        # Querying last 30 seconds should return all 3 (all final, all recently added).
        recent_lines = await repository.get_recent_transcript_lines(
            conversation_id, seconds=30
        )
        assert len(recent_lines) == 3

        # Verify returned objects are ORM models with attribute access
        assert hasattr(recent_lines[0], 'speaker')
        assert hasattr(recent_lines[0], 'text')
        assert recent_lines[0].speaker == "agent"
        assert recent_lines[0].text == "Message 1"

        # Querying with 0 seconds window should return none
        zero_lines = await repository.get_recent_transcript_lines(
            conversation_id, seconds=0
        )
        assert len(zero_lines) == 0

    async def test_get_recent_transcript_window(self, repository):
        """Test retrieving recent transcript lines as dicts within time window.

        get_recent_transcript_window uses timestamp (conversation time) to filter
        lines within the specified time window. Returns dicts for OpportunityDetector.
        """
        conversation_id = await repository.create_conversation()

        # Add lines with different conversation timestamps
        now = datetime.now(timezone.utc)
        lines = [
            TranscriptLine(
                timestamp=now - timedelta(seconds=50),
                speaker="agent",
                text="Message 1",
                sequence_number=1,
            ),
            TranscriptLine(
                timestamp=now - timedelta(seconds=20),
                speaker="customer",
                text="Message 2",
                sequence_number=2,
            ),
            TranscriptLine(
                timestamp=now - timedelta(seconds=10),
                speaker="agent",
                text="Message 3",
                sequence_number=3,
            ),
        ]
        await repository.add_transcript_lines(conversation_id, lines)

        # Querying last 30 seconds of conversation should return only last 2 lines
        # (Message 1 is 50 seconds old in conversation time, outside window)
        recent_lines = await repository.get_recent_transcript_window(
            conversation_id, seconds=30
        )
        assert len(recent_lines) == 2

        # Verify returned objects are dicts
        assert isinstance(recent_lines[0], dict)
        assert recent_lines[0]["speaker"] == "customer"
        assert recent_lines[0]["text"] == "Message 2"

        # Querying with 0 seconds window should return none
        zero_lines = await repository.get_recent_transcript_window(
            conversation_id, seconds=0
        )
        assert len(zero_lines) == 0

    async def test_get_all_final_transcript_lines(self, repository):
        """Test retrieving all final transcript lines as dicts (full conversation context).

        get_all_final_transcript_lines returns complete conversation history
        with only final lines (filters is_final=True). Used by utterance-based
        OpportunityDetector to send full context to LLM.
        """
        conversation_id = await repository.create_conversation()

        # Add mix of interim and final lines
        now = datetime.now(timezone.utc)

        # Simulate word-by-word streaming with interim/final pattern
        # Line 1: "Hello how are you" - with interim updates
        await repository.upsert_transcript_line(
            conversation_id=conversation_id,
            line=TranscriptLine(
                timestamp=now - timedelta(seconds=10),
                speaker="agent",
                text="Hello",
                sequence_number=1,
            ),
            line_id=f"{conversation_id}-seq-1",
            is_final=False  # interim
        )
        await repository.upsert_transcript_line(
            conversation_id=conversation_id,
            line=TranscriptLine(
                timestamp=now - timedelta(seconds=10),
                speaker="agent",
                text="Hello how",
                sequence_number=1,
            ),
            line_id=f"{conversation_id}-seq-1",
            is_final=False  # interim
        )
        await repository.upsert_transcript_line(
            conversation_id=conversation_id,
            line=TranscriptLine(
                timestamp=now - timedelta(seconds=10),
                speaker="agent",
                text="Hello how are you",
                sequence_number=1,
            ),
            line_id=f"{conversation_id}-seq-1",
            is_final=True  # final
        )

        # Line 2: Final only (no interim)
        await repository.upsert_transcript_line(
            conversation_id=conversation_id,
            line=TranscriptLine(
                timestamp=now - timedelta(seconds=5),
                speaker="customer",
                text="I need help with my order",
                sequence_number=2,
            ),
            line_id=f"{conversation_id}-seq-2",
            is_final=True
        )

        # Line 3: Another final line
        await repository.upsert_transcript_line(
            conversation_id=conversation_id,
            line=TranscriptLine(
                timestamp=now,
                speaker="agent",
                text="Sure I can help with that",
                sequence_number=3,
            ),
            line_id=f"{conversation_id}-seq-3",
            is_final=True
        )

        # Call the new method
        final_lines = await repository.get_all_final_transcript_lines(conversation_id)

        # Should return only 3 final lines (not interim updates)
        assert len(final_lines) == 3

        # Verify returned objects are dicts
        assert isinstance(final_lines[0], dict)
        assert isinstance(final_lines[1], dict)
        assert isinstance(final_lines[2], dict)

        # Verify correct schema
        assert "speaker" in final_lines[0]
        assert "text" in final_lines[0]
        assert "timestamp" in final_lines[0]
        assert "sequence_number" in final_lines[0]

        # Verify ordering by sequence_number
        assert final_lines[0]["sequence_number"] == 1
        assert final_lines[1]["sequence_number"] == 2
        assert final_lines[2]["sequence_number"] == 3

        # Verify content
        assert final_lines[0]["speaker"] == "agent"
        assert final_lines[0]["text"] == "Hello how are you"
        assert final_lines[1]["speaker"] == "customer"
        assert final_lines[1]["text"] == "I need help with my order"
        assert final_lines[2]["speaker"] == "agent"
        assert final_lines[2]["text"] == "Sure I can help with that"

        # Verify timestamp is ISO format string
        assert isinstance(final_lines[0]["timestamp"], str)
        # Should be parseable as ISO 8601
        datetime.fromisoformat(final_lines[0]["timestamp"])

    async def test_save_summary(self, repository):
        """Test saving a summary."""
        conversation_id = await repository.create_conversation()

        await repository.save_summary(
            conversation_id=conversation_id,
            version=1,
            summary_text="This is a test summary.",
            transcript_line_count=10,
        )

        conversation = await repository.get_conversation(conversation_id)
        assert len(conversation.summaries) == 1
        assert conversation.summaries[0].version == 1
        assert conversation.summaries[0].summary_text == "This is a test summary."

    async def test_get_latest_summary(self, repository):
        """Test retrieving the latest summary."""
        conversation_id = await repository.create_conversation()

        # Add multiple summaries
        await repository.save_summary(conversation_id, 1, "Summary v1", 5)
        await repository.save_summary(conversation_id, 2, "Summary v2", 10)
        await repository.save_summary(conversation_id, 3, "Summary v3", 15)

        latest = await repository.get_latest_summary(conversation_id)

        assert latest is not None
        assert latest.version == 3
        assert latest.summary_text == "Summary v3"

    async def test_get_latest_summary_none_returns_none(self, repository):
        """Test that getting latest summary with no summaries returns None."""
        conversation_id = await repository.create_conversation()

        latest = await repository.get_latest_summary(conversation_id)

        assert latest is None

    async def test_get_summary_count(self, repository):
        """Test getting count of summaries."""
        conversation_id = await repository.create_conversation()

        # Initially zero
        count = await repository.get_summary_count(conversation_id)
        assert count == 0

        # Add summaries
        await repository.save_summary(conversation_id, 1, "Summary 1", 5)
        await repository.save_summary(conversation_id, 2, "Summary 2", 10)

        count = await repository.get_summary_count(conversation_id)
        assert count == 2

    async def test_get_all_summaries(self, repository):
        """Test retrieving all summaries for conversation."""
        conversation_id = await repository.create_conversation()

        await repository.save_summary(conversation_id, 1, "Summary 1", 5)
        await repository.save_summary(conversation_id, 2, "Summary 2", 10)
        await repository.save_summary(conversation_id, 3, "Summary 3", 15)

        summaries = await repository.get_all_summaries(conversation_id)

        assert len(summaries) == 3
        assert summaries[0].version == 1
        assert summaries[2].version == 3

    # ===== ACW (After-Call Work) Tests =====

    async def test_mark_complete(self, repository):
        """Test marking conversation as completed."""
        conversation_id = await repository.create_conversation()

        # Mark as complete
        await repository.mark_complete(conversation_id)

        # Verify status and ended_at are set
        conversation = await repository.get_conversation(conversation_id)
        assert conversation.status == "completed"
        assert conversation.ended_at is not None
        # SQLite doesn't preserve timezone info, but PostgreSQL will
        # Just verify ended_at is recent (within last 10 seconds)
        assert (datetime.now(timezone.utc) - conversation.ended_at.replace(tzinfo=timezone.utc)).total_seconds() < 10

    async def test_save_disposition(self, repository):
        """Test saving disposition code."""
        conversation_id = await repository.create_conversation()

        await repository.save_disposition(conversation_id, "RESOLVED")

        conversation = await repository.get_conversation(conversation_id)
        assert conversation.disposition_code == "RESOLVED"

    async def test_save_wrap_up_notes(self, repository):
        """Test saving wrap-up notes."""
        conversation_id = await repository.create_conversation()

        notes = "Customer needed help with order #12345. Issue resolved."
        await repository.save_wrap_up_notes(conversation_id, notes)

        conversation = await repository.get_conversation(conversation_id)
        assert conversation.wrap_up_notes == notes

    async def test_save_agent_feedback(self, repository):
        """Test saving agent feedback rating."""
        conversation_id = await repository.create_conversation()

        await repository.save_agent_feedback(conversation_id, "up")

        conversation = await repository.get_conversation(conversation_id)
        assert conversation.agent_feedback == "up"

    async def test_save_agent_feedback_down(self, repository):
        """Test saving negative agent feedback."""
        conversation_id = await repository.create_conversation()

        await repository.save_agent_feedback(conversation_id, "down")

        conversation = await repository.get_conversation(conversation_id)
        assert conversation.agent_feedback == "down"

    async def test_save_compliance_results(self, repository):
        """Test bulk saving compliance checklist results."""
        conversation_id = await repository.create_conversation()

        items = [
            {
                "label": "Verified customer identity",
                "checked": True,
                "auto_detected": True,
            },
            {
                "label": "Confirmed order details",
                "checked": True,
                "auto_detected": False,
            },
            {
                "label": "Explained resolution",
                "checked": False,
                "auto_detected": False,
            },
        ]

        await repository.save_compliance_results(conversation_id, items)

        # Verify compliance results were saved
        conversation = await repository.get_conversation(conversation_id)
        assert len(conversation.compliance_results) == 3

        # Verify first item
        result = conversation.compliance_results[0]
        assert result.item_label == "Verified customer identity"
        assert result.is_checked is True
        assert result.auto_detected is True
        assert result.checked_at is not None

    async def test_save_crm_fields(self, repository):
        """Test bulk saving CRM field extractions."""
        conversation_id = await repository.create_conversation()

        fields = [
            {
                "field_name": "Case Subject",
                "extracted_value": "Order inquiry - tracking",
                "source": "AI",
                "confidence": 0.95,
            },
            {
                "field_name": "Case Type",
                "extracted_value": "Order Status",
                "source": "Transcript",
                "confidence": 1.0,
            },
            {
                "field_name": "Priority",
                "extracted_value": "Medium",
                "source": "AI",
                "confidence": 0.78,
            },
        ]

        await repository.save_crm_fields(conversation_id, fields)

        # Verify CRM fields were saved
        conversation = await repository.get_conversation(conversation_id)
        assert len(conversation.crm_field_extractions) == 3

        # Verify first field
        field = conversation.crm_field_extractions[0]
        assert field.field_name == "Case Subject"
        assert field.extracted_value == "Order inquiry - tracking"
        assert field.source == "AI"
        assert field.confidence == 0.95
        assert field.extracted_at is not None

    async def test_save_acw_data_all_at_once(self, repository):
        """Test saving all ACW data in one transaction."""
        conversation_id = await repository.create_conversation()

        # Save all ACW data
        await repository.save_disposition(conversation_id, "RESOLVED")
        await repository.save_wrap_up_notes(
            conversation_id,
            "Customer satisfied with resolution."
        )
        await repository.save_agent_feedback(conversation_id, "up")

        compliance_items = [
            {"label": "Identity verified", "checked": True, "auto_detected": True},
            {"label": "Issue resolved", "checked": True, "auto_detected": False},
        ]
        await repository.save_compliance_results(conversation_id, compliance_items)

        crm_fields = [
            {
                "field_name": "Resolution",
                "extracted_value": "Tracking provided",
                "source": "AI",
                "confidence": 0.92,
            }
        ]
        await repository.save_crm_fields(conversation_id, crm_fields)

        await repository.mark_complete(conversation_id)

        # Verify everything was saved
        conversation = await repository.get_conversation(conversation_id)
        assert conversation.status == "completed"
        assert conversation.disposition_code == "RESOLVED"
        assert conversation.wrap_up_notes == "Customer satisfied with resolution."
        assert conversation.agent_feedback == "up"
        assert conversation.ended_at is not None
        assert len(conversation.compliance_results) == 2
        assert len(conversation.crm_field_extractions) == 1


@pytest_asyncio.fixture
async def repository():
    """Create repository instance with in-memory test database."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.models.domain import Base

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
