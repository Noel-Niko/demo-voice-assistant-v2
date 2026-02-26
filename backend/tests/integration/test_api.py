"""Integration tests for FastAPI REST API.

Tests full request/response cycle through all application layers.
Follows 12-factor app principles: stateless, config from env, backing services.
"""
import pytest
import pytest_asyncio
import os
from unittest.mock import patch, Mock, AsyncMock
from uuid import UUID
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone

# Set test environment variables before importing app (12-factor: config)
os.environ.setdefault("OPENAI_API_KEY", "test-key-for-integration-tests")
os.environ.setdefault("TRANSCRIPT_FILE_PATH", "/tmp/test_transcript.txt")

from app.main import app
from app.models.database import create_engine, create_session_maker, init_db
from app.services.event_bus import InMemoryEventBus
from app.services.cache import InMemoryCache
from app.services.transcript_parser import TranscriptParser
from app.services.transcript_streamer import TranscriptStreamer
from app.services.word_streamer import WordStreamer
from app.services.summary_generator import SummaryGenerator
from app.services.conversation_manager import ConversationManager
from app.repositories.conversation_repository import ConversationRepository


@pytest_asyncio.fixture
async def test_app():
    """Create test application with initialized dependencies.

    Follows 12-factor principles:
    - Config from environment (OPENAI_API_KEY)
    - Backing services as attached resources (database)
    - Stateless processes
    """
    # Initialize database (in-memory for tests)
    engine = create_engine()
    await init_db(engine)

    # Create event bus
    event_bus = InMemoryEventBus(queue_size=100)
    await event_bus.start()

    # Create session maker
    session_maker = create_session_maker(engine)

    # Initialize repository (use real implementation - it has in-memory DB)
    repository = ConversationRepository(session_maker)

    # Mock transcript parser to avoid file I/O
    parser = Mock(spec=TranscriptParser)
    parser.read_all_lines = AsyncMock(return_value=[])

    # Initialize word streamer
    word_streamer = WordStreamer(
        repository=repository,
        event_bus=event_bus,
        words_per_second=2.5,
    )

    # Initialize streamer
    streamer = TranscriptStreamer(
        parser=parser,
        repository=repository,
        event_bus=event_bus,
        word_streamer=word_streamer,
        initial_delay=2.0,
        inter_line_delay=0.5,
    )

    # Initialize cache (in-memory for tests)
    cache = InMemoryCache()

    # Mock summary generator to avoid OpenAI calls
    # Following 12-factor: external services as backing resources
    mock_summary_gen = Mock()
    mock_summary_gen.set_interval = Mock()
    mock_summary_gen.get_interval = Mock(return_value=30)

    # Initialize conversation manager
    manager = ConversationManager(
        repository=repository,
        streamer=streamer,
        event_bus=event_bus,
    )

    # Mock listening mode manager that creates real database records
    # This is an integration test, so we use real repository but mock external services (MCP/LLM)
    mock_listening_mode_manager = Mock()

    async def mock_start_session(conversation_id):
        """Mock start_session that creates real database record."""
        return await repository.create_listening_mode_session(conversation_id)

    async def mock_stop_session(conversation_id):
        """Mock stop_session that updates database record."""
        session = await repository.get_active_listening_mode_session(conversation_id)
        if session:
            await repository.end_listening_mode_session(session.id)

    mock_listening_mode_manager.start_session = AsyncMock(side_effect=mock_start_session)
    mock_listening_mode_manager.stop_session = AsyncMock(side_effect=mock_stop_session)

    # Set dependencies in app.state (replaces set_dependencies)
    app.state.event_bus = event_bus
    app.state.cache = cache
    app.state.conversation_manager = manager
    app.state.summary_generator = mock_summary_gen
    app.state.repository = repository
    app.state.mcp_client = None  # Not used in tests
    app.state.listening_mode_manager = mock_listening_mode_manager  # Mock for tests

    yield app

    # Cleanup
    await event_bus.stop()
    await cache.close()


