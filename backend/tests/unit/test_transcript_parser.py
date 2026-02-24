"""Unit tests for TranscriptParser.

Following TDD: Tests written FIRST, then implementation.
"""
import pytest
from datetime import datetime

from app.services.transcript_parser import TranscriptParser, TranscriptLine


class TestTranscriptParser:
    """Test suite for TranscriptParser."""

    def test_parse_line_with_pipe_delimiter(self):
        """Test parsing line with standard pipe delimiter."""
        parser = TranscriptParser("dummy.txt")
        line = "02/01/2026 11:39:00|Agent:Thank you for calling."

        result = parser.parse_line(line, 1)

        assert result is not None
        assert result.speaker == "agent"
        assert result.text == "Thank you for calling."
        assert result.sequence_number == 1
        assert result.timestamp == datetime(2026, 2, 1, 11, 39, 0)

    def test_parse_line_with_tab_delimiter(self):
        """Test parsing line with tab delimiter (edge case from line 70)."""
        parser = TranscriptParser("dummy.txt")
        line = "04/10/2026 11:40:08\tCustomer:Okay, it's 784562."

        result = parser.parse_line(line, 70)

        assert result is not None
        assert result.speaker == "customer"
        assert result.text == "Okay, it's 784562."
        assert result.sequence_number == 70

    def test_parse_line_with_tab_delimiter_no_speaker(self):
        """Test parsing line with tab delimiter and missing speaker prefix."""
        parser = TranscriptParser("dummy.txt")
        line = "04/10/2026 11:40:08\tOkay, it's 784562."

        result = parser.parse_line(line, 70)

        assert result is not None
        assert result.speaker == "unknown"
        assert result.text == "Okay, it's 784562."

    def test_parse_line_normalizes_speaker_to_lowercase(self):
        """Test that speaker names are normalized to lowercase."""
        parser = TranscriptParser("dummy.txt")
        line = "02/01/2026 11:39:00|AGENT:Hello"

        result = parser.parse_line(line, 1)

        assert result.speaker == "agent"

    def test_parse_line_handles_colon_in_message(self):
        """Test that colons in message text are preserved."""
        parser = TranscriptParser("dummy.txt")
        line = "02/01/2026 11:39:00|Agent:Order number: 12345"

        result = parser.parse_line(line, 1)

        assert result.text == "Order number: 12345"

    def test_parse_line_skips_header_line(self):
        """Test that header line is skipped."""
        parser = TranscriptParser("dummy.txt")
        line = "Timestamp|Transcript_Log"

        result = parser.parse_line(line, 0)

        assert result is None

    def test_parse_line_invalid_format_returns_none(self):
        """Test that invalid format returns None."""
        parser = TranscriptParser("dummy.txt")
        line = "Invalid line without proper format"

        result = parser.parse_line(line, 1)

        assert result is None

    def test_parse_line_invalid_timestamp_returns_none(self):
        """Test that invalid timestamp format returns None."""
        parser = TranscriptParser("dummy.txt")
        line = "InvalidDate|Agent:Hello"

        result = parser.parse_line(line, 1)

        assert result is None

    def test_parse_line_empty_returns_none(self):
        """Test that empty line returns None."""
        parser = TranscriptParser("dummy.txt")
        line = ""

        result = parser.parse_line(line, 1)

        assert result is None

    def test_parse_line_strips_whitespace(self):
        """Test that leading/trailing whitespace is stripped."""
        parser = TranscriptParser("dummy.txt")
        line = "  02/01/2026 11:39:00|Agent:  Hello  "

        result = parser.parse_line(line, 1)

        assert result is not None
        assert result.text == "Hello"

    @pytest.mark.asyncio
    async def test_read_all_lines_from_file(self, tmp_path):
        """Test reading and parsing all lines from file."""
        # Create temporary test file
        test_file = tmp_path / "test_transcript.txt"
        test_file.write_text(
            "Timestamp|Transcript_Log\n"
            "02/01/2026 11:39:00|Agent:Hello\n"
            "02/01/2026 11:39:01|Customer:Hi\n"
            "Invalid line\n"
            "02/01/2026 11:39:02|Agent:How can I help?\n"
        )

        parser = TranscriptParser(str(test_file))
        lines = await parser.read_all_lines()

        # Should have 3 valid lines (skipping header and invalid line)
        assert len(lines) == 3
        assert lines[0].speaker == "agent"
        assert lines[1].speaker == "customer"
        assert lines[2].speaker == "agent"

    @pytest.mark.asyncio
    async def test_read_all_lines_preserves_sequence(self, tmp_path):
        """Test that sequence numbers are preserved correctly."""
        test_file = tmp_path / "test_transcript.txt"
        test_file.write_text(
            "02/01/2026 11:39:00|Agent:First\n"
            "02/01/2026 11:39:01|Customer:Second\n"
            "02/01/2026 11:39:02|Agent:Third\n"
        )

        parser = TranscriptParser(str(test_file))
        lines = await parser.read_all_lines()

        assert lines[0].sequence_number == 1
        assert lines[1].sequence_number == 2
        assert lines[2].sequence_number == 3
