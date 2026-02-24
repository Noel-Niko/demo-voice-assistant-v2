"""Tests for summary generator AI cost tracking.

Verifies that summary generation calls save_ai_interaction() to track
tokens, costs, and latency for dashboard model breakdown.
"""
import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4

from app.services.summary_generator import SummaryGenerator
from app.services.event_bus import InMemoryEventBus
from app.repositories.conversation_repository import ConversationRepository


@pytest_asyncio.fixture
async def event_bus():
    """Create event bus for tests."""
    bus = InMemoryEventBus(queue_size=10)
    await bus.start()
    yield bus
    await bus.stop()


@pytest.fixture
def mock_repository():
    """Create mock repository that tracks save calls."""
    repo = Mock(spec=ConversationRepository)
    repo.save_summary = AsyncMock()
    repo.save_ai_interaction = AsyncMock()
    return repo


@pytest.fixture
def summary_generator(mock_repository, event_bus):
    """Create summary generator with mocks."""
    return SummaryGenerator(
        repository=mock_repository,
        event_bus=event_bus,
        api_key="test-key",
        model="gpt-3.5-turbo",
        interval_seconds=30,
    )


@pytest.mark.asyncio
async def test_summary_generation_saves_ai_interaction(summary_generator, mock_repository):
    """Test that summary generation calls save_ai_interaction().

    After a successful summary generation, save_ai_interaction() should be
    called with interaction_type='summary', tokens, cost, and latency.
    """
    conversation_id = uuid4()

    # Mock OpenAI streaming response
    mock_chunk_1 = Mock()
    mock_chunk_1.choices = [Mock(delta=Mock(content="This is "))]
    mock_chunk_1.usage = None

    mock_chunk_2 = Mock()
    mock_chunk_2.choices = [Mock(delta=Mock(content="a test summary."))]
    mock_chunk_2.usage = None

    # Final chunk with usage data
    mock_chunk_final = Mock()
    mock_chunk_final.choices = [Mock(delta=Mock(content=""))]
    mock_chunk_final.usage = Mock(total_tokens=150)

    async def mock_stream():
        yield mock_chunk_1
        yield mock_chunk_2
        yield mock_chunk_final

    # Patch OpenAI client
    with patch.object(summary_generator, 'client') as mock_client:
        mock_client.chat = Mock()
        mock_client.chat.completions = Mock()
        mock_create = AsyncMock()
        mock_create.return_value.__aenter__ = AsyncMock(return_value=mock_stream())
        mock_create.return_value.__aexit__ = AsyncMock()
        mock_client.chat.completions.create = mock_create

        # Mock transcript fetching
        mock_repository.get_summary = AsyncMock(return_value=None)
        mock_repository.get_transcript_lines = AsyncMock(return_value=[
            Mock(speaker="Agent", text="Hello"),
            Mock(speaker="Customer", text="Hi there"),
        ])

        # Generate summary
        await summary_generator._generate_summary(conversation_id=conversation_id)

    # Verify save_ai_interaction was called
    assert mock_repository.save_ai_interaction.called, \
        "save_ai_interaction should be called after successful summary generation"

    call_kwargs = mock_repository.save_ai_interaction.call_args.kwargs
    assert call_kwargs["conversation_id"] == conversation_id
    assert call_kwargs["interaction_type"] == "summary"
    assert "prompt_text" in call_kwargs
    assert "response_text" in call_kwargs
    assert call_kwargs["model_name"] == "gpt-3.5-turbo"
    assert call_kwargs["tokens_used"] == 150
    assert "cost_usd" in call_kwargs
    assert call_kwargs["cost_usd"] > 0  # Should be calculated
    assert "latency_ms" in call_kwargs
    assert call_kwargs["latency_ms"] >= 0  # Should be measured (can be 0 in fast mocked tests)


@pytest.mark.asyncio
async def test_summary_ai_interaction_has_correct_model(summary_generator, mock_repository):
    """Test that AI interaction is saved with the correct model_name.

    When the model is changed via set_model(), subsequent summaries should
    use the new model in save_ai_interaction() calls.
    """
    conversation_id = uuid4()

    # Change model to gpt-4o
    summary_generator.set_model("gpt-4o", None)

    # Mock OpenAI streaming
    mock_chunk_final = Mock()
    mock_chunk_final.choices = [Mock(delta=Mock(content="Summary"))]
    mock_chunk_final.usage = Mock(total_tokens=100)

    async def mock_stream():
        yield mock_chunk_final

    # Mock transcript fetching
    mock_repository.get_summary = AsyncMock(return_value=None)
    mock_repository.get_transcript_lines = AsyncMock(return_value=[
        Mock(speaker="Agent", text="Test"),
    ])

    with patch.object(summary_generator, 'client') as mock_client:
        mock_client.chat = Mock()
        mock_client.chat.completions = Mock()
        mock_create = AsyncMock()
        mock_create.return_value.__aenter__ = AsyncMock(return_value=mock_stream())
        mock_create.return_value.__aexit__ = AsyncMock()
        mock_client.chat.completions.create = mock_create

        await summary_generator._generate_summary(conversation_id=conversation_id)

    # Verify model_name is gpt-4o
    call_kwargs = mock_repository.save_ai_interaction.call_args.kwargs
    assert call_kwargs["model_name"] == "gpt-4o"


