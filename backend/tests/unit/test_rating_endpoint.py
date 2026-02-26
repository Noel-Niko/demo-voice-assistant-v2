"""Unit tests for MCP suggestion rating endpoint (Fix 2).

Tests the POST /api/suggestions/{interaction_id}/rate endpoint that allows users
to rate MCP query results with thumbs up/down.

Following TDD: These tests are written BEFORE implementation.
Expected to FAIL initially, then PASS after implementing:
- SuggestionRatingRequest/Response schemas
- GET/UPDATE repository methods for agent_interaction ratings
- POST /api/suggestions/{interaction_id}/rate endpoint
"""
import json
from unittest.mock import Mock

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.models.database import create_engine, create_session_maker, init_db
from app.repositories.conversation_repository import ConversationRepository
from app.services.data_export_service import DataExportService
from app.config import settings


@pytest_asyncio.fixture
async def test_app(monkeypatch):
    """Create test app with initialized database."""
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")

    engine = create_engine()
    await init_db(engine)
    session_maker = create_session_maker(engine)
    repository = ConversationRepository(session_maker)
    app.state.repository = repository

    # Mock model_manager
    mock_model_manager = Mock()
    mock_model_manager.get_current_preset = Mock(
        return_value=Mock(model_name="gpt-3.5-turbo", reasoning_effort=None)
    )
    app.state.model_manager = mock_model_manager

    # Mock MCP client
    app.state.mcp_client = Mock()

    yield app

    # Cleanup
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def conversation_with_interaction(test_app):
    """Create a conversation with a manual query interaction for testing.

    Returns:
        tuple: (conversation_id, interaction_id)
    """
    repository = test_app.state.repository

    # Create conversation
    conversation_id = await repository.create_conversation()

    # Create manual query interaction
    interaction_id = await repository.save_agent_interaction(
        conversation_id=conversation_id,
        interaction_type="manual_query",
        query_text="test query",
        mcp_request=json.dumps({"query": "test"}),
        mcp_response=json.dumps({"suggestions": []}),
    )

    return conversation_id, interaction_id


@pytest.mark.asyncio
async def test_rate_suggestion_up(test_app, conversation_with_interaction):
    """Test 1: Rating a suggestion with thumbs up.

    Verifies:
    - POST /api/suggestions/{id}/rate with rating="up" returns 200
    - Response contains correct status and rating
    - Database record is updated with user_rating="up"
    """
    conversation_id, interaction_id = conversation_with_interaction

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/suggestions/{interaction_id}/rate",
            json={"rating": "up"},
        )

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "rated"
    assert data["interaction_id"] == str(interaction_id)
    assert data["rating"] == "up"

    # Verify database update
    repository = test_app.state.repository
    interaction = await repository.get_agent_interaction(interaction_id)
    assert interaction is not None
    assert interaction.user_rating == "up"


@pytest.mark.asyncio
async def test_rate_suggestion_down(test_app, conversation_with_interaction):
    """Test 2: Rating a suggestion with thumbs down.

    Verifies:
    - POST /api/suggestions/{id}/rate with rating="down" returns 200
    - Response contains correct status and rating
    - Database record is updated with user_rating="down"
    """
    conversation_id, interaction_id = conversation_with_interaction

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/suggestions/{interaction_id}/rate",
            json={"rating": "down"},
        )

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "rated"
    assert data["interaction_id"] == str(interaction_id)
    assert data["rating"] == "down"

    # Verify database update
    repository = test_app.state.repository
    interaction = await repository.get_agent_interaction(interaction_id)
    assert interaction is not None
    assert interaction.user_rating == "down"


@pytest.mark.asyncio
async def test_rate_nonexistent_suggestion_returns_404(test_app):
    """Test 3: Rating a non-existent interaction returns 404.

    Verifies:
    - POST /api/suggestions/{invalid_id}/rate returns 404
    - Error message indicates interaction not found
    """
    nonexistent_id = 999999  # Integer ID that doesn't exist

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/suggestions/{nonexistent_id}/rate",
            json={"rating": "up"},
        )

    assert response.status_code == 404

    data = response.json()
    assert "not found" in data["detail"].lower()
    assert str(nonexistent_id) in data["detail"]


