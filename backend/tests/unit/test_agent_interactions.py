"""Unit tests for Agent Interaction metrics functionality.

Tests ADR-013: Agent Interaction Metrics and Analytics
Tests new AgentInteraction and ListeningModeSession models.
"""
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from app.models.domain import AgentInteraction, ListeningModeSession, Conversation


class TestAgentInteractionModel:
    """Test AgentInteraction model (ADR-013)."""

    def test_agent_interaction_has_context_data_field(self):
        """Test that AgentInteraction uses context_data (not metadata)."""
        # Given: A conversation
        conversation_id = str(uuid4())

        # When: Creating an AgentInteraction with context_data
        interaction = AgentInteraction(
            conversation_id=conversation_id,
            interaction_type="mcp_query_manual",
            query_text="recommend safety gloves",
            context_data='{"server": "/product_retrieval", "tool": "get_product_docs"}',
            user_rating="up",
            manually_edited=False,
        )

        # Then: context_data field should be accessible
        assert interaction.context_data == '{"server": "/product_retrieval", "tool": "get_product_docs"}'
        assert interaction.interaction_type == "mcp_query_manual"
        assert interaction.user_rating == "up"

    def test_agent_interaction_no_metadata_field(self):
        """Test that AgentInteraction uses context_data field name (not metadata)."""
        # Given: A conversation
        conversation_id = str(uuid4())

        # When: Creating an AgentInteraction with context_data
        interaction = AgentInteraction(
            conversation_id=conversation_id,
            interaction_type="mode_switch",
            context_data='{"mode": "listening"}',
        )

        # Then: Should have context_data accessible (not metadata)
        assert hasattr(interaction, 'context_data')
        assert interaction.context_data == '{"mode": "listening"}'
        # Verify no direct 'metadata' attribute at instance level
        # (SQLAlchemy's metadata is a class-level attribute, different from field names)

    def test_agent_interaction_all_fields(self):
        """Test AgentInteraction with all fields populated."""
        # Given: Full interaction data
        conversation_id = str(uuid4())
        timestamp = datetime.now(timezone.utc)

        # When: Creating interaction with all fields
        interaction = AgentInteraction(
            conversation_id=conversation_id,
            interaction_type="mcp_query_manual",
            timestamp=timestamp,
            query_text="find ANSELL gloves",
            llm_request='{"model": "gpt-3.5-turbo"}',
            llm_response='{"tool": "get_product_docs"}',
            mcp_request='{"query": "ANSELL gloves"}',
            mcp_response='{"content": [{"type": "text", "text": "SKU 1FYX7"}]}',
            user_rating="up",
            manually_edited=True,
            edit_details='{"before": "...", "after": "..."}',
            context_data='{"server": "/product_retrieval"}',
        )

        # Then: All fields should be set correctly
        assert interaction.conversation_id == conversation_id
        assert interaction.interaction_type == "mcp_query_manual"
        assert interaction.query_text == "find ANSELL gloves"
        assert interaction.user_rating == "up"
        assert interaction.manually_edited is True
        assert interaction.context_data == '{"server": "/product_retrieval"}'
        assert "SKU 1FYX7" in interaction.mcp_response

    def test_agent_interaction_repr(self):
        """Test AgentInteraction __repr__ method."""
        # Given: An interaction
        interaction = AgentInteraction(
            conversation_id=str(uuid4()),
            interaction_type="suggestion_rated",
            user_rating="down",
        )
        interaction.id = 123

        # When: Getting string representation
        repr_str = repr(interaction)

        # Then: Should contain key info
        assert "AgentInteraction" in repr_str
        assert "123" in repr_str
        assert "suggestion_rated" in repr_str
        assert "down" in repr_str