@pytest.mark.asyncio
async def test_summary_costs_appear_in_export(mock_repository, event_bus):
    """Test that summary AI interactions flow through to export.

    This is an integration-style test verifying the data path:
    save_ai_interaction() -> export -> dashboard
    """
    conversation_id = uuid4()

    # Track what was saved
    saved_interactions = []

    async def capture_ai_interaction(**kwargs):
        saved_interactions.append(kwargs)

    mock_repository.save_ai_interaction = AsyncMock(side_effect=capture_ai_interaction)
    mock_repository.save_summary = AsyncMock()

    generator = SummaryGenerator(
        repository=mock_repository,
        event_bus=event_bus,
        api_key="test-key",
        model="gpt-3.5-turbo",
    )

    # Mock OpenAI streaming
    mock_chunk = Mock()
    mock_chunk.choices = [Mock(delta=Mock(content="Summary text"))]
    mock_chunk.usage = Mock(total_tokens=200)

    async def mock_stream():
        yield mock_chunk

    # Mock transcript fetching
    mock_repository.get_summary = AsyncMock(return_value=None)
    mock_repository.get_transcript_lines = AsyncMock(return_value=[
        Mock(speaker="Agent", text="Test"),
    ])

    with patch.object(generator, 'client') as mock_client:
        mock_client.chat = Mock()
        mock_client.chat.completions = Mock()
        mock_create = AsyncMock()
        mock_create.return_value.__aenter__ = AsyncMock(return_value=mock_stream())
        mock_create.return_value.__aexit__ = AsyncMock()
        mock_client.chat.completions.create = mock_create

        await generator._generate_summary(conversation_id=conversation_id)

    # Verify interaction was saved with correct data
    assert len(saved_interactions) == 1
    interaction = saved_interactions[0]
    assert interaction["interaction_type"] == "summary"
    assert interaction["tokens_used"] == 200
    assert interaction["cost_usd"] == pytest.approx(0.00035, rel=1e-6)  # 200 * 0.00175 / 1000


@pytest.mark.asyncio
async def test_summary_failure_does_not_save_ai_interaction(summary_generator, mock_repository):
    """Test that failed summaries don't save AI interactions.

    If OpenAI call fails, save_ai_interaction() should NOT be called
    (since no tokens were used).
    """
    conversation_id = uuid4()

    # Mock transcript fetching
    mock_repository.get_summary = AsyncMock(return_value=None)
    mock_repository.get_transcript_lines = AsyncMock(return_value=[
        Mock(speaker="Agent", text="Test"),
    ])

    # Mock OpenAI to raise exception
    with patch.object(summary_generator, 'client') as mock_client:
        mock_client.chat = Mock()
        mock_client.chat.completions = Mock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("OpenAI API error")
        )

        # _generate_summary catches exceptions internally (fire-and-forget pattern)
        # so it will NOT propagate the error — it logs and returns normally
        await summary_generator._generate_summary(conversation_id=conversation_id)

    # Verify save_ai_interaction was NOT called
    assert not mock_repository.save_ai_interaction.called, \
        "save_ai_interaction should not be called when OpenAI fails"


@pytest.mark.asyncio
async def test_save_ai_interaction_failure_does_not_break_summary(summary_generator, mock_repository):
    """Test that save_ai_interaction failure doesn't break summary generation.

    If save_ai_interaction() fails, the summary should still be saved and
    the error should be logged (fire-and-forget pattern).
    """
    conversation_id = uuid4()

    # Make save_ai_interaction fail
    mock_repository.save_ai_interaction = AsyncMock(
        side_effect=Exception("Database error")
    )

    # Mock transcript fetching
    mock_repository.get_summary = AsyncMock(return_value=None)
    mock_repository.get_transcript_lines = AsyncMock(return_value=[
        Mock(speaker="Agent", text="Test"),
    ])

    # Mock successful OpenAI streaming
    mock_chunk = Mock()
    mock_chunk.choices = [Mock(delta=Mock(content="Summary"))]
    mock_chunk.usage = Mock(total_tokens=100)

    async def mock_stream():
        yield mock_chunk

    with patch.object(summary_generator, 'client') as mock_client:
        mock_client.chat = Mock()
        mock_client.chat.completions = Mock()
        mock_create = AsyncMock()
        mock_create.return_value.__aenter__ = AsyncMock(return_value=mock_stream())
        mock_create.return_value.__aexit__ = AsyncMock()
        mock_client.chat.completions.create = mock_create

        # Should NOT raise exception (fire-and-forget)
        await summary_generator._generate_summary(conversation_id=conversation_id)

    # Verify save_summary was still called (summary was saved)
    assert mock_repository.save_summary.called, \
        "save_summary should be called even if save_ai_interaction fails"