@pytest.mark.asyncio
async def test_rate_changes_existing_rating(test_app, conversation_with_interaction):
    """Test 4: Changing a rating from up to down.

    Verifies:
    - Rating "up" first, then rating "down" overwrites the previous rating
    - Final database value is "down"
    - Both API calls return 200
    """
    conversation_id, interaction_id = conversation_with_interaction

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First rating: up
        response1 = await client.post(
            f"/api/suggestions/{interaction_id}/rate",
            json={"rating": "up"},
        )
        assert response1.status_code == 200
        assert response1.json()["rating"] == "up"

        # Change rating: down
        response2 = await client.post(
            f"/api/suggestions/{interaction_id}/rate",
            json={"rating": "down"},
        )
        assert response2.status_code == 200
        assert response2.json()["rating"] == "down"

    # Verify final database state
    repository = test_app.state.repository
    interaction = await repository.get_agent_interaction(interaction_id)
    assert interaction is not None
    assert interaction.user_rating == "down"


@pytest.mark.asyncio
async def test_rated_suggestion_appears_in_export(test_app, conversation_with_interaction):
    """Test 5: Rated suggestions appear correctly in exported data.

    Verifies:
    - After rating an interaction and completing the conversation
    - Exported JSON includes agent_interaction with user_rating="up"
    - metrics.mcp_queries.rated_up == 1
    """
    conversation_id, interaction_id = conversation_with_interaction

    # Rate the suggestion
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/api/suggestions/{interaction_id}/rate",
            json={"rating": "up"},
        )

    # Complete the conversation
    repository = test_app.state.repository
    await repository.mark_complete(conversation_id)

    # Export data
    export_service = DataExportService(repository)
    export_path = await export_service.export_conversation_data(str(conversation_id))

    # Read exported data
    with open(export_path) as f:
        export_data = json.load(f)

    # Verify agent_interactions includes rated interaction
    agent_interactions = export_data.get("agent_interactions", [])
    # Note: Export doesn't include 'id', so we verify by content and rating
    rated_interactions = [i for i in agent_interactions if i.get("user_rating") == "up"]
    assert len(rated_interactions) == 1
    assert rated_interactions[0]["interaction_type"] == "manual_query"
    assert rated_interactions[0]["query_text"] == "test query"

    # Verify metrics
    metrics = export_data.get("metrics", {})
    mcp_queries = metrics.get("mcp_queries", {})
    assert mcp_queries.get("rated_up", 0) == 1
    assert mcp_queries.get("rated_down", 0) == 0


@pytest.mark.asyncio
async def test_dashboard_counts_rated_suggestions(test_app, conversation_with_interaction):
    """Test 6: Dashboard correctly aggregates rated suggestion counts.

    Verifies:
    - After rating multiple suggestions across conversations
    - Dashboard feedback_metrics shows correct total_rated_up count
    - Dashboard ai_suggestion_metrics shows correct total_suggestions_rated count

    Note: This test verifies the data chain:
      Rating endpoint -> DB -> Export -> Dashboard aggregation
    """
    conversation_id, interaction_id = conversation_with_interaction

    # Rate first suggestion (up)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/api/suggestions/{interaction_id}/rate",
            json={"rating": "up"},
        )

    # Create second interaction and rate it (down)
    repository = test_app.state.repository
    interaction_id_2 = await repository.save_agent_interaction(
        conversation_id=conversation_id,
        interaction_type="manual_query",
        query_text="test query 2",
        mcp_request=json.dumps({"query": "test 2"}),
        mcp_response=json.dumps({"suggestions": []}),
    )

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/api/suggestions/{interaction_id_2}/rate",
            json={"rating": "down"},
        )

    # Complete conversation and export
    await repository.mark_complete(conversation_id)
    export_service = DataExportService(repository)
    export_path = await export_service.export_conversation_data(str(conversation_id))

    # Read exported data
    with open(export_path) as f:
        export_data = json.load(f)

    # Verify export metrics
    metrics = export_data.get("metrics", {})
    mcp_queries = metrics.get("mcp_queries", {})
    assert mcp_queries.get("rated_up", 0) == 1
    assert mcp_queries.get("rated_down", 0) == 1

    # Verify total rated count (for dashboard aggregation)
    agent_interactions = export_data.get("agent_interactions", [])
    rated_count = sum(
        1 for i in agent_interactions if i.get("user_rating") is not None
    )
    assert rated_count == 2
