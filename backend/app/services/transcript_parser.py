"""Transcript parser for reading and parsing transcript files.

Handles the Option2_data_file.txt format with edge cases:
- Pipe delimiter: MM/DD/YYYY HH:MM:SS|Speaker:Message
- Tab delimiter: MM/DD/YYYY HH:MM:SS\tSpeaker:Message (line 70 edge case)

Follows Single Responsibility Principle - only parses transcript data.
"""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TranscriptLine:
    """Parsed transcript line data.

    Attributes:
        timestamp: Original timestamp from transcript
        speaker: Speaker role (agent, customer, unknown)
        text: Transcript text content
        sequence_number: Line number in original file
    """

    timestamp: datetime
    speaker: str
    text: str
    sequence_number: int


class TranscriptParser:
    """Parser for transcript files.

    Handles both pipe (|) and tab (\t) delimiters for robustness.
    Gracefully degrades on malformed lines (returns None).
    """

    def __init__(self, file_path: str) -> None:
        """Initialize parser.

        Args:
            file_path: Path to transcript file
        """
        self.file_path = Path(file_path)

    def parse_line(self, line: str, sequence: int) -> TranscriptLine | None:
        """Parse single transcript line.

        Handles edge cases:
        - Line 70 uses tab instead of pipe
        - Missing speaker prefix
        - Invalid timestamp format
        - Header line

        Args:
            line: Raw line text
            sequence: Line number in file

        Returns:
            Parsed TranscriptLine or None if invalid
        """
        line = line.strip()

        # Skip empty lines
        if not line:
            return None

        # Skip header line
        if line.startswith("Timestamp"):
            return None

        # Try pipe delimiter first, then tab
        parts = None
        if "|" in line:
            parts = line.split("|", 1)
        elif "\t" in line:
            parts = line.split("\t", 1)
        else:
            logger.warning(
                "invalid_line_format",
                line=line[:50],
                sequence=sequence,
                reason="no_delimiter",
            )
            return None

        if len(parts) != 2:
            logger.warning(
                "invalid_line_format",
                line=line[:50],
                sequence=sequence,
                reason="split_failed",
            )
            return None

        timestamp_str, rest = parts

        # Parse speaker and text
        if ":" in rest:
            speaker, text = rest.split(":", 1)
            speaker = speaker.strip().lower()
            text = text.strip()
        else:
            # Edge case: No speaker prefix (line 70 variant)
            speaker = "unknown"
            text = rest.strip()
            logger.debug(
                "line_missing_speaker",
                sequence=sequence,
                line=line[:50],
            )

        # Parse timestamp
        try:
            timestamp = datetime.strptime(timestamp_str.strip(), "%m/%d/%Y %H:%M:%S")
        except ValueError as e:
            logger.warning(
                "invalid_timestamp",
                timestamp_str=timestamp_str,
                sequence=sequence,
                error=str(e),
            )
            return None

        return TranscriptLine(
            timestamp=timestamp,
            speaker=speaker,
            text=text,
            sequence_number=sequence,
        )

    async def read_all_lines(self) -> list[TranscriptLine]:
        """Read and parse all lines from transcript file.

        Skips invalid lines and logs warnings.

        Returns:
            List of parsed transcript lines

        Raises:
            FileNotFoundError: If transcript file doesn't exist
        """
        if not self.file_path.exists():
            logger.error("transcript_file_not_found", path=str(self.file_path))
            raise FileNotFoundError(f"Transcript file not found: {self.file_path}")

        lines = []
        with open(self.file_path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f, start=1):
                parsed = self.parse_line(line, idx)
                if parsed:
                    lines.append(parsed)

        logger.info(
            "transcript_file_parsed",
            file_path=str(self.file_path),
            total_lines=idx if 'idx' in locals() else 0,
            valid_lines=len(lines),
        )

        return lines
