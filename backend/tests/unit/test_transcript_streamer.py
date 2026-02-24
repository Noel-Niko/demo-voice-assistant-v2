"""Unit tests for TranscriptStreamer.

Following TDD: Tests written FIRST, then implementation.
Tests reflect word-by-word streaming pattern via WordStreamer delegation.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, call
from uuid import UUID
from datetime import datetime

from app.services.transcript_streamer import TranscriptStreamer
from app.services.transcript_parser import TranscriptLine
from app.services.event_bus import Event


@pytest.mark.asyncio
class TestTranscriptStreamer:
    """Test suite for TranscriptStreamer."""

    def _make_streamer(self, parser=None, repository=None, event_bus=None,
                       word_streamer=None, initial_delay=0.0, inter_line_delay=0.0):
        """Helper to build a TranscriptStreamer with sensible test defaults."""
        parser = parser or Mock(read_all_lines=AsyncMock(return_value=[]))
        repository = repository or Mock()
        event_bus = event_bus or Mock(publish=AsyncMock())
        word_streamer = word_streamer or Mock(stream_line_as_words=AsyncMock())
        return TranscriptStreamer(
            parser=parser,
            repository=repository,
            event_bus=event_bus,
            word_streamer=word_streamer,
            initial_delay=initial_delay,
            inter_line_delay=inter_line_delay,
        )

    def _make_lines(self, count: int) -> list[TranscriptLine]:
        """Create N test transcript lines."""
        return [
            TranscriptLine(
                timestamp=datetime(2026, 2, 1, 11, 39, i % 60),
                speaker="agent" if i % 2 == 0 else "customer",
                text=f"Message {i}",
                sequence_number=i,
            )
            for i in range(1, count + 1)
        ]

    async def test_start_creates_task(self):
        """Test that starting streaming creates a background task."""
        streamer = self._make_streamer()
        conversation_id = UUID("12345678-1234-1234-1234-123456789012")

        await streamer.start_streaming(conversation_id)

        assert conversation_id in streamer._active_streams

        await streamer.stop_streaming(conversation_id)

    async def test_stop_cancels_task(self):
        """Test that stopping streaming cancels the background task."""
        lines = self._make_lines(50)
        parser = Mock(read_all_lines=AsyncMock(return_value=lines))
        word_streamer = Mock(stream_line_as_words=AsyncMock(side_effect=lambda *a: asyncio.sleep(1)))

        streamer = self._make_streamer(parser=parser, word_streamer=word_streamer)
        conversation_id = UUID("12345678-1234-1234-1234-123456789012")

        await streamer.start_streaming(conversation_id)
        await asyncio.sleep(0.05)

        await streamer.stop_streaming(conversation_id)

        assert conversation_id not in streamer._active_streams

    async def test_no_duplicate_streams(self):
        """Test that starting stream twice for same conversation is ignored."""
        streamer = self._make_streamer()
        conversation_id = UUID("12345678-1234-1234-1234-123456789012")

        await streamer.start_streaming(conversation_id)
        await streamer.start_streaming(conversation_id)

        assert len(streamer._active_streams) == 1

        await streamer.stop_streaming(conversation_id)

    async def test_streams_each_line_through_word_streamer(self):
        """Test that each transcript line is delegated to word_streamer.stream_line_as_words()."""
        lines = self._make_lines(3)
        parser = Mock(read_all_lines=AsyncMock(return_value=lines))
        word_streamer = Mock(stream_line_as_words=AsyncMock())

        streamer = self._make_streamer(parser=parser, word_streamer=word_streamer)
        conversation_id = UUID("12345678-1234-1234-1234-123456789012")

        await streamer.start_streaming(conversation_id)
        await asyncio.sleep(0.1)

        assert word_streamer.stream_line_as_words.call_count == 3

        for i, line in enumerate(lines):
            actual_call = word_streamer.stream_line_as_words.call_args_list[i]
            assert actual_call[0][0] == conversation_id
            assert actual_call[0][1] == line

    async def test_generates_correct_line_ids(self):
        """Test that line IDs follow {conversation_id}-seq-{sequence_number} format."""
        lines = self._make_lines(2)
        parser = Mock(read_all_lines=AsyncMock(return_value=lines))
        word_streamer = Mock(stream_line_as_words=AsyncMock())

        streamer = self._make_streamer(parser=parser, word_streamer=word_streamer)
        conversation_id = UUID("12345678-1234-1234-1234-123456789012")

        await streamer.start_streaming(conversation_id)
        await asyncio.sleep(0.1)

        for i, line in enumerate(lines):
            actual_call = word_streamer.stream_line_as_words.call_args_list[i]
            expected_line_id = f"{conversation_id}-seq-{line.sequence_number}"
            assert actual_call[0][2] == expected_line_id

    async def test_inter_line_delay_between_lines(self):
        """Test that there is a delay between lines (but not after the last one)."""
        lines = self._make_lines(3)
        parser = Mock(read_all_lines=AsyncMock(return_value=lines))
        word_streamer = Mock(stream_line_as_words=AsyncMock())

        inter_line_delay = 0.1
        streamer = self._make_streamer(
            parser=parser,
            word_streamer=word_streamer,
            inter_line_delay=inter_line_delay,
        )
        conversation_id = UUID("12345678-1234-1234-1234-123456789012")

        import time
        start = time.time()
        await streamer.start_streaming(conversation_id)
        # 3 lines with 0.1s delay between each pair = 0.2s minimum
        await asyncio.sleep(0.4)
        elapsed = time.time() - start

        assert word_streamer.stream_line_as_words.call_count == 3
        # Should have taken at least 0.2s (2 inter-line delays)
        assert elapsed >= 0.2

    async def test_streaming_complete_event_after_all_lines(self):
        """Test that streaming.complete event is published after all lines are streamed."""
        lines = self._make_lines(2)
        parser = Mock(read_all_lines=AsyncMock(return_value=lines))
        event_bus = Mock(publish=AsyncMock())
        word_streamer = Mock(stream_line_as_words=AsyncMock())

        streamer = self._make_streamer(
            parser=parser,
            event_bus=event_bus,
            word_streamer=word_streamer,
        )
        conversation_id = UUID("12345678-1234-1234-1234-123456789012")

        await streamer.start_streaming(conversation_id)
        await asyncio.sleep(0.1)

        event_types = [c[0][0].event_type for c in event_bus.publish.call_args_list]
        assert "streaming.complete" in event_types

    async def test_does_not_call_repository_add_transcript_lines(self):
        """TranscriptStreamer should NOT call repository.add_transcript_lines (WordStreamer handles persistence)."""
        lines = self._make_lines(2)
        parser = Mock(read_all_lines=AsyncMock(return_value=lines))
        repository = Mock(add_transcript_lines=AsyncMock())
        word_streamer = Mock(stream_line_as_words=AsyncMock())

        streamer = self._make_streamer(
            parser=parser,
            repository=repository,
            word_streamer=word_streamer,
        )
        conversation_id = UUID("12345678-1234-1234-1234-123456789012")

        await streamer.start_streaming(conversation_id)
        await asyncio.sleep(0.1)

        repository.add_transcript_lines.assert_not_called()