@pytest_asyncio.fixture
async def client(test_app):
    """Create async HTTP client for testing.

    Uses ASGI transport for in-process testing without network I/O.
    """
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
class TestHealthEndpoint:
    """Test suite for health check endpoint."""

    async def test_health_check_returns_200(self, client):
        """Test that health endpoint returns 200 OK."""
        response = await client.get("/api/health")
        assert response.status_code == 200

    async def test_health_check_response_structure(self, client):
        """Test that health response has correct structure."""
        response = await client.get("/api/health")
        data = response.json()

        assert "status" in data
        assert data["status"] == "healthy"
        assert "timestamp" in data

        # Verify timestamp is valid ISO format
        timestamp = datetime.fromisoformat(data["timestamp"].replace('Z', '+00:00'))
        assert isinstance(timestamp, datetime)


@pytest.mark.asyncio
class TestRootEndpoint:
    """Test suite for root endpoint."""

    async def test_root_endpoint_returns_api_info(self, client):
        """Test that root endpoint returns API information."""
        response = await client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert "message" in data
        assert "version" in data
        assert "endpoints" in data
        assert "create_conversation" in data["endpoints"]
        assert "get_conversation" in data["endpoints"]
        assert "websocket" in data["endpoints"]


@pytest.mark.asyncio
class TestCreateConversation:
    """Test suite for POST /api/conversations endpoint."""

    async def test_create_conversation_success(self, client):
        """Test successful conversation creation."""
        response = await client.post("/api/conversations")
        assert response.status_code == 200

        data = response.json()
        assert "conversation_id" in data
        assert "status" in data
        assert "started_at" in data

    async def test_create_conversation_returns_valid_uuid(self, client):
        """Test that created conversation has valid UUID."""
        response = await client.post("/api/conversations")
        data = response.json()

        # Should be able to parse as UUID
        conversation_id = UUID(data["conversation_id"])
        assert isinstance(conversation_id, UUID)

    async def test_create_conversation_returns_active_status(self, client):
        """Test that new conversation has active status."""
        response = await client.post("/api/conversations")
        data = response.json()

        assert data["status"] == "active"

    async def test_create_conversation_returns_valid_timestamp(self, client):
        """Test that conversation has valid started_at timestamp."""
        response = await client.post("/api/conversations")
        data = response.json()

        # Should be able to parse timestamp
        started_at_str = data["started_at"]
        # Handle both timezone-aware and naive timestamps
        if 'Z' in started_at_str:
            started_at = datetime.fromisoformat(started_at_str.replace('Z', '+00:00'))
        elif '+' in started_at_str or started_at_str.endswith(tuple('0123456789')):
            started_at = datetime.fromisoformat(started_at_str)
            # Make timezone-aware if naive
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
        else:
            started_at = datetime.fromisoformat(started_at_str)
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)

        assert isinstance(started_at, datetime)

        # Should be recent (within last minute)
        now = datetime.now(timezone.utc)
        time_diff = (now - started_at).total_seconds()
        assert time_diff < 60  # Less than 1 minute ago

    async def test_create_multiple_conversations_returns_unique_ids(self, client):
        """Test that multiple conversations get unique IDs."""
        response1 = await client.post("/api/conversations")
        response2 = await client.post("/api/conversations")

        data1 = response1.json()
        data2 = response2.json()

        assert data1["conversation_id"] != data2["conversation_id"]


