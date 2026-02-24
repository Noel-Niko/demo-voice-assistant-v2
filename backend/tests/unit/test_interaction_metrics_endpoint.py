"""Tests for interaction metrics endpoint rating counts.

Verifies that GET /api/conversations/{id}/metrics correctly counts ratings
from the user_rating field, not from a non-existent interaction_type.
"""
import pytest
import pytest_asyncio
from uuid import uuid4
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.models.database import init_db, get_session_maker
from app.models.domain import AgentInteraction, Conversation
from app.repositories.conversation_repository import ConversationRepository


@pytest_asyncio.fixture
async def test_app():
    """Create test application with initialized database."""
    await init_db()

    # Initialize repository and add to app state
    session_maker = get_session_maker()
    repository = ConversationRepository(session_maker)
    app.state.repository = repository

    yield app


@pytest.mark.asyncio
async def test_interaction_metrics_counts_ratings_from_user_rating_field(test_app):
    """Test that interaction metrics counts ratings from user_rating field.

    The endpoint should count interactions where user_rating='up' or 'down',
    regardless of interaction_type. The old broken code filtered by
    interaction_type='suggestion_rated' which never existed.
    """
    from sqlalchemy import select

    session_maker = get_session_maker()

    # Create test conversation
    conversation_id = uuid4()
    async with session_maker() as session:
        conversation = Conversation(
            id=str(conversation_id),
            agent_id="test-agent",
            customer_id="test-customer",
        )
        session.add(conversation)

        # Create agent interactions with ratings
        # These should be counted regardless of interaction_type
        interaction_up_1 = AgentInteraction(
            conversation_id=str(conversation_id),
            interaction_type="mcp_query_manual",
            query_text="test query 1",
            user_rating="up",
        )
        interaction_up_2 = AgentInteraction(
            conversation_id=str(conversation_id),
            interaction_type="mcp_query_auto",
            query_text="test query 2",
            user_rating="up",
        )
        interaction_down = AgentInteraction(
            conversation_id=str(conversation_id),
            interaction_type="mcp_query_manual",
            query_text="test query 3",
            user_rating="down",
        )
        # Unrated interaction should not be counted
        interaction_none = AgentInteraction(
            conversation_id=str(conversation_id),
            interaction_type="mcp_query_manual",
            query_text="test query 4",
            user_rating=None,
        )

        session.add_all([
            interaction_up_1,
            interaction_up_2,
            interaction_down,
            interaction_none,
        ])
        await session.commit()

    # Test the endpoint
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/conversations/{conversation_id}/metrics")

    assert response.status_code == 200
    data = response.json()

    # Verify rating counts
    assert "summary_ratings" in data
    assert data["summary_ratings"]["up"] == 2, "Should count 2 'up' ratings"
    assert data["summary_ratings"]["down"] == 1, "Should count 1 'down' rating"

    # Cleanup
    async with session_maker() as session:
        # Delete interactions first (foreign key constraint)
        stmt = select(AgentInteraction).where(
            AgentInteraction.conversation_id == str(conversation_id)
        )
        result = await session.execute(stmt)
        interactions = result.scalars().all()
        for interaction in interactions:
            await session.delete(interaction)

        # Delete conversation
        stmt = select(Conversation).where(Conversation.id == str(conversation_id))
        result = await session.execute(stmt)
        conversation = result.scalar_one_or_none()
        if conversation:
            await session.delete(conversation)

        await session.commit()


@pytest.mark.asyncio
async def test_interaction_metrics_ignores_null_ratings(test_app):
    """Test that interactions with null user_rating are not counted.

    Only interactions with explicit 'up' or 'down' ratings should be counted.
    """
    from sqlalchemy import select

    session_maker = get_session_maker()

    # Create test conversation
    conversation_id = uuid4()
    async with session_maker() as session:
        conversation = Conversation(
            id=str(conversation_id),
            agent_id="test-agent",
            customer_id="test-customer",
        )
        session.add(conversation)

        # Create interactions with null ratings
        interaction_1 = AgentInteraction(
            conversation_id=str(conversation_id),
            interaction_type="mcp_query_manual",
            query_text="test query 1",
            user_rating=None,
        )
        interaction_2 = AgentInteraction(
            conversation_id=str(conversation_id),
            interaction_type="mcp_query_auto",
            query_text="test query 2",
            user_rating=None,
        )

        session.add_all([interaction_1, interaction_2])
        await session.commit()

    # Test the endpoint
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/conversations/{conversation_id}/metrics")

    assert response.status_code == 200
    data = response.json()

    # Verify no ratings counted
    assert "summary_ratings" in data
    assert data["summary_ratings"]["up"] == 0, "Should count 0 'up' ratings"
    assert data["summary_ratings"]["down"] == 0, "Should count 0 'down' ratings"

    # Cleanup
    async with session_maker() as session:
        # Delete interactions first
        stmt = select(AgentInteraction).where(
            AgentInteraction.conversation_id == str(conversation_id)
        )
        result = await session.execute(stmt)
        interactions = result.scalars().all()
        for interaction in interactions:
            await session.delete(interaction)

        # Delete conversation
        stmt = select(Conversation).where(Conversation.id == str(conversation_id))
        result = await session.execute(stmt)
        conversation = result.scalar_one_or_none()
        if conversation:
            await session.delete(conversation)

        await session.commit()
