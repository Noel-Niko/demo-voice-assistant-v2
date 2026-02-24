"""Transcript streamer service for emitting transcript lines over time.

Streams transcript data line-by-line, delegating word-level streaming to WordStreamer.
Follows Single Responsibility Principle - orchestrates line sequencing only.
"""
import asyncio
from uuid import UUID

from app.services.event_bus import Event, InMemoryEventBus
from app.services.transcript_parser import TranscriptParser
from app.services.word_streamer import WordStreamer
from app.repositories.conversation_repository import ConversationRepository

import structlog

logger = structlog.get_logger(__name__)


class TranscriptStreamer:
    """Streams transcript lines one at a time via WordStreamer.

    Reads all lines from the parser, then iterates through them sequentially,
    delegating each line to WordStreamer for word-by-word delivery.
    Publishes streaming.complete when all lines have been streamed.

    Follows Observer Pattern (publishes events) and Async/Await Pattern.
    """

    def __init__(
        self,
        parser: TranscriptParser,
        repository: ConversationRepository,
        event_bus: InMemoryEventBus,
        word_streamer: WordStreamer,
        initial_delay: float = 2.0,
        inter_line_delay: float = 0.5,
    ) -> None:
        """Initialize transcript streamer.

        Args:
            parser: Transcript file parser
            repository: Conversation repository for persistence
            event_bus: Event bus for publishing events
            word_streamer: WordStreamer for word-level streaming
            initial_delay: Delay before first line in seconds (default: 2.0)
            inter_line_delay: Delay between lines in seconds (default: 0.5)
        """
        self.parser = parser
        self.repository = repository
        self.event_bus = event_bus
        self.word_streamer = word_streamer
        self.initial_delay = initial_delay
        self.inter_line_delay = inter_line_delay
        self._active_streams: dict[UUID, asyncio.Task] = {}

    async def start_streaming(self, conversation_id: UUID) -> None:
        """Start streaming transcript for conversation.

        Creates a background task that streams transcript lines one at a time.

        Args:
            conversation_id: Conversation UUID
        """
        if conversation_id in self._active_streams:
            logger.warning(
                "stream_already_active",
                conversation_id=str(conversation_id),
            )
            return

        lines = await self.parser.read_all_lines()

        logger.info(
            "streaming_started",
            conversation_id=str(conversation_id),
            total_lines=len(lines),
        )

        task = asyncio.create_task(
            self._stream_lines(conversation_id, lines)
        )
        self._active_streams[conversation_id] = task

    async def stop_streaming(self, conversation_id: UUID) -> None:
        """Stop streaming for conversation.

        Cancels the background streaming task.

        Args:
            conversation_id: Conversation UUID
        """
        if conversation_id in self._active_streams:
            task = self._active_streams[conversation_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self._active_streams[conversation_id]

            logger.info(
                "streaming_stopped",
                conversation_id=str(conversation_id),
            )

    async def _stream_lines(self, conversation_id: UUID, lines: list) -> None:
        """Stream transcript lines one at a time via WordStreamer.

        Args:
            conversation_id: Conversation UUID
            lines: All transcript lines to stream
        """
        try:
            if self.initial_delay > 0:
                logger.debug(
                    "waiting_before_first_line",
                    conversation_id=str(conversation_id),
                    initial_delay=self.initial_delay,
                )
                await asyncio.sleep(self.initial_delay)

            for i, line in enumerate(lines):
                line_id = f"{conversation_id}-seq-{line.sequence_number}"

                await self.word_streamer.stream_line_as_words(
                    conversation_id, line, line_id
                )

                logger.debug(
                    "line_streamed",
                    conversation_id=str(conversation_id),
                    line_id=line_id,
                    sequence_number=line.sequence_number,
                )

                is_last = (i == len(lines) - 1)
                if not is_last and self.inter_line_delay > 0:
                    await asyncio.sleep(self.inter_line_delay)

            await self._on_streaming_complete(conversation_id)

        except asyncio.CancelledError:
            logger.info(
                "streaming_cancelled",
                conversation_id=str(conversation_id),
            )
            raise
        except Exception as e:
            logger.error(
                "streaming_error",
                conversation_id=str(conversation_id),
                error=str(e),
                exc_info=True,
            )
            raise

    async def _on_streaming_complete(self, conversation_id: UUID) -> None:
        """Handle streaming completion.

        Publishes streaming.complete event and cleans up task.

        Args:
            conversation_id: Conversation UUID
        """
        event = Event.create(
            event_type="streaming.complete",
            source="transcript_streamer",
            data={"conversation_id": str(conversation_id)},
            conversation_id=str(conversation_id),
        )
        await self.event_bus.publish(event)

        if conversation_id in self._active_streams:
            del self._active_streams[conversation_id]

        logger.info(
            "streaming_complete",
            conversation_id=str(conversation_id),
        )

    async def shutdown(self) -> None:
        """Shutdown transcript streamer and cancel all active streaming tasks.

        Should be called during application shutdown before stopping event bus.
        Immediately cancels all streaming tasks to prevent them from publishing
        events after the event bus has stopped.
        """
        if not self._active_streams:
            logger.info("transcript_streamer_shutdown_no_active_streams")
            return

        logger.info(
            "transcript_streamer_shutting_down",
            active_stream_count=len(self._active_streams),
        )

        # Cancel all active streaming tasks
        tasks_to_cancel = list(self._active_streams.values())
        conversation_ids = list(self._active_streams.keys())

        for task in tasks_to_cancel:
            task.cancel()

        # Wait for all tasks to complete cancellation
        await asyncio.gather(*tasks_to_cancel, return_exceptions=True)

        # Clear the active streams dictionary
        self._active_streams.clear()

        logger.info(
            "transcript_streamer_shutdown_complete",
            cancelled_conversations=len(conversation_ids),
        )
