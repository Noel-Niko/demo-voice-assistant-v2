"""Tests for manual query recording in agent_interactions table.

Verifies that manual MCP queries are saved to agent_interactions and
that interaction IDs are returned for rating functionality.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from app.main import app
from app.models.database import create_engine, create_session_maker, init_db
from app.repositories.conversation_repository import ConversationRepository
from app.config import settings


@pytest_asyncio.fixture
async def test_app(monkeypatch):
    """Create test app with initialized database."""
    # Set required environment variables
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")

    engine = create_engine()
    await init_db(engine)
    session_maker = create_session_maker(engine)
    repository = ConversationRepository(session_maker)
    app.state.repository = repository

    # Mock model_manager
    mock_model_manager = Mock()
    mock_model_manager.get_current_preset = Mock(return_value=Mock(model_name="gpt-3.5-turbo", reasoning_effort=None))
    app.state.model_manager = mock_model_manager

    # Mock MCP client (prevents 503 error)
    app.state.mcp_client = Mock()

    yield app


@pytest.mark.asyncio
async def test_save_agent_interaction_returns_int(test_app):
    """Test that save_agent_interaction() returns an integer interaction_id.

    This is required for rating functionality - we need the ID to associate
    ratings with the correct interaction.
    """
    repository = test_app.state.repository
    conversation_id = uuid4()

    # Save a manual query interaction
    interaction_id = await repository.save_agent_interaction(
        conversation_id=conversation_id,
        interaction_type="manual_query",
        query_text="Test query",
        mcp_request='{"servers": ["brave-search"], "query": "Test"}',
        mcp_response='{"results": "Test results"}',
    )

    # Should return an integer
    assert isinstance(interaction_id, int), \
        "save_agent_interaction should return int interaction_id"
    assert interaction_id > 0, \
        "interaction_id should be positive"


@pytest.mark.asyncio
async def test_manual_query_saves_agent_interaction(test_app):
    """Test that manual MCP query endpoint saves to agent_interactions table.

    When user submits manual query, should save interaction with type='manual_query',
    query_text, mcp_request, and mcp_response for dashboard metrics.
    """
    from app.api.dependencies import get_mcp_orchestrator

    repository = test_app.state.repository

    # Create conversation first
    conversation_id = await repository.create_conversation()

    # Mock MCP orchestrator - must mock .query() which is what routes.py calls
    mock_orchestrator = AsyncMock()
    mock_orchestrator.set_progress_callback = Mock()
    mock_orchestrator.query = AsyncMock(return_value={
        "result": {"content": [{"title": "Result 1", "text": "Found 1 result", "url": "http://example.com"}]},
        "server_path": "brave-search",
        "tool_name": "search",
    })

    # Override dependency
    test_app.dependency_overrides[get_mcp_orchestrator] = lambda: mock_orchestrator

    try:
        with TestClient(test_app) as client:
            response = client.post(
                "/api/mcp/query",
                json={
                    "conversation_id": str(conversation_id),
                    "query": "test search query",
                },
            )
    finally:
        # Clean up override
        test_app.dependency_overrides.clear()

    # Should succeed
    assert response.status_code == 200, \
        f"Manual query should succeed: {response.text}"

    # Check that agent_interaction was saved
    interactions = await repository.get_agent_interactions(conversation_id)
    assert len(interactions) == 1, \
        "Should save exactly 1 agent interaction"

    interaction = interactions[0]
    assert interaction.interaction_type == "manual_query", \
        "Should save with type='manual_query'"
    assert interaction.query_text == "test search query", \
        "Should save original query text"
    assert interaction.mcp_request is not None, \
        "Should save MCP request payload"
    assert interaction.mcp_response is not None, \
        "Should save MCP response payload"


@pytest.mark.asyncio
async def test_manual_query_returns_interaction_id_in_sse(test_app):
    """Test that manual query SSE response includes interaction_id.

    The interaction_id is needed by frontend to enable thumbs up/down rating.
    """
    from app.api.dependencies import get_mcp_orchestrator

    repository = test_app.state.repository

    # Create conversation
    conversation_id = await repository.create_conversation()

    # Mock MCP orchestrator - must mock .query() which is what routes.py calls
    mock_orchestrator = AsyncMock()
    mock_orchestrator.set_progress_callback = Mock()
    mock_orchestrator.query = AsyncMock(return_value={
        "result": {"content": [{"title": "Result", "text": "Found result"}]},
        "server_path": "brave-search",
        "tool_name": "search",
    })

    # Override dependency
    test_app.dependency_overrides[get_mcp_orchestrator] = lambda: mock_orchestrator

    try:
        with TestClient(test_app) as client:
            response = client.post(
                "/api/mcp/query",
                json={
                    "conversation_id": str(conversation_id),
                    "query": "test query",
                },
            )
    finally:
        test_app.dependency_overrides.clear()

    # Parse SSE response
    assert response.status_code == 200
    lines = response.text.strip().split("\n")

    # Find the result event - SSE format is: data: {"type": "result", "data": {...}}
    import json
    result_data = None
    for line in lines:
        if line.startswith("data: ") and line != "data: [DONE]":
            payload = json.loads(line[len("data: "):])
            if payload.get("type") == "result":
                result_data = payload.get("data")
                break

    assert result_data is not None, \
        "Should have result event in SSE stream"

    assert "interaction_id" in result_data, \
        "SSE result should include interaction_id for rating"
    assert isinstance(result_data["interaction_id"], int), \
        "interaction_id should be int"
    assert result_data["interaction_id"] > 0, \
        "interaction_id should be positive"


@pytest.mark.asyncio
async def test_manual_query_with_conversation_id_in_body(test_app):
    """Test that frontend sends conversation_id in request body.

    The endpoint needs conversation_id to save the interaction to the
    correct conversation for dashboard filtering.
    """
    from app.api.dependencies import get_mcp_orchestrator

    repository = test_app.state.repository

    # Create conversation
    conversation_id = await repository.create_conversation()

    # Mock MCP orchestrator - must mock .query() which is what routes.py calls
    mock_orchestrator = AsyncMock()
    mock_orchestrator.set_progress_callback = Mock()
    mock_orchestrator.query = AsyncMock(return_value={
        "result": {"content": []},
        "server_path": "brave-search",
        "tool_name": "search",
    })

    # Override dependency
    test_app.dependency_overrides[get_mcp_orchestrator] = lambda: mock_orchestrator

    try:
        with TestClient(test_app) as client:
            # Request should include conversation_id in body
            response = client.post(
                "/api/mcp/query",
                json={
                    "conversation_id": str(conversation_id),
                    "query": "test",
                },
            )
    finally:
        test_app.dependency_overrides.clear()

    assert response.status_code == 200, \
        "Should accept conversation_id in request body"

    # Verify interaction was saved with correct conversation_id
    interactions = await repository.get_agent_interactions(conversation_id)
    assert len(interactions) == 1, \
        "Should save interaction with provided conversation_id"
    assert interactions[0].conversation_id == str(conversation_id), \
        "Should use conversation_id from request body"


@pytest.mark.asyncio
async def test_manual_query_resilient_to_save_failures(test_app):
    """Test that manual query succeeds even if save_agent_interaction fails.

    Uses fire-and-forget pattern - save failure should not break user experience.
    Should log warning but still return MCP results.
    """
    from app.api.dependencies import get_mcp_orchestrator

    repository = test_app.state.repository

    # Create conversation
    conversation_id = await repository.create_conversation()

    # Mock MCP orchestrator (successful) - must mock .query() which is what routes.py calls
    mock_orchestrator = AsyncMock()
    mock_orchestrator.set_progress_callback = Mock()
    mock_orchestrator.query = AsyncMock(return_value={
        "result": {"content": [{"title": "Result", "text": "Success"}]},
        "server_path": "brave-search",
        "tool_name": "search",
    })

    # Mock save_agent_interaction to fail
    original_save = repository.save_agent_interaction
    repository.save_agent_interaction = AsyncMock(
        side_effect=Exception("Database error")
    )

    # Override dependency
    test_app.dependency_overrides[get_mcp_orchestrator] = lambda: mock_orchestrator

    try:
        with TestClient(test_app) as client:
            response = client.post(
                "/api/mcp/query",
                json={
                    "conversation_id": str(conversation_id),
                    "query": "test",
                },
            )

        # Should still succeed (fire-and-forget)
        assert response.status_code == 200, \
            "Manual query should succeed even if save_agent_interaction fails"

        # Should still return MCP results - SSE format is: data: {"type": "result", ...}
        import json
        lines = response.text.strip().split("\n")
        has_result = False
        for line in lines:
            if line.startswith("data: ") and line != "data: [DONE]":
                try:
                    payload = json.loads(line[len("data: "):])
                    if payload.get("type") == "result":
                        has_result = True
                        break
                except json.JSONDecodeError:
                    continue
        assert has_result, "Should still stream MCP results"

    finally:
        # Restore original method
        repository.save_agent_interaction = original_save
        # Clean up override
        test_app.dependency_overrides.clear()
