"""Unit tests for new repository retrieval methods.

Following TDD: Tests written FIRST, then implementation.

Tests get_compliance_attempts, get_content_edits, get_disposition_suggestions,
get_listening_mode_sessions, get_crm_field_extractions.
"""
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.domain import (
    Base,
    ComplianceDetectionAttempt,
    ContentEdit,
    DispositionSuggestion,
    ListeningModeSession,
    CRMFieldExtraction,
)
from app.repositories.conversation_repository import ConversationRepository


@pytest_asyncio.fixture
async def repository():
    """Create repository instance with in-memory test database."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    repo = ConversationRepository(session_maker)
    yield repo
    await engine.dispose()


@pytest.mark.asyncio
class TestRepositoryRetrievalMethods:
    """Tests for new retrieval methods added for dashboard data export."""

    async def test_get_compliance_attempts(self, repository):
        """Test retrieving compliance detection attempts for a conversation."""
        conv_id = await repository.create_conversation()

        # Save attempts via existing method
        await repository.save_compliance_attempts(conv_id, [
            {
                "item_label": "Greeting",
                "ai_detected": True,
                "ai_confidence": 0.95,
                "agent_override": False,
                "final_status": True,
            },
            {
                "item_label": "Account Verification",
                "ai_detected": False,
                "ai_confidence": 0.3,
                "agent_override": True,
                "final_status": True,
            },
        ])

        results = await repository.get_compliance_attempts(conv_id)

        assert len(results) == 2
        assert results[0].item_label == "Greeting"
        assert results[0].ai_detected is True
        assert results[0].ai_confidence == 0.95
        assert results[1].agent_override is True

    async def test_get_compliance_attempts_empty(self, repository):
        """Test retrieving compliance attempts when none exist."""
        conv_id = await repository.create_conversation()
        results = await repository.get_compliance_attempts(conv_id)
        assert results == []

    async def test_get_content_edits(self, repository):
        """Test retrieving content edits for a conversation."""
        conv_id = await repository.create_conversation()

        # Insert content edits directly (no save method exists)
        async with repository.session_maker() as session:
            session.add(ContentEdit(
                conversation_id=str(conv_id),
                field_name="wrap_up_notes",
                original_value="AI generated notes",
                edited_value="Agent corrected notes",
                edit_type="modification",
                agent_id="agent-1",
            ))
            session.add(ContentEdit(
                conversation_id=str(conv_id),
                field_name="crm_field_case_subject",
                original_value="Order issue",
                edited_value="Billing dispute",
                edit_type="complete_rewrite",
                agent_id="agent-1",
            ))
            await session.commit()

        results = await repository.get_content_edits(conv_id)

        assert len(results) == 2
        assert results[0].field_name == "wrap_up_notes"
        assert results[0].edit_type == "modification"
        assert results[1].edit_type == "complete_rewrite"

    async def test_get_content_edits_empty(self, repository):
        """Test retrieving content edits when none exist."""
        conv_id = await repository.create_conversation()
        results = await repository.get_content_edits(conv_id)
        assert results == []

    async def test_get_disposition_suggestions(self, repository):
        """Test retrieving disposition suggestions for a conversation."""
        conv_id = await repository.create_conversation()

        await repository.save_disposition_suggestions(conv_id, [
            {
                "code": "RESOLVED",
                "label": "Issue Resolved",
                "confidence": 0.92,
                "reasoning": "Customer confirmed resolution",
                "rank": 1,
            },
            {
                "code": "FOLLOWUP_REQUIRED",
                "label": "Follow-up Required",
                "confidence": 0.65,
                "reasoning": "Some items unresolved",
                "rank": 2,
            },
        ])

        results = await repository.get_disposition_suggestions(conv_id)

        assert len(results) == 2
        # Sorted by rank
        assert results[0].rank == 1
        assert results[0].suggested_code == "RESOLVED"
        assert results[0].confidence == 0.92
        assert results[1].rank == 2
        assert results[1].suggested_code == "FOLLOWUP_REQUIRED"

    async def test_get_disposition_suggestions_empty(self, repository):
        """Test retrieving disposition suggestions when none exist."""
        conv_id = await repository.create_conversation()
        results = await repository.get_disposition_suggestions(conv_id)
        assert results == []

    async def test_get_listening_mode_sessions(self, repository):
        """Test retrieving all listening mode sessions for a conversation."""
        conv_id = await repository.create_conversation()

        # Create sessions via existing method
        session_id = await repository.create_listening_mode_session(conv_id)
        await repository.end_listening_mode_session(session_id)

        results = await repository.get_listening_mode_sessions(conv_id)

        assert len(results) == 1
        assert results[0].conversation_id == str(conv_id)
        assert results[0].ended_at is not None

    async def test_get_listening_mode_sessions_empty(self, repository):
        """Test retrieving listening mode sessions when none exist."""
        conv_id = await repository.create_conversation()
        results = await repository.get_listening_mode_sessions(conv_id)
        assert results == []

    async def test_get_crm_field_extractions(self, repository):
        """Test retrieving CRM field extractions for a conversation."""
        conv_id = await repository.create_conversation()

        await repository.save_crm_fields(conv_id, [
            {
                "field_name": "case_subject",
                "extracted_value": "Order inquiry",
                "source": "AI",
                "confidence": 0.88,
            },
            {
                "field_name": "customer_email",
                "extracted_value": "test@example.com",
                "source": "Transcript",
                "confidence": 0.95,
            },
        ])

        results = await repository.get_crm_field_extractions(conv_id)

        assert len(results) == 2
        assert results[0].field_name == "case_subject"
        assert results[0].source == "AI"
        assert results[1].source == "Transcript"

    async def test_get_crm_field_extractions_empty(self, repository):
        """Test retrieving CRM field extractions when none exist."""
        conv_id = await repository.create_conversation()
        results = await repository.get_crm_field_extractions(conv_id)
        assert results == []