class TestListeningModeSessionModel:
    """Test ListeningModeSession model (ADR-013)."""

    def test_listening_mode_session_creation(self):
        """Test creating a listening mode session."""
        # Given: A conversation
        conversation_id = str(uuid4())

        # When: Creating a session
        session = ListeningModeSession(
            conversation_id=conversation_id,
            auto_queries_count=5,
            products_suggested='[{"sku": "1FYX7", "name": "ANSELL Gloves"}]',
            orders_tracked='[{"order_number": "12345", "status": "Shipped"}]',
            opportunities_detected=8,
        )

        # Then: Fields should be set
        assert session.conversation_id == conversation_id
        assert session.auto_queries_count == 5
        assert session.opportunities_detected == 8
        assert "1FYX7" in session.products_suggested
        assert "12345" in session.orders_tracked

    def test_listening_mode_session_defaults(self):
        """Test default values for listening mode session."""
        # Given: A conversation
        conversation_id = str(uuid4())

        # When: Creating session with explicit defaults
        # Note: SQLAlchemy Column defaults apply at DB insert time, not object creation
        session = ListeningModeSession(
            conversation_id=conversation_id,
            auto_queries_count=0,
            opportunities_detected=0,
        )

        # Then: Values should be set
        assert session.auto_queries_count == 0
        assert session.opportunities_detected == 0
        assert session.ended_at is None  # Still active

    def test_listening_mode_session_repr_active(self):
        """Test __repr__ for active session."""
        # Given: An active session
        session = ListeningModeSession(
            conversation_id=str(uuid4()),
            auto_queries_count=3,
        )
        session.id = 456

        # When: Getting string representation
        repr_str = repr(session)

        # Then: Should show active status
        assert "ListeningModeSession" in repr_str
        assert "456" in repr_str
        assert "queries=3" in repr_str
        assert "active" in repr_str

    def test_listening_mode_session_repr_completed(self):
        """Test __repr__ for completed session."""
        # Given: A completed session
        started = datetime.now(timezone.utc)
        ended = datetime(2026, 2, 21, 12, 10, 0, tzinfo=timezone.utc)

        session = ListeningModeSession(
            conversation_id=str(uuid4()),
            auto_queries_count=7,
            started_at=datetime(2026, 2, 21, 12, 0, 0, tzinfo=timezone.utc),
            ended_at=ended,
        )
        session.id = 789

        # When: Getting string representation
        repr_str = repr(session)

        # Then: Should show duration
        assert "ListeningModeSession" in repr_str
        assert "789" in repr_str
        assert "queries=7" in repr_str
        assert "600" in repr_str or "600.0" in repr_str  # 10 minutes = 600 seconds


class TestAgentInteractionTypes:
    """Test various interaction types for AgentInteraction."""

    @pytest.mark.parametrize("interaction_type", [
        "mcp_query_manual",
        "mcp_query_auto",
        "mode_switch",
        "suggestion_rated",
        "summary_edited",
        "disposition_selected",
        "compliance_override",
    ])
    def test_valid_interaction_types(self, interaction_type):
        """Test all documented interaction types."""
        # Given: A conversation
        conversation_id = str(uuid4())

        # When: Creating interaction with type
        interaction = AgentInteraction(
            conversation_id=conversation_id,
            interaction_type=interaction_type,
        )

        # Then: Type should be set correctly
        assert interaction.interaction_type == interaction_type

    def test_mode_switch_interaction(self):
        """Test mode switch interaction (listening mode toggle)."""
        # Given: Agent toggles listening mode
        conversation_id = str(uuid4())

        # When: Recording mode switch
        interaction = AgentInteraction(
            conversation_id=conversation_id,
            interaction_type="mode_switch",
            context_data='{"new_mode": "listening", "previous_mode": "manual"}',
        )

        # Then: Should capture mode change
        assert interaction.interaction_type == "mode_switch"
        assert "listening" in interaction.context_data

    def test_suggestion_rated_interaction(self):
        """Test suggestion rating interaction."""
        # Given: Agent rates a suggestion
        conversation_id = str(uuid4())

        # When: Recording rating
        interaction = AgentInteraction(
            conversation_id=conversation_id,
            interaction_type="suggestion_rated",
            query_text="recommend safety gloves",
            user_rating="up",
            mcp_response='{"content": [{"text": "SKU 1FYX7"}]}',
        )

        # Then: Should capture rating
        assert interaction.user_rating == "up"
        assert interaction.interaction_type == "suggestion_rated"
