"""Word Streamer Service for simulating real-time transcription.

Simulates production Genesys Cloud behavior where speech-to-text transcription
arrives word-by-word or phrase-by-phrase as the speaker talks.

In production:
- Genesys streams audio → text in real-time
- You receive interim results as words accumulate
- Final result arrives when speaker pauses

In demo:
- We have complete lines from file
- WordStreamer splits them into words
- Emits interim results progressively (like Genesys)
- Natural 2.5 words/second pacing
"""
import asyncio
from uuid import UUID
from datetime import datetime, timezone

from app.services.event_bus import Event, InMemoryEventBus
from app.services.transcript_parser import TranscriptLine
from app.repositories.conversation_repository import ConversationRepository

import structlog

logger = structlog.get_logger(__name__)


class WordStreamer:
    """Streams transcript lines word-by-word to simulate real-time transcription.

    Follows Single Responsibility Principle - only handles word-level streaming.
    Uses Observer Pattern (publishes events) and Async/Await Pattern.
    """

    def __init__(
        self,
        repository: ConversationRepository,
        event_bus: InMemoryEventBus,
        words_per_second: float = 2.5,
    ) -> None:
        """Initialize word streamer.

        Args:
            repository: Conversation repository for persistence
            event_bus: Event bus for publishing events
            words_per_second: Natural speaking rate (default: 2.5)
        """
        self.repository = repository
        self.event_bus = event_bus
        self.words_per_second = words_per_second

    def split_into_words(self, text: str) -> list[str]:
        """Split text into words while preserving punctuation.

        Args:
            text: Text to split

        Returns:
            List of words (empty list if text is empty)
        """
        if not text or not text.strip():
            return []

        # Split on whitespace, preserving punctuation with words
        return text.split()

    def calculate_word_delay(self) -> float:
        """Calculate delay between words based on speaking rate.

        Returns:
            Delay in seconds between words
        """
        return 1.0 / self.words_per_second

    async def stream_line_as_words(
        self,
        conversation_id: UUID,
        line: TranscriptLine,
        line_id: str,
    ) -> None:
        """Stream a complete line as word-by-word updates.

        Simulates real-time transcription by:
        1. Splitting line into words
        2. Emitting interim updates as words accumulate
        3. Emitting final update when complete

        Args:
            conversation_id: Conversation UUID
            line: Complete transcript line to stream
            line_id: Unique identifier for this line (for tracking interim updates)
        """
        words = self.split_into_words(line.text)
        word_delay = self.calculate_word_delay()

        # Handle empty line
        if not words:
            await self._publish_final(conversation_id, line, line_id, "")
            return

        # Handle single word - go straight to final
        if len(words) == 1:
            await self._publish_final(conversation_id, line, line_id, words[0])
            return

        # Stream words incrementally with interim updates
        accumulated_words = []

        for i, word in enumerate(words):
            accumulated_words.append(word)
            partial_text = " ".join(accumulated_words)

            is_last_word = (i == len(words) - 1)

            if is_last_word:
                # Final word - publish final event
                await self._publish_final(conversation_id, line, line_id, partial_text)
            else:
                # Interim word - publish interim event
                await self._publish_interim(conversation_id, line, line_id, partial_text)

            # Wait before next word (except after final word)
            if not is_last_word:
                await asyncio.sleep(word_delay)

    async def _publish_interim(
        self,
        conversation_id: UUID,
        line: TranscriptLine,
        line_id: str,
        partial_text: str,
    ) -> None:
        """Publish interim update event.

        Args:
            conversation_id: Conversation UUID
            line: Original transcript line
            line_id: Unique line identifier
            partial_text: Accumulated words so far
        """
        # Save interim line to database
        interim_line = TranscriptLine(
            timestamp=line.timestamp,
            speaker=line.speaker,
            text=partial_text,
            sequence_number=line.sequence_number,
        )

        await self.repository.upsert_transcript_line(
            conversation_id,
            interim_line,
            line_id=line_id,
            is_final=False,
        )

        # Publish interim event
        event = Event.create(
            event_type="transcript.word.interim",
            source="word_streamer",
            data={
                "conversation_id": str(conversation_id),
                "line_id": line_id,
                "speaker": line.speaker,
                "partial_text": partial_text,
                "is_final": False,
                "timestamp": line.timestamp.isoformat(),
                "sequence_number": line.sequence_number,
            },
            conversation_id=str(conversation_id),
        )

        await self.event_bus.publish(event)

        logger.debug(
            "interim_word_update",
            conversation_id=str(conversation_id),
            line_id=line_id,
            partial_text=partial_text,
        )

    async def _publish_final(
        self,
        conversation_id: UUID,
        line: TranscriptLine,
        line_id: str,
        final_text: str,
    ) -> None:
        """Publish final update event.

        Args:
            conversation_id: Conversation UUID
            line: Original transcript line
            line_id: Unique line identifier
            final_text: Complete text
        """
        # Save final line to database
        final_line = TranscriptLine(
            timestamp=line.timestamp,
            speaker=line.speaker,
            text=final_text,
            sequence_number=line.sequence_number,
        )

        await self.repository.upsert_transcript_line(
            conversation_id,
            final_line,
            line_id=line_id,
            is_final=True,
        )

        # Publish final event
        event = Event.create(
            event_type="transcript.word.final",
            source="word_streamer",
            data={
                "conversation_id": str(conversation_id),
                "line_id": line_id,
                "speaker": line.speaker,
                "text": final_text,
                "is_final": True,
                "timestamp": line.timestamp.isoformat(),
                "sequence_number": line.sequence_number,
            },
            conversation_id=str(conversation_id),
        )

        await self.event_bus.publish(event)

        logger.info(
            "final_word_update",
            conversation_id=str(conversation_id),
            line_id=line_id,
            text=final_text,
        )
