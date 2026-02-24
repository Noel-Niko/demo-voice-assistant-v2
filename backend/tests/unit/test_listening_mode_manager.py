"""Unit tests for ListeningModeManager service.

Tests the session lifecycle management and auto-query execution
for listening mode.
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from app.services.listening_mode_manager import ListeningModeManager
from app.services.event_bus import Event
from app.models.domain import ListeningModeSession


@pytest.fixture
def mock_repository():
    """Mock conversation repository."""
    repo = AsyncMock()
    repo.create_listening_mode_session = AsyncMock(return_value=1)
    repo.get_active_listening_mode_session = AsyncMock(return_value=None)
    repo.update_listening_mode_session = AsyncMock()
    repo.end_listening_mode_session = AsyncMock()
    repo.save_agent_interaction = AsyncMock()
    return repo


@pytest.fixture
def mock_event_bus():
    """Mock event bus."""
    bus = AsyncMock()
    bus.subscribe = Mock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_mcp_orchestrator():
    """Mock MCP orchestrator."""
    orchestrator = AsyncMock()
    orchestrator.query = AsyncMock(return_value={
        "success": True,
        "result": "Product found: Ladder X1000",
        "server_used": "product-search",
        "tool_used": "search_products"
    })
    return orchestrator


@pytest.fixture
def mock_cache():
    """Mock cache."""
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


@pytest.fixture
def manager(mock_repository, mock_event_bus, mock_mcp_orchestrator, mock_cache):
    """Create ListeningModeManager instance."""
    return ListeningModeManager(
        repository=mock_repository,
        event_bus=mock_event_bus,
        mcp_orchestrator=mock_mcp_orchestrator,
        cache=mock_cache,
    )


@pytest.mark.asyncio
class TestListeningModeManager:
    """Test suite for ListeningModeManager service."""

    async def test_subscribes_to_opportunity_events(self, manager, mock_event_bus):
        """Test that manager subscribes to opportunity.detected events."""
        # Verify subscription was registered
        mock_event_bus.subscribe.assert_called_once_with(
            "listening_mode.opportunity.detected",
            manager._on_opportunity_detected
        )

    async def test_starts_session_on_first_opportunity(self, manager, mock_repository):
        """Test that session is created when first opportunity arrives."""
        conversation_id = uuid4()

        # Mock no active session
        mock_repository.get_active_listening_mode_session.return_value = None

        # Create opportunity event
        event = Event.create(
            event_type="listening_mode.opportunity.detected",
            source="opportunity_detector",
            conversation_id=str(conversation_id),
            data={
                "opportunity_type": "product_search",
                "confidence": 0.9,
                "query_text": "warehouse ladder",
                "reasoning": "Customer requested ladder",
                "semantic_fingerprint": "product_search_ladder"
            }
        )

        # Trigger opportunity
        await manager._on_opportunity_detected(event)
        await asyncio.sleep(0.1)  # Let async tasks run

        # Verify session was created
        mock_repository.create_listening_mode_session.assert_called_once_with(conversation_id)

    async def test_prevents_duplicate_sessions(self, manager, mock_repository):
        """Test that duplicate sessions are not created if one is already active."""
        conversation_id = uuid4()

        # Mock active session already exists
        active_session = Mock(spec=ListeningModeSession)
        active_session.id = 1
        active_session.conversation_id = str(conversation_id)
        mock_repository.get_active_listening_mode_session.return_value = active_session

        # Create opportunity event
        event = Event.create(
            event_type="listening_mode.opportunity.detected",
            source="opportunity_detector",
            conversation_id=str(conversation_id),
            data={
                "opportunity_type": "product_search",
                "confidence": 0.9,
                "query_text": "warehouse ladder",
                "reasoning": "Customer requested ladder",
                "semantic_fingerprint": "product_search_ladder"
            }
        )

        # Trigger opportunity
        await manager._on_opportunity_detected(event)
        await asyncio.sleep(0.1)

        # Verify session was NOT created (already exists)
        mock_repository.create_listening_mode_session.assert_not_called()

    async def test_executes_auto_query_on_opportunity(
        self, manager, mock_repository, mock_mcp_orchestrator, mock_event_bus
    ):
        """Test that MCP query is executed when opportunity is detected."""
        conversation_id = uuid4()

        # Mock active session
        active_session = Mock(spec=ListeningModeSession)
        active_session.id = 1
        active_session.conversation_id = str(conversation_id)
        active_session.auto_queries_count = 0
        active_session.opportunities_detected = 0
        mock_repository.get_active_listening_mode_session.return_value = active_session

        # Create opportunity event
        event = Event.create(
            event_type="listening_mode.opportunity.detected",
            source="opportunity_detector",
            conversation_id=str(conversation_id),
            data={
                "opportunity_type": "product_search",
                "confidence": 0.9,
                "query_text": "warehouse ladder",
                "reasoning": "Customer requested ladder",
                "semantic_fingerprint": "product_search_ladder"
            }
        )

        # Trigger opportunity
        await manager._on_opportunity_detected(event)
        await asyncio.sleep(0.1)

        # Verify MCP query was executed
        mock_mcp_orchestrator.query.assert_called_once()
        call_kwargs = mock_mcp_orchestrator.query.call_args.kwargs
        assert call_kwargs["user_query"] == "warehouse ladder"
        assert call_kwargs["preferred_server"] is None  # Let LLM select

    async def test_logs_agent_interaction_for_auto_query(
        self, manager, mock_repository, mock_mcp_orchestrator
    ):
        """Test that auto-query is logged to AgentInteraction table."""
        import json
        conversation_id = uuid4()

        # Mock active session
        active_session = Mock(spec=ListeningModeSession)
        active_session.id = 1
        active_session.conversation_id = str(conversation_id)
        active_session.auto_queries_count = 0
        active_session.opportunities_detected = 0
        mock_repository.get_active_listening_mode_session.return_value = active_session

        # Create opportunity event
        event = Event.create(
            event_type="listening_mode.opportunity.detected",
            source="opportunity_detector",
            conversation_id=str(conversation_id),
            data={
                "opportunity_type": "product_search",
                "confidence": 0.9,
                "query_text": "warehouse ladder",
                "reasoning": "Customer requested ladder",
                "semantic_fingerprint": "product_search_ladder"
            }
        )

        # Trigger opportunity
        await manager._on_opportunity_detected(event)
        await asyncio.sleep(0.1)

        # Verify interaction was logged
        mock_repository.save_agent_interaction.assert_called_once()
        call_kwargs = mock_repository.save_agent_interaction.call_args.kwargs
        assert call_kwargs["conversation_id"] == conversation_id
        assert call_kwargs["interaction_type"] == "mcp_query_auto"
        assert call_kwargs["query_text"] == "warehouse ladder"

        # Parse context_data JSON
        context_data = json.loads(call_kwargs["context_data"])
        assert context_data["tool_used"] == "search_products"
        assert context_data["mcp_server_used"] == "product-search"
        assert context_data["opportunity_type"] == "product_search"

    async def test_increments_session_metrics(
        self, manager, mock_repository, mock_mcp_orchestrator
    ):
        """Test that session metrics are incremented after auto-query."""
        conversation_id = uuid4()

        # Mock active session
        active_session = Mock(spec=ListeningModeSession)
        active_session.id = 1
        active_session.conversation_id = str(conversation_id)
        active_session.auto_queries_count = 2
        active_session.opportunities_detected = 5
        mock_repository.get_active_listening_mode_session.return_value = active_session

        # Create opportunity event
        event = Event.create(
            event_type="listening_mode.opportunity.detected",
            source="opportunity_detector",
            conversation_id=str(conversation_id),
            data={
                "opportunity_type": "order_tracking",
                "confidence": 0.95,
                "query_text": "order 771903",
                "reasoning": "Customer mentioned order number",
                "semantic_fingerprint": "order_tracking_771903"
            }
        )

        # Trigger opportunity
        await manager._on_opportunity_detected(event)
        await asyncio.sleep(0.1)

        # Verify session was updated with incremented counts
        mock_repository.update_listening_mode_session.assert_called()
        call_kwargs = mock_repository.update_listening_mode_session.call_args.kwargs
        assert call_kwargs["session_id"] == 1
        assert call_kwargs["auto_queries_count"] == 3  # Incremented from 2
        assert call_kwargs["opportunities_detected"] == 6  # Incremented from 5

    async def test_handles_mcp_errors_gracefully(
        self, manager, mock_repository, mock_mcp_orchestrator, mock_event_bus
    ):
        """Test that MCP errors don't crash the manager."""
        conversation_id = uuid4()

        # Mock active session
        active_session = Mock(spec=ListeningModeSession)
        active_session.id = 1
        active_session.conversation_id = str(conversation_id)
        active_session.auto_queries_count = 0
        active_session.opportunities_detected = 0
        mock_repository.get_active_listening_mode_session.return_value = active_session

        # Mock MCP error
        mock_mcp_orchestrator.query.side_effect = Exception("MCP server timeout")

        # Create opportunity event
        event = Event.create(
            event_type="listening_mode.opportunity.detected",
            source="opportunity_detector",
            conversation_id=str(conversation_id),
            data={
                "opportunity_type": "product_search",
                "confidence": 0.9,
                "query_text": "warehouse ladder",
                "reasoning": "Customer requested ladder",
                "semantic_fingerprint": "product_search_ladder"
            }
        )

        # Trigger opportunity (should not raise exception)
        await manager._on_opportunity_detected(event)
        await asyncio.sleep(0.1)

        # Verify error event was published
        published_events = [call[0][0] for call in mock_event_bus.publish.call_args_list]
        error_events = [e for e in published_events if e.event_type == "listening_mode.query.error"]
        assert len(error_events) >= 1

        # Verify session metrics still updated (opportunity counted even if query failed)
        mock_repository.update_listening_mode_session.assert_called()
        call_kwargs = mock_repository.update_listening_mode_session.call_args.kwargs
        assert call_kwargs["opportunities_detected"] == 1

    async def test_publishes_query_complete_event(
        self, manager, mock_repository, mock_mcp_orchestrator, mock_event_bus
    ):
        """Test that query.complete event is published after successful query."""
        conversation_id = uuid4()

        # Mock active session
        active_session = Mock(spec=ListeningModeSession)
        active_session.id = 1
        active_session.conversation_id = str(conversation_id)
        active_session.auto_queries_count = 0
        active_session.opportunities_detected = 0
        mock_repository.get_active_listening_mode_session.return_value = active_session

        # Create opportunity event
        event = Event.create(
            event_type="listening_mode.opportunity.detected",
            source="opportunity_detector",
            conversation_id=str(conversation_id),
            data={
                "opportunity_type": "product_search",
                "confidence": 0.9,
                "query_text": "warehouse ladder",
                "reasoning": "Customer requested ladder",
                "semantic_fingerprint": "product_search_ladder"
            }
        )

        # Trigger opportunity
        await manager._on_opportunity_detected(event)
        await asyncio.sleep(0.1)

        # Verify query.complete event was published
        published_events = [call[0][0] for call in mock_event_bus.publish.call_args_list]
        complete_events = [e for e in published_events if e.event_type == "listening_mode.query.complete"]
        assert len(complete_events) >= 1

        complete_event = complete_events[0]
        assert complete_event.data["opportunity_type"] == "product_search"
        assert complete_event.data["query_text"] == "warehouse ladder"
        assert complete_event.data["result"]["success"] is True

    async def test_start_session_public_method(self, manager, mock_repository):
        """Test public start_session method."""
        conversation_id = uuid4()

        # Start session
        session_id = await manager.start_session(conversation_id)

        # Verify session was created
        assert session_id == 1
        mock_repository.create_listening_mode_session.assert_called_once_with(conversation_id)

    async def test_stop_session_public_method(self, manager, mock_repository):
        """Test public stop_session method."""
        conversation_id = uuid4()

        # Mock active session
        active_session = Mock(spec=ListeningModeSession)
        active_session.id = 5
        active_session.conversation_id = str(conversation_id)
        mock_repository.get_active_listening_mode_session.return_value = active_session

        # Stop session
        await manager.stop_session(conversation_id)

        # Verify session was ended
        mock_repository.end_listening_mode_session.assert_called_once_with(5)

    async def test_shutdown_cancels_background_tasks(
        self, manager, mock_repository, mock_mcp_orchestrator, mock_event_bus
    ):
        """Test that shutdown cancels all background auto-query tasks.

        Bug: Background tasks created by _execute_auto_query continue running
        after shutdown, trying to use event bus and HTTP clients that are closed.

        This test verifies that shutdown properly cancels all tasks.
        """
        conversation_id = uuid4()

        # Mock active session
        active_session = Mock(spec=ListeningModeSession)
        active_session.id = 1
        active_session.conversation_id = str(conversation_id)
        active_session.auto_queries_count = 0
        active_session.opportunities_detected = 0
        mock_repository.get_active_listening_mode_session.return_value = active_session

        # Make MCP query slow (so task is still running when we shutdown)
        async def slow_query(*args, **kwargs):
            await asyncio.sleep(2)  # Long enough to still be running
            return {"success": True, "result": "Done", "tool_used": "test"}

        mock_mcp_orchestrator.query.side_effect = slow_query

        # Create opportunity event to trigger background task
        event = Event.create(
            event_type="listening_mode.opportunity.detected",
            source="opportunity_detector",
            conversation_id=str(conversation_id),
            data={
                "opportunity_type": "product_search",
                "confidence": 0.9,
                "query_text": "warehouse ladder",
                "reasoning": "Customer requested ladder",
                "semantic_fingerprint": "product_search_ladder"
            }
        )

        # Trigger opportunity (creates background task)
        await manager._on_opportunity_detected(event)
        await asyncio.sleep(0.1)  # Let task start

        # At this point, task is running and waiting in slow_query
        # Verify we have active background tasks
        assert len(manager._background_tasks) > 0, "Should have background tasks running"

        # Now shutdown the manager
        await manager.shutdown()

        # Verify all tasks were cancelled and cleared
        assert len(manager._background_tasks) == 0, "All tasks should be cancelled and cleared"
        assert manager._shutting_down is True, "Shutdown flag should be set"

        # Verify event bus publish was NOT called after shutdown
        # (if task kept running, it would try to publish complete event)
        await asyncio.sleep(0.2)

        # Count how many times publish was called
        # Should only be the 'started' event, not 'complete' (task was cancelled)
        publish_calls = mock_event_bus.publish.call_count
        published_events = [call[0][0] for call in mock_event_bus.publish.call_args_list]
        complete_events = [e for e in published_events if e.event_type == "listening_mode.query.complete"]

        # Task was cancelled, so complete event should NOT be published
        assert len(complete_events) == 0, "Complete event should not be published (task cancelled)"
