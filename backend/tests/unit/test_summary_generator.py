"""Unit tests for SummaryGenerator.

Following TDD: Tests written FIRST, then implementation.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from uuid import UUID
from datetime import datetime

from app.services.summary_generator import SummaryGenerator
from app.models.domain import Summary


@pytest.mark.asyncio
class TestSummaryGenerator:
    """Test suite for SummaryGenerator."""

    async def test_lazy_client_initialization(self):
        """Test that OpenAI client is lazily initialized."""
        repository = Mock()
        event_bus = Mock()

        generator = SummaryGenerator(repository, event_bus, api_key="test_key")

        # Client should be None initially
        assert generator.client is None

        # Ensure client is created on first use
        client = generator._ensure_client()
        assert client is not None
        assert generator.client is not None

    async def test_subscribes_to_transcript_word_final_events(self):
        """Test that generator subscribes to transcript.word.final events."""
        repository = Mock()
        event_bus = Mock()
        event_bus.subscribe = Mock()

        generator = SummaryGenerator(repository, event_bus, api_key="test_key")

        # Should have subscribed to transcript.word.final
        event_bus.subscribe.assert_any_call("transcript.word.final", generator._on_transcript_word_final)

    async def test_on_transcript_word_final_starts_periodic_timer(self):
        """Test that first transcript.word.final event starts periodic summarization."""
        repository = Mock()
        event_bus = Mock()
        event_bus.publish = AsyncMock()

        generator = SummaryGenerator(
            repository, event_bus, api_key="test_key", interval_seconds=0.1
        )

        conversation_id = UUID("12345678-1234-1234-1234-123456789012")
        from app.services.event_bus import Event

        event = Event.create(
            event_type="transcript.word.final",
            source="test",
            data={"line_id": "test-seq-1", "text": "Hello"},
            conversation_id=str(conversation_id),
        )

        await generator._on_transcript_word_final(event)

        # Should have created a task
        assert conversation_id in generator._active_tasks

        # Clean up
        await generator._stop_summarization(conversation_id)

    async def test_generate_summary_with_no_previous_summary(self):
        """Test generating first summary with no previous context."""
        repository = Mock()
        repository.get_recent_transcript_lines = AsyncMock(return_value=[
            Mock(speaker="agent", text="Hello"),
            Mock(speaker="customer", text="Hi"),
        ])
        repository.get_latest_summary = AsyncMock(return_value=None)
        repository.save_summary = AsyncMock()
        repository.get_summary_count = AsyncMock(return_value=0)

        event_bus = Mock()
        event_bus.publish = AsyncMock()

        # Mock OpenAI streaming response
        mock_chunks = [
            Mock(choices=[Mock(delta=Mock(content="Customer "))]),
            Mock(choices=[Mock(delta=Mock(content="called "))]),
            Mock(choices=[Mock(delta=Mock(content="for help."))]),
        ]

        with patch("app.services.summary_generator.AsyncOpenAI") as mock_openai_class:
            mock_client = AsyncMock()
            mock_stream = AsyncMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)

            async def async_iter():
                for chunk in mock_chunks:
                    yield chunk

            mock_stream.__aiter__ = lambda self: async_iter()

            # create() should return an awaitable that returns the stream
            async def mock_create(*args, **kwargs):
                return mock_stream

            mock_client.chat.completions.create = mock_create
            mock_openai_class.return_value = mock_client

            generator = SummaryGenerator(repository, event_bus, api_key="test_key")
            generator.client = mock_client

            conversation_id = UUID("12345678-1234-1234-1234-123456789012")
            await generator._generate_summary(conversation_id)

            # Should have published summary.start, tokens, and complete
            event_types = [call[0][0].event_type for call in event_bus.publish.call_args_list]
            assert "summary.start" in event_types
            assert "summary.token" in event_types
            assert "summary.complete" in event_types

            # Should have saved summary
            repository.save_summary.assert_called_once()

    async def test_generate_summary_with_previous_context(self):
        """Test generating rolling summary with previous context."""
        repository = Mock()
        repository.get_recent_transcript_lines = AsyncMock(return_value=[
            Mock(speaker="agent", text="Can I help with anything else?"),
        ])
        repository.get_latest_summary = AsyncMock(return_value=Mock(
            summary_text="Customer called about order status."
        ))
        repository.save_summary = AsyncMock()
        repository.get_summary_count = AsyncMock(return_value=1)

        event_bus = Mock()
        event_bus.publish = AsyncMock()

        mock_chunks = [Mock(choices=[Mock(delta=Mock(content="Updated summary."))])]

        with patch("app.services.summary_generator.AsyncOpenAI") as mock_openai_class:
            mock_client = AsyncMock()
            mock_stream = AsyncMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)

            async def async_iter():
                for chunk in mock_chunks:
                    yield chunk

            mock_stream.__aiter__ = lambda self: async_iter()

            # create() should return an awaitable that returns the stream
            async def mock_create(*args, **kwargs):
                return mock_stream

            mock_client.chat.completions.create = mock_create
            mock_openai_class.return_value = mock_client

            generator = SummaryGenerator(repository, event_bus, api_key="test_key")
            generator.client = mock_client

            conversation_id = UUID("12345678-1234-1234-1234-123456789012")
            await generator._generate_summary(conversation_id)

            # Should have used previous summary in context
            repository.get_latest_summary.assert_called_once()
            repository.save_summary.assert_called_once()

    async def test_stream_tokens_publishes_each_token(self):
        """Test that each token is published as separate event."""
        repository = Mock()
        repository.get_recent_transcript_lines = AsyncMock(return_value=[
            Mock(speaker="agent", text="Hello"),
        ])
        repository.get_latest_summary = AsyncMock(return_value=None)
        repository.save_summary = AsyncMock()
        repository.get_summary_count = AsyncMock(return_value=0)

        event_bus = Mock()
        event_bus.publish = AsyncMock()

        mock_chunks = [
            Mock(choices=[Mock(delta=Mock(content="Token1"))]),
            Mock(choices=[Mock(delta=Mock(content="Token2"))]),
            Mock(choices=[Mock(delta=Mock(content="Token3"))]),
        ]

        with patch("app.services.summary_generator.AsyncOpenAI") as mock_openai_class:
            mock_client = AsyncMock()
            mock_stream = AsyncMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)

            async def async_iter():
                for chunk in mock_chunks:
                    yield chunk

            mock_stream.__aiter__ = lambda self: async_iter()

            # create() should return an awaitable that returns the stream
            async def mock_create(*args, **kwargs):
                return mock_stream

            mock_client.chat.completions.create = mock_create
            mock_openai_class.return_value = mock_client

            generator = SummaryGenerator(repository, event_bus, api_key="test_key")
            generator.client = mock_client

            conversation_id = UUID("12345678-1234-1234-1234-123456789012")
            await generator._generate_summary(conversation_id)

            # Should have published 3 summary.token events
            token_events = [
                call for call in event_bus.publish.call_args_list
                if call[0][0].event_type == "summary.token"
            ]
            assert len(token_events) == 3

    async def test_stops_on_streaming_complete_event(self):
        """Test that summarization stops when streaming completes."""
        repository = Mock()
        event_bus = Mock()
        event_bus.subscribe = Mock()

        generator = SummaryGenerator(repository, event_bus, api_key="test_key")

        conversation_id = UUID("12345678-1234-1234-1234-123456789012")

        # Create a real asyncio task that can be cancelled
        async def dummy_task():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                pass

        generator._active_tasks[conversation_id] = asyncio.create_task(dummy_task())

        from app.services.event_bus import Event
        event = Event.create(
            event_type="streaming.complete",
            source="test",
            data={},
            conversation_id=str(conversation_id),
        )

        await generator._on_streaming_complete(event)

        # Task should be removed
        assert conversation_id not in generator._active_tasks

    # ===== Model Selector Tests =====

    async def test_set_model_updates_model(self):
        """Test that set_model changes the model used for generation."""
        repository = Mock()
        event_bus = Mock()

        generator = SummaryGenerator(repository, event_bus, api_key="test_key")
        assert generator.model == "gpt-3.5-turbo"  # default

        generator.set_model("gpt-4o")
        assert generator.model == "gpt-4o"

    async def test_set_model_with_reasoning_effort(self):
        """Test that set_model stores reasoning_effort for API kwargs."""
        repository = Mock()
        event_bus = Mock()

        generator = SummaryGenerator(repository, event_bus, api_key="test_key")

        generator.set_model("gpt-5", reasoning_effort="low")
        assert generator.model == "gpt-5"
        assert generator._reasoning_effort == "low"

    async def test_set_model_clears_reasoning_effort_when_none(self):
        """Test that set_model clears reasoning_effort when not provided."""
        repository = Mock()
        event_bus = Mock()

        generator = SummaryGenerator(repository, event_bus, api_key="test_key")

        # Set reasoning first
        generator.set_model("gpt-5", reasoning_effort="low")
        assert generator._reasoning_effort == "low"

        # Switch to model without reasoning
        generator.set_model("gpt-4o")
        assert generator._reasoning_effort is None

    # ===== Bug Fix Tests =====

    async def test_handles_openai_usage_chunk_with_empty_choices(self):
        """Test that generator handles OpenAI usage chunk with empty choices array.

        Bug: When stream_options={"include_usage": True}, OpenAI sends a final chunk
        with choices=[] and usage data, causing IndexError on chunk.choices[0].

        This test verifies the fix handles empty choices gracefully.
        """
        repository = Mock()
        repository.get_recent_transcript_lines = AsyncMock(return_value=[
            Mock(speaker="agent", text="Hello"),
        ])
        repository.get_latest_summary = AsyncMock(return_value=None)
        repository.save_summary = AsyncMock()
        repository.get_summary_count = AsyncMock(return_value=0)
        repository.save_ai_interaction = AsyncMock()

        event_bus = Mock()
        event_bus.publish = AsyncMock()

        # Mock OpenAI streaming response with usage chunk at the end
        mock_chunks = [
            Mock(choices=[Mock(delta=Mock(content="Summary "))], usage=None),
            Mock(choices=[Mock(delta=Mock(content="text."))], usage=None),
            # This is the critical chunk: empty choices with usage data
            Mock(choices=[], usage=Mock(total_tokens=50)),
        ]

        with patch("app.services.summary_generator.AsyncOpenAI") as mock_openai_class:
            mock_client = AsyncMock()
            mock_stream = AsyncMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)

            async def async_iter():
                for chunk in mock_chunks:
                    yield chunk

            mock_stream.__aiter__ = lambda self: async_iter()

            async def mock_create(*args, **kwargs):
                return mock_stream

            mock_client.chat.completions.create = mock_create
            mock_openai_class.return_value = mock_client

            generator = SummaryGenerator(repository, event_bus, api_key="test_key")
            generator.client = mock_client

            conversation_id = UUID("12345678-1234-1234-1234-123456789012")

            # This should NOT raise IndexError
            await generator._generate_summary(conversation_id)

            # Verify summary.complete event was published (proves we didn't crash)
            event_types = [call[0][0].event_type for call in event_bus.publish.call_args_list]
            assert "summary.complete" in event_types, "summary.complete event should be published"

            # Verify summary was saved
            repository.save_summary.assert_called_once()

            # Verify we published exactly 2 token events (not 3, since last chunk has no content)
            token_events = [
                call for call in event_bus.publish.call_args_list
                if call[0][0].event_type == "summary.token"
            ]
            assert len(token_events) == 2

    async def test_periodic_loop_continues_after_generation_error(self):
        """Test that periodic loop continues generating summaries after an error.

        Bug: When _generate_summary raises an exception, it propagates to _periodic_summarize
        and kills the entire periodic loop permanently.

        This test verifies that after the fix:
        1. First summary generation fails with an exception
        2. Exception is logged but loop continues
        3. Second summary generation succeeds
        """
        repository = Mock()
        event_bus = Mock()
        event_bus.publish = AsyncMock()

        # Set interval to 2 seconds (loop sleeps 1 second per iteration)
        generator = SummaryGenerator(
            repository, event_bus, api_key="test_key", interval_seconds=2
        )

        conversation_id = UUID("12345678-1234-1234-1234-123456789012")

        # Track how many times _generate_summary is called
        call_count = 0
        original_generate = generator._generate_summary

        async def mock_generate(conv_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call fails
                raise ValueError("Simulated API error")
            else:
                # Subsequent calls succeed (no-op)
                pass

        generator._generate_summary = mock_generate

        # Start periodic summarization
        from app.services.event_bus import Event
        event = Event.create(
            event_type="transcript.word.final",
            source="test",
            data={"line_id": "test-seq-1", "text": "Hello"},
            conversation_id=str(conversation_id),
        )
        await generator._on_transcript_word_final(event)

        # Wait for 5 seconds (enough for 2 complete intervals of 2 seconds each)
        await asyncio.sleep(5.5)

        # Stop the task
        await generator._stop_summarization(conversation_id)

        # Verify _generate_summary was called at least twice
        # This proves the loop continued after the first error
        assert call_count >= 2, f"Expected at least 2 calls, got {call_count}. Loop died after first error."

    async def test_model_switch_during_generation_uses_captured_config(self):
        """Test that model changes mid-operation don't affect in-flight API calls.

        Bug: When user switches models during summary generation (e.g., GPT-3.5 → GPT-5),
        the API call reads self.model and self._reasoning_effort at different times,
        causing parameter mismatches (e.g., sending temperature to o1 models).

        This test verifies that after the fix:
        1. Summary generation starts with GPT-3.5
        2. Model switches to GPT-5 mid-operation
        3. API call uses the originally captured GPT-3.5 config (not GPT-5)
        """
        repository = Mock()
        repository.get_recent_transcript_lines = AsyncMock(return_value=[
            Mock(speaker="agent", text="Hello"),
        ])
        repository.get_latest_summary = AsyncMock(return_value=None)
        repository.save_summary = AsyncMock()
        repository.get_summary_count = AsyncMock(return_value=0)
        repository.save_ai_interaction = AsyncMock()

        event_bus = Mock()
        event_bus.publish = AsyncMock()

        # Track what kwargs were passed to OpenAI API
        captured_api_kwargs = {}

        # Mock OpenAI streaming response
        mock_chunks = [
            Mock(choices=[Mock(delta=Mock(content="Summary"))], usage=None),
            Mock(choices=[], usage=Mock(total_tokens=20)),
        ]

        with patch("app.services.summary_generator.AsyncOpenAI") as mock_openai_class:
            mock_client = AsyncMock()
            mock_stream = AsyncMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)

            async def async_iter():
                for chunk in mock_chunks:
                    yield chunk

            mock_stream.__aiter__ = lambda self: async_iter()

            async def mock_create(*args, **kwargs):
                # Capture kwargs for verification
                captured_api_kwargs.update(kwargs)
                return mock_stream

            mock_client.chat.completions.create = mock_create
            mock_openai_class.return_value = mock_client

            # Initialize with GPT-3.5
            generator = SummaryGenerator(repository, event_bus, api_key="test_key")
            generator.client = mock_client
            generator.model = "gpt-3.5-turbo"
            generator._reasoning_effort = None

            conversation_id = UUID("12345678-1234-1234-1234-123456789012")

            # Monkey-patch _generate_summary to switch model mid-operation
            original_get_recent = repository.get_recent_transcript_lines

            async def get_recent_with_model_switch(*args, **kwargs):
                # Switch model to GPT-5 DURING the operation
                generator.model = "gpt-5"
                generator._reasoning_effort = "low"
                return await original_get_recent(*args, **kwargs)

            repository.get_recent_transcript_lines = get_recent_with_model_switch

            # Generate summary
            await generator._generate_summary(conversation_id)

            # Verify the API call used GPT-3.5 config (captured at start), not GPT-5
            assert captured_api_kwargs["model"] == "gpt-3.5-turbo", \
                "API call should use originally captured model (GPT-3.5), not switched model (GPT-5)"
            assert "temperature" in captured_api_kwargs, \
                "GPT-3.5 should use temperature parameter"
            assert "reasoning_effort" not in captured_api_kwargs, \
                "GPT-3.5 should NOT have reasoning_effort parameter"
            assert "max_tokens" in captured_api_kwargs, \
                "GPT-3.5 should use max_tokens (not max_completion_tokens)"

            # Verify the logged model name also matches the captured config
            save_ai_call = repository.save_ai_interaction.call_args
            assert save_ai_call[1]["model_name"] == "gpt-3.5-turbo", \
                "Logged model should match captured config"

    # ===== Reasoning Model Token Budget Tests =====

    async def test_build_api_kwargs_increases_tokens_for_reasoning_models(self):
        """Test that _build_api_kwargs multiplies max_completion_tokens for reasoning models.

        Bug: When GPT-5 or o1 models are used, max_completion_tokens includes BOTH
        reasoning tokens AND output tokens. With max_completion_tokens=500, the model
        exhausts its entire budget on internal reasoning, producing empty output.
        Logs confirm: summary_text: "" for versions 2 and 3.

        Fix: Multiply base_max_tokens by REASONING_TOKEN_MULTIPLIER for reasoning models.
        """
        repository = Mock()
        event_bus = Mock()

        generator = SummaryGenerator(repository, event_bus, api_key="test_key")

        # GPT-5 with base_max_tokens=500 should get a multiplied budget
        kwargs = generator._build_api_kwargs(
            base_temp=0.3,
            base_max_tokens=500,
            model="gpt-5",
            reasoning_effort="low",
        )

        assert "max_completion_tokens" in kwargs, \
            "GPT-5 should use max_completion_tokens"
        assert kwargs["max_completion_tokens"] > 500, (
            f"GPT-5 max_completion_tokens should be > 500 (base) to account for "
            f"reasoning token overhead, got {kwargs['max_completion_tokens']}"
        )
        # Should be approximately 4x the base
        assert kwargs["max_completion_tokens"] >= 2000, (
            f"GPT-5 needs ~4x base tokens for reasoning overhead, "
            f"got {kwargs['max_completion_tokens']}"
        )

    async def test_build_api_kwargs_unchanged_for_non_reasoning_models(self):
        """Test that _build_api_kwargs does NOT multiply tokens for standard models."""
        repository = Mock()
        event_bus = Mock()

        generator = SummaryGenerator(repository, event_bus, api_key="test_key")

        kwargs = generator._build_api_kwargs(
            base_temp=0.3,
            base_max_tokens=500,
            model="gpt-3.5-turbo",
            reasoning_effort=None,
        )

        assert "max_tokens" in kwargs
        assert kwargs["max_tokens"] == 500, \
            "Non-reasoning models should use base_max_tokens unmodified"

    async def test_build_api_kwargs_multiplies_for_o1_models(self):
        """Test that o1-preview and o1-mini also get multiplied token budgets."""
        repository = Mock()
        event_bus = Mock()

        generator = SummaryGenerator(repository, event_bus, api_key="test_key")

        for model_name in ["o1-preview", "o1-mini"]:
            kwargs = generator._build_api_kwargs(
                base_temp=0.3,
                base_max_tokens=500,
                model=model_name,
                reasoning_effort="medium",
            )

            assert kwargs["max_completion_tokens"] > 500, (
                f"{model_name} should get multiplied token budget, "
                f"got {kwargs['max_completion_tokens']}"
            )
