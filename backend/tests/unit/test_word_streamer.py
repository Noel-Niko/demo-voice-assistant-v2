"""Unit tests for WordStreamer.

Following TDD: Tests written FIRST, then implementation.

WordStreamer simulates production Genesys behavior by:
- Splitting complete lines into words
- Emitting words incrementally (like real-time transcription)
- Sending interim updates as words accumulate
- Sending final update when line is complete
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4
from datetime import datetime, timezone

from app.services.word_streamer import WordStreamer
from app.services.transcript_parser import TranscriptLine
from app.services.event_bus import InMemoryEventBus


@pytest.mark.asyncio
class TestWordStreamer:
    """Test suite for WordStreamer service."""

    def test_split_into_words_basic(self):
        """Test splitting text into words."""
        event_bus = Mock()
        repository = Mock()

        streamer = WordStreamer(
            repository=repository,
            event_bus=event_bus,
            words_per_second=2.5,
        )

        words = streamer.split_into_words("Hello world test")
        assert words == ["Hello", "world", "test"]

    def test_split_into_words_with_punctuation(self):
        """Test that punctuation stays with words."""
        event_bus = Mock()
        repository = Mock()

        streamer = WordStreamer(
            repository=repository,
            event_bus=event_bus,
            words_per_second=2.5,
        )

        words = streamer.split_into_words("Hello, world! How are you?")
        assert words == ["Hello,", "world!", "How", "are", "you?"]

    def test_split_into_words_empty_string(self):
        """Test splitting empty string returns empty list."""
        event_bus = Mock()
        repository = Mock()

        streamer = WordStreamer(
            repository=repository,
            event_bus=event_bus,
            words_per_second=2.5,
        )

        words = streamer.split_into_words("")
        assert words == []

    def test_split_into_words_single_word(self):
        """Test splitting single word."""
        event_bus = Mock()
        repository = Mock()

        streamer = WordStreamer(
            repository=repository,
            event_bus=event_bus,
            words_per_second=2.5,
        )

        words = streamer.split_into_words("Hello")
        assert words == ["Hello"]

    def test_calculate_word_delay(self):
        """Test calculating delay between words at 2.5 words/second."""
        event_bus = Mock()
        repository = Mock()

        streamer = WordStreamer(
            repository=repository,
            event_bus=event_bus,
            words_per_second=2.5,
        )

        # 2.5 words/second = 0.4 seconds per word
        delay = streamer.calculate_word_delay()
        assert delay == 0.4

    def test_calculate_word_delay_custom_rate(self):
        """Test calculating delay with custom words per second."""
        event_bus = Mock()
        repository = Mock()

        streamer = WordStreamer(
            repository=repository,
            event_bus=event_bus,
            words_per_second=5.0,
        )

        # 5.0 words/second = 0.2 seconds per word
        delay = streamer.calculate_word_delay()
        assert delay == 0.2

    async def test_stream_line_as_words_emits_interim_events(self):
        """Test that streaming emits interim updates as words accumulate."""
        event_bus = Mock()
        event_bus.publish = AsyncMock()
        repository = Mock()
        repository.upsert_transcript_line = AsyncMock()

        streamer = WordStreamer(
            repository=repository,
            event_bus=event_bus,
            words_per_second=100,  # Fast for testing
        )

        line = TranscriptLine(
            timestamp=datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc),
            speaker="agent",
            text="Hello world test",
            sequence_number=1,
        )

        conversation_id = UUID("12345678-1234-1234-1234-123456789012")
        line_id = "test-line-1"

        await streamer.stream_line_as_words(conversation_id, line, line_id)

        # Should have published interim events for each word
        # "Hello" (interim), "Hello world" (interim), "Hello world test" (final)
        assert event_bus.publish.call_count >= 3

        # Check event types
        calls = event_bus.publish.call_args_list
        event_types = [call[0][0].event_type for call in calls]

        # Should have interim events
        assert "transcript.word.interim" in event_types
        # Should have final event
        assert "transcript.word.final" in event_types

    async def test_stream_line_as_words_interim_has_partial_text(self):
        """Test that interim events contain accumulated words."""
        event_bus = Mock()
        event_bus.publish = AsyncMock()
        repository = Mock()
        repository.upsert_transcript_line = AsyncMock()

        streamer = WordStreamer(
            repository=repository,
            event_bus=event_bus,
            words_per_second=100,
        )

        line = TranscriptLine(
            timestamp=datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc),
            speaker="agent",
            text="Hello world test",
            sequence_number=1,
        )

        conversation_id = UUID("12345678-1234-1234-1234-123456789012")
        line_id = "test-line-1"

        await streamer.stream_line_as_words(conversation_id, line, line_id)

        # Find interim events
        calls = event_bus.publish.call_args_list
        interim_events = [
            call[0][0] for call in calls
            if call[0][0].event_type == "transcript.word.interim"
        ]

        # Should have at least 2 interim events
        assert len(interim_events) >= 2

        # Check first interim event has partial text
        first_interim = interim_events[0]
        assert first_interim.data["partial_text"] == "Hello"
        assert first_interim.data["is_final"] == False

        # Check second interim event has more words
        if len(interim_events) > 1:
            second_interim = interim_events[1]
            assert second_interim.data["partial_text"] == "Hello world"
            assert second_interim.data["is_final"] == False

    async def test_stream_line_as_words_final_has_complete_text(self):
        """Test that final event contains complete text and is_final=True."""
        event_bus = Mock()
        event_bus.publish = AsyncMock()
        repository = Mock()
        repository.upsert_transcript_line = AsyncMock()

        streamer = WordStreamer(
            repository=repository,
            event_bus=event_bus,
            words_per_second=100,
        )

        line = TranscriptLine(
            timestamp=datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc),
            speaker="agent",
            text="Hello world test",
            sequence_number=1,
        )

        conversation_id = UUID("12345678-1234-1234-1234-123456789012")
        line_id = "test-line-1"

        await streamer.stream_line_as_words(conversation_id, line, line_id)

        # Find final event
        calls = event_bus.publish.call_args_list
        final_events = [
            call[0][0] for call in calls
            if call[0][0].event_type == "transcript.word.final"
        ]

        # Should have exactly one final event
        assert len(final_events) == 1

        final_event = final_events[0]
        assert final_event.data["text"] == "Hello world test"
        assert final_event.data["is_final"] == True
        assert final_event.data["line_id"] == line_id

    async def test_stream_line_as_words_saves_to_repository(self):
        """Test that interim and final updates are saved to repository."""
        event_bus = Mock()
        event_bus.publish = AsyncMock()
        repository = Mock()
        repository.upsert_transcript_line = AsyncMock()

        streamer = WordStreamer(
            repository=repository,
            event_bus=event_bus,
            words_per_second=100,
        )

        line = TranscriptLine(
            timestamp=datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc),
            speaker="agent",
            text="Hello world",
            sequence_number=1,
        )

        conversation_id = UUID("12345678-1234-1234-1234-123456789012")
        line_id = "test-line-1"

        await streamer.stream_line_as_words(conversation_id, line, line_id)

        # Should have called upsert for each word (interim) + final
        assert repository.upsert_transcript_line.call_count >= 2

    async def test_stream_line_respects_timing(self):
        """Test that word streaming respects configured timing."""
        event_bus = Mock()
        event_bus.publish = AsyncMock()
        repository = Mock()
        repository.upsert_transcript_line = AsyncMock()

        # Use slower rate for timing test
        streamer = WordStreamer(
            repository=repository,
            event_bus=event_bus,
            words_per_second=5.0,  # 0.2 seconds per word
        )

        line = TranscriptLine(
            timestamp=datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc),
            speaker="agent",
            text="Hello world",
            sequence_number=1,
        )

        conversation_id = UUID("12345678-1234-1234-1234-123456789012")
        line_id = "test-line-1"

        import time
        start_time = time.time()
        await streamer.stream_line_as_words(conversation_id, line, line_id)
        elapsed = time.time() - start_time

        # 2 words with 1 delay between them = 0.2s (with some tolerance)
        assert elapsed >= 0.15  # Allow some overhead for async operations

    async def test_stream_single_word_line(self):
        """Test streaming a line with only one word."""
        event_bus = Mock()
        event_bus.publish = AsyncMock()
        repository = Mock()
        repository.upsert_transcript_line = AsyncMock()

        streamer = WordStreamer(
            repository=repository,
            event_bus=event_bus,
            words_per_second=100,
        )

        line = TranscriptLine(
            timestamp=datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc),
            speaker="agent",
            text="Hello",
            sequence_number=1,
        )

        conversation_id = UUID("12345678-1234-1234-1234-123456789012")
        line_id = "test-line-1"

        await streamer.stream_line_as_words(conversation_id, line, line_id)

        # Single word should go straight to final
        calls = event_bus.publish.call_args_list
        event_types = [call[0][0].event_type for call in calls]

        # Should have final event
        assert "transcript.word.final" in event_types

    async def test_stream_empty_line(self):
        """Test streaming empty line publishes final immediately."""
        event_bus = Mock()
        event_bus.publish = AsyncMock()
        repository = Mock()
        repository.upsert_transcript_line = AsyncMock()

        streamer = WordStreamer(
            repository=repository,
            event_bus=event_bus,
            words_per_second=100,
        )

        line = TranscriptLine(
            timestamp=datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc),
            speaker="agent",
            text="",
            sequence_number=1,
        )

        conversation_id = UUID("12345678-1234-1234-1234-123456789012")
        line_id = "test-line-1"

        await streamer.stream_line_as_words(conversation_id, line, line_id)

        # Empty line should publish final immediately
        assert event_bus.publish.call_count == 1

        final_event = event_bus.publish.call_args_list[0][0][0]
        assert final_event.event_type == "transcript.word.final"
        assert final_event.data["text"] == ""
        assert final_event.data["is_final"] == True