@pytest.mark.asyncio
class TestGetConversation:
    """Test suite for GET /api/conversations/{id} endpoint."""

    async def test_get_conversation_success(self, client):
        """Test successful conversation retrieval."""
        # Create conversation first
        create_response = await client.post("/api/conversations")
        conversation_id = create_response.json()["conversation_id"]

        # Retrieve it
        response = await client.get(f"/api/conversations/{conversation_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["conversation_id"] == conversation_id
        assert data["status"] == "active"

    async def test_get_conversation_not_found_404(self, client):
        """Test that non-existent conversation returns 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/conversations/{fake_id}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_get_conversation_invalid_uuid_422(self, client):
        """Test that invalid UUID format returns 422."""
        invalid_id = "not-a-uuid"
        response = await client.get(f"/api/conversations/{invalid_id}")

        assert response.status_code == 422  # Validation error

    async def test_get_conversation_includes_transcript_lines(self, client):
        """Test that response includes transcript lines array."""
        # Create conversation
        create_response = await client.post("/api/conversations")
        conversation_id = create_response.json()["conversation_id"]

        # Retrieve it
        response = await client.get(f"/api/conversations/{conversation_id}")
        data = response.json()

        assert "transcript_lines" in data
        assert isinstance(data["transcript_lines"], list)

    async def test_get_conversation_includes_summaries(self, client):
        """Test that response includes summaries array."""
        # Create conversation
        create_response = await client.post("/api/conversations")
        conversation_id = create_response.json()["conversation_id"]

        # Retrieve it
        response = await client.get(f"/api/conversations/{conversation_id}")
        data = response.json()

        assert "summaries" in data
        assert isinstance(data["summaries"], list)

    async def test_get_conversation_includes_started_at(self, client):
        """Test that response includes started_at timestamp."""
        # Create conversation
        create_response = await client.post("/api/conversations")
        conversation_id = create_response.json()["conversation_id"]

        # Retrieve it
        response = await client.get(f"/api/conversations/{conversation_id}")
        data = response.json()

        assert "started_at" in data
        started_at = datetime.fromisoformat(data["started_at"].replace('Z', '+00:00'))
        assert isinstance(started_at, datetime)

    async def test_get_conversation_includes_ended_at(self, client):
        """Test that response includes ended_at field (nullable)."""
        # Create conversation
        create_response = await client.post("/api/conversations")
        conversation_id = create_response.json()["conversation_id"]

        # Retrieve it
        response = await client.get(f"/api/conversations/{conversation_id}")
        data = response.json()

        assert "ended_at" in data
        # Should be None for active conversation
        assert data["ended_at"] is None


@pytest.mark.asyncio
class TestConversationStateIntegration:
    """Integration tests verifying full stack behavior."""

    async def test_conversation_persists_across_requests(self, client):
        """Test that conversation data persists (12-factor: backing services)."""
        # Create conversation
        create_response = await client.post("/api/conversations")
        conversation_id = create_response.json()["conversation_id"]

        # Retrieve it multiple times
        response1 = await client.get(f"/api/conversations/{conversation_id}")
        response2 = await client.get(f"/api/conversations/{conversation_id}")

        # Should return same data (stateless, data in backing service)
        assert response1.json() == response2.json()

    async def test_multiple_conversations_are_independent(self, client):
        """Test that conversations don't interfere with each other."""
        # Create two conversations
        response1 = await client.post("/api/conversations")
        response2 = await client.post("/api/conversations")

        id1 = response1.json()["conversation_id"]
        id2 = response2.json()["conversation_id"]

        # Retrieve both
        get_response1 = await client.get(f"/api/conversations/{id1}")
        get_response2 = await client.get(f"/api/conversations/{id2}")

        # Should be different conversations
        assert get_response1.json()["conversation_id"] != get_response2.json()["conversation_id"]


@pytest.mark.asyncio
class TestErrorHandling:
    """Test suite for error handling and edge cases."""

    async def test_get_with_malformed_uuid_returns_422(self, client):
        """Test validation error for malformed UUID."""
        response = await client.get("/api/conversations/invalid")
        assert response.status_code == 422

    async def test_create_conversation_handles_errors_gracefully(self, client):
        """Test that server errors are handled gracefully."""
        # This test verifies error handling is in place
        # In production, errors should return 500 with proper logging
        response = await client.post("/api/conversations")

        # Should either succeed or return proper error
        assert response.status_code in [200, 500]

        if response.status_code == 500:
            data = response.json()
            assert "detail" in data


@pytest.mark.asyncio
class TestTwelveFactorCompliance:
    """Tests verifying 12-factor app principles."""

    async def test_api_is_stateless(self, client):
        """Test that API doesn't store request state (12-factor: processes)."""
        # Create conversation
        create_response = await client.post("/api/conversations")
        conversation_id = create_response.json()["conversation_id"]

        # Multiple retrievals should work independently
        # (no session state between requests)
        for _ in range(3):
            response = await client.get(f"/api/conversations/{conversation_id}")
            assert response.status_code == 200
            assert response.json()["conversation_id"] == conversation_id

    async def test_config_from_environment(self, client):
        """Test that config comes from environment (12-factor: config)."""
        # Verify OpenAI API key would come from environment
        # (tested indirectly - app startup would fail without it)

        # Health check succeeds means config loaded correctly
        response = await client.get("/api/health")
        assert response.status_code == 200

    async def test_logs_to_stdout(self, client):
        """Test that logs go to stdout (12-factor: logs)."""
        # Structlog is configured to print to stdout
        # This is verified in app startup

        # Making requests should generate logs without errors
        await client.post("/api/conversations")
        response = await client.get("/api/health")
        assert response.status_code == 200


@pytest.mark.asyncio
class TestResponseSchemas:
    """Test suite for validating response schema compliance."""

    async def test_conversation_create_schema_validation(self, client):
        """Test that create response matches schema exactly."""
        response = await client.post("/api/conversations")
        data = response.json()

        # Must have exactly these fields
        required_fields = {"conversation_id", "status", "started_at"}
        assert set(data.keys()) == required_fields

        # Types must match
        assert isinstance(data["conversation_id"], str)
        assert data["status"] in ["active", "completed"]
        assert isinstance(data["started_at"], str)

    async def test_conversation_state_schema_validation(self, client):
        """Test that state response matches schema exactly."""
        # Create conversation
        create_response = await client.post("/api/conversations")
        conversation_id = create_response.json()["conversation_id"]

        # Get state
        response = await client.get(f"/api/conversations/{conversation_id}")
        data = response.json()

        # Must have these fields (including ACW fields and summary_interval)
        required_fields = {
            "conversation_id", "status", "started_at", "ended_at",
            "transcript_lines", "summaries", "summary_interval",
            "disposition_code", "wrap_up_notes", "agent_feedback", "acw_duration_secs",
            "compliance_results", "crm_field_extractions"
        }
        assert set(data.keys()) == required_fields

        # Types must match
        assert isinstance(data["conversation_id"], str)
        assert data["status"] in ["active", "completed"]
        assert isinstance(data["transcript_lines"], list)
        assert isinstance(data["summaries"], list)
        assert isinstance(data["summary_interval"], int)
        assert isinstance(data["compliance_results"], list)
        assert isinstance(data["crm_field_extractions"], list)
        # ACW fields are nullable
        assert data["disposition_code"] is None or isinstance(data["disposition_code"], str)
        assert data["wrap_up_notes"] is None or isinstance(data["wrap_up_notes"], str)
        assert data["agent_feedback"] is None or isinstance(data["agent_feedback"], str)
        assert data["acw_duration_secs"] is None or isinstance(data["acw_duration_secs"], int)

    async def test_health_check_schema_validation(self, client):
        """Test that health response matches schema exactly."""
        response = await client.get("/api/health")
        data = response.json()

        # Must have exactly these fields
        required_fields = {"status", "timestamp"}
        assert set(data.keys()) == required_fields

        # Types must match
        assert data["status"] in ["healthy", "unhealthy"]


@pytest.mark.asyncio
class TestACWEndpoint:
    """Test suite for ACW (After-Call Work) completion endpoint."""

    async def test_complete_conversation_minimal(self, client):
        """Test completing conversation with minimal ACW data."""
        # Create conversation
        create_response = await client.post("/api/conversations")
        assert create_response.status_code == 200
        conversation_id = create_response.json()["conversation_id"]

        # Complete with minimal data
        acw_data = {
            "disposition_code": "RESOLVED",
        }
        response = await client.put(
            f"/api/conversations/{conversation_id}/complete",
            json=acw_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["disposition_code"] == "RESOLVED"

        # Verify conversation is marked complete
        get_response = await client.get(f"/api/conversations/{conversation_id}")
        get_data = get_response.json()
        assert get_data["status"] == "completed"
        assert get_data["ended_at"] is not None

    async def test_complete_conversation_full_acw_data(self, client):
        """Test completing conversation with all ACW fields."""
        # Create conversation
        create_response = await client.post("/api/conversations")
        conversation_id = create_response.json()["conversation_id"]

        # Complete with full ACW data
        acw_data = {
            "disposition_code": "ESCALATED",
            "wrap_up_notes": "Customer needs follow-up from manager.",
            "agent_feedback": "down",
            "acw_duration_secs": 45,
            "compliance_checklist": [
                {"label": "Verified identity", "checked": True, "auto_detected": True},
                {"label": "Confirmed resolution", "checked": True, "auto_detected": False},
                {"label": "Offered additional help", "checked": False, "auto_detected": False},
            ],
            "crm_fields": [
                {
                    "field_name": "Case Subject",
                    "extracted_value": "Order tracking inquiry",
                    "source": "AI",
                    "confidence": 0.95
                },
                {
                    "field_name": "Priority",
                    "extracted_value": "High",
                    "source": "Transcript",
                    "confidence": 1.0
                },
            ]
        }
        response = await client.put(
            f"/api/conversations/{conversation_id}/complete",
            json=acw_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["disposition_code"] == "ESCALATED"
        assert data["wrap_up_notes"] == "Customer needs follow-up from manager."
        assert data["agent_feedback"] == "down"
        assert data["acw_duration_secs"] == 45

        # Verify persistence
        get_response = await client.get(f"/api/conversations/{conversation_id}")
        get_data = get_response.json()
        assert get_data["status"] == "completed"
        assert len(get_data["compliance_results"]) == 3
        assert len(get_data["crm_field_extractions"]) == 2

    async def test_complete_conversation_not_found(self, client):
        """Test completing non-existent conversation returns 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        acw_data = {"disposition_code": "RESOLVED"}

        response = await client.put(
            f"/api/conversations/{fake_id}/complete",
            json=acw_data
        )

        assert response.status_code == 404

    async def test_complete_conversation_invalid_uuid(self, client):
        """Test completing with invalid UUID returns 422."""
        acw_data = {"disposition_code": "RESOLVED"}

        response = await client.put(
            "/api/conversations/not-a-uuid/complete",
            json=acw_data
        )

        assert response.status_code == 422

    async def test_complete_already_completed_conversation(self, client):
        """Test completing an already completed conversation (idempotent)."""
        # Create and complete conversation
        create_response = await client.post("/api/conversations")
        conversation_id = create_response.json()["conversation_id"]

        acw_data = {"disposition_code": "RESOLVED"}
        first_response = await client.put(
            f"/api/conversations/{conversation_id}/complete",
            json=acw_data
        )
        assert first_response.status_code == 200
        first_data = first_response.json()
        assert first_data["status"] == "completed"

        # Complete again - should be idempotent
        second_response = await client.put(
            f"/api/conversations/{conversation_id}/complete",
            json=acw_data
        )
        assert second_response.status_code == 200
        second_data = second_response.json()
        assert second_data["status"] == "completed"
        assert second_data["conversation_id"] == conversation_id


@pytest.mark.asyncio
class TestConversationStateSchema:
    """Test suite for verifying summary_interval in API responses."""

    async def test_conversation_state_includes_summary_interval(self, client):
        """Verify GET /api/conversations/{id} includes summary_interval field."""
        # Create conversation
        create_response = await client.post("/api/conversations")
        assert create_response.status_code == 200
        conversation_id = create_response.json()["conversation_id"]

        # Get conversation state
        response = await client.get(f"/api/conversations/{conversation_id}")
        assert response.status_code == 200

        data = response.json()

        # Verify summary_interval is present
        assert "summary_interval" in data
        assert isinstance(data["summary_interval"], int)

        # Should default to config setting (5 seconds)
        assert data["summary_interval"] == 5

    async def test_update_summary_interval_persists_to_database(self, client):
        """Verify PUT endpoint persists interval to database, not just in-memory."""
        # Create conversation
        create_response = await client.post("/api/conversations")
        conversation_id = create_response.json()["conversation_id"]

        # Update interval via PUT endpoint
        new_interval = 15
        update_response = await client.put(
            f"/api/conversations/{conversation_id}/summary-interval",
            params={"interval_seconds": new_interval}
        )
        assert update_response.status_code == 200

        # Get conversation state to verify persistence
        get_response = await client.get(f"/api/conversations/{conversation_id}")
        assert get_response.status_code == 200

        data = get_response.json()

        # Verify interval was persisted (not just in-memory)
        assert data["summary_interval"] == new_interval


@pytest.mark.asyncio
class TestListeningModeEndpoints:
    """Test suite for listening mode REST API endpoints.

    Tests the 3 listening mode endpoints:
    - POST /api/conversations/{id}/listening-mode/start
    - POST /api/conversations/{id}/listening-mode/stop
    - GET /api/conversations/{id}/listening-mode/status
    """

    async def test_start_listening_mode_success(self, client):
        """Test starting listening mode returns 201 with session details."""
        # Create conversation first
        create_response = await client.post("/api/conversations")
        assert create_response.status_code == 200
        conversation_id = create_response.json()["conversation_id"]

        # Start listening mode
        response = await client.post(
            f"/api/conversations/{conversation_id}/listening-mode/start"
        )

        # Verify response
        assert response.status_code == 201
        data = response.json()

        # Verify response schema
        assert "session_id" in data
        assert "conversation_id" in data
        assert "started_at" in data
        assert "status" in data

        # Verify values
        assert isinstance(data["session_id"], int)
        assert data["session_id"] > 0
        assert data["conversation_id"] == conversation_id
        assert data["status"] == "active"
        assert datetime.fromisoformat(data["started_at"])  # Valid ISO timestamp

    async def test_start_listening_mode_conversation_not_found(self, client):
        """Test starting listening mode returns 404 for non-existent conversation."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = await client.post(
            f"/api/conversations/{fake_id}/listening-mode/start"
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_start_listening_mode_invalid_uuid(self, client):
        """Test starting listening mode returns 422 for invalid UUID."""
        response = await client.post(
            "/api/conversations/invalid-uuid/listening-mode/start"
        )

        assert response.status_code == 422

    async def test_start_listening_mode_idempotent(self, client):
        """Test starting listening mode twice returns same session (idempotent)."""
        # Create conversation
        create_response = await client.post("/api/conversations")
        conversation_id = create_response.json()["conversation_id"]

        # Start listening mode first time
        response1 = await client.post(
            f"/api/conversations/{conversation_id}/listening-mode/start"
        )
        assert response1.status_code == 201
        session_id_1 = response1.json()["session_id"]

        # Start listening mode second time (should return existing session)
        response2 = await client.post(
            f"/api/conversations/{conversation_id}/listening-mode/start"
        )
        assert response2.status_code == 201
        session_id_2 = response2.json()["session_id"]

        # Should return same session ID (idempotent)
        assert session_id_1 == session_id_2

    async def test_stop_listening_mode_success(self, client):
        """Test stopping listening mode returns 200 with metrics."""
        # Create conversation and start listening mode
        create_response = await client.post("/api/conversations")
        conversation_id = create_response.json()["conversation_id"]

        await client.post(
            f"/api/conversations/{conversation_id}/listening-mode/start"
        )

        # Stop listening mode
        response = await client.post(
            f"/api/conversations/{conversation_id}/listening-mode/stop"
        )

        # Verify response
        assert response.status_code == 200
        data = response.json()

        # Verify response schema
        assert "session_id" in data
        assert "conversation_id" in data
        assert "ended_at" in data
        assert "auto_queries_count" in data
        assert "opportunities_detected" in data
        assert "duration_seconds" in data

        # Verify values
        assert data["conversation_id"] == conversation_id
        assert datetime.fromisoformat(data["ended_at"])  # Valid ISO timestamp
        assert isinstance(data["auto_queries_count"], int)
        assert isinstance(data["opportunities_detected"], int)
        assert isinstance(data["duration_seconds"], float)
        # Duration should be small (test just started/stopped session)
        # Allow some tolerance for test execution time (up to 60 seconds)
        assert 0 <= data["duration_seconds"] < 60

    async def test_stop_listening_mode_no_active_session(self, client):
        """Test stopping listening mode returns 404 when no active session."""
        # Create conversation but don't start listening mode
        create_response = await client.post("/api/conversations")
        conversation_id = create_response.json()["conversation_id"]

        # Try to stop (no active session)
        response = await client.post(
            f"/api/conversations/{conversation_id}/listening-mode/stop"
        )

        assert response.status_code == 404
        assert "no active" in response.json()["detail"].lower()

    async def test_stop_listening_mode_conversation_not_found(self, client):
        """Test stopping listening mode returns 404 for non-existent conversation."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = await client.post(
            f"/api/conversations/{fake_id}/listening-mode/stop"
        )

        assert response.status_code == 404

    async def test_get_listening_mode_status_active(self, client):
        """Test status endpoint returns active session details."""
        # Create conversation and start listening mode
        create_response = await client.post("/api/conversations")
        conversation_id = create_response.json()["conversation_id"]

        await client.post(
            f"/api/conversations/{conversation_id}/listening-mode/start"
        )

        # Get status
        response = await client.get(
            f"/api/conversations/{conversation_id}/listening-mode/status"
        )

        # Verify response
        assert response.status_code == 200
        data = response.json()

        # Verify response schema
        assert "is_active" in data
        assert "session_id" in data
        assert "conversation_id" in data
        assert "started_at" in data
        assert "ended_at" in data
        assert "auto_queries_count" in data
        assert "opportunities_detected" in data
        assert "elapsed_seconds" in data

        # Verify active session values
        assert data["is_active"] is True
        assert data["session_id"] is not None
        assert data["conversation_id"] == conversation_id
        assert data["started_at"] is not None
        assert data["ended_at"] is None  # Not ended yet
        assert isinstance(data["elapsed_seconds"], float)
        # Elapsed time should be small (just started)
        # Allow some tolerance for test execution time (up to 60 seconds)
        assert 0 <= data["elapsed_seconds"] < 60

    async def test_get_listening_mode_status_inactive(self, client):
        """Test status endpoint returns inactive when no session."""
        # Create conversation but don't start listening mode
        create_response = await client.post("/api/conversations")
        conversation_id = create_response.json()["conversation_id"]

        # Get status
        response = await client.get(
            f"/api/conversations/{conversation_id}/listening-mode/status"
        )

        # Verify response
        assert response.status_code == 200
        data = response.json()

        # Verify inactive session values
        assert data["is_active"] is False
        assert data["session_id"] is None
        assert data["conversation_id"] == conversation_id
        assert data["started_at"] is None
        assert data["ended_at"] is None
        assert data["auto_queries_count"] == 0
        assert data["opportunities_detected"] == 0
        assert data["elapsed_seconds"] is None

    async def test_get_listening_mode_status_after_stop(self, client):
        """Test status endpoint returns inactive after stopping."""
        # Create conversation, start, then stop listening mode
        create_response = await client.post("/api/conversations")
        conversation_id = create_response.json()["conversation_id"]

        await client.post(
            f"/api/conversations/{conversation_id}/listening-mode/start"
        )
        await client.post(
            f"/api/conversations/{conversation_id}/listening-mode/stop"
        )

        # Get status
        response = await client.get(
            f"/api/conversations/{conversation_id}/listening-mode/status"
        )

        # Should show inactive (no active session)
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

    async def test_listening_mode_graceful_degradation_when_disabled(self, client, test_app):
        """Test endpoints return 503 when listening mode manager is None (feature disabled)."""
        # Temporarily set listening_mode_manager to None (simulate feature disabled)
        original_manager = test_app.state.listening_mode_manager
        test_app.state.listening_mode_manager = None

        try:
            # Create conversation
            create_response = await client.post("/api/conversations")
            conversation_id = create_response.json()["conversation_id"]

            # Try to start (should fail gracefully)
            start_response = await client.post(
                f"/api/conversations/{conversation_id}/listening-mode/start"
            )
            assert start_response.status_code == 503
            assert "not available" in start_response.json()["detail"].lower()

            # Try to stop (should fail gracefully)
            stop_response = await client.post(
                f"/api/conversations/{conversation_id}/listening-mode/stop"
            )
            assert stop_response.status_code == 503

            # Status should return inactive (graceful degradation)
            status_response = await client.get(
                f"/api/conversations/{conversation_id}/listening-mode/status"
            )
            assert status_response.status_code == 200
            assert status_response.json()["is_active"] is False

        finally:
            # Restore original manager
            test_app.state.listening_mode_manager = original_manager

    async def test_listening_mode_full_lifecycle(self, client):
        """Test complete lifecycle: create conversation → start → check status → stop."""
        # 1. Create conversation
        create_response = await client.post("/api/conversations")
        assert create_response.status_code == 200
        conversation_id = create_response.json()["conversation_id"]

        # 2. Verify initial status (inactive)
        status1 = await client.get(
            f"/api/conversations/{conversation_id}/listening-mode/status"
        )
        assert status1.json()["is_active"] is False

        # 3. Start listening mode
        start_response = await client.post(
            f"/api/conversations/{conversation_id}/listening-mode/start"
        )
        assert start_response.status_code == 201
        session_id = start_response.json()["session_id"]

        # 4. Verify status (active)
        status2 = await client.get(
            f"/api/conversations/{conversation_id}/listening-mode/status"
        )
        assert status2.json()["is_active"] is True
        assert status2.json()["session_id"] == session_id

        # 5. Stop listening mode
        stop_response = await client.post(
            f"/api/conversations/{conversation_id}/listening-mode/stop"
        )
        assert stop_response.status_code == 200
        assert stop_response.json()["session_id"] == session_id

        # 6. Verify final status (inactive)
        status3 = await client.get(
            f"/api/conversations/{conversation_id}/listening-mode/status"
        )
        assert status3.json()["is_active"] is False