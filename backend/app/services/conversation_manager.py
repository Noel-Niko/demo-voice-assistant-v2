"""Conversation manager for orchestrating conversation lifecycle.

Provides high-level facade over transcript streaming and summarization services.
Follows Facade Pattern for clean API.
"""
from uuid import UUID

from app.services.transcript_streamer import TranscriptStreamer
from app.services.event_bus import Event, InMemoryEventBus
from app.repositories.conversation_repository import ConversationRepository
from app.models.schemas import (
    ConversationStateResponse,
    TranscriptLineSchema,
    SummarySchema,
    ComplianceResultSchema,
    CRMFieldExtractionSchema,
)

import structlog

logger = structlog.get_logger(__name__)


class ConversationManager:
    """Manages conversation lifecycle and coordination.

    Facade that provides simple interface for complex operations:
    - Starting conversations
    - Coordinating transcript streaming
    - Retrieving conversation state

    Follows Facade Pattern and Single Responsibility Principle.
    """

    def __init__(
        self,
        repository: ConversationRepository,
        streamer: TranscriptStreamer,
        event_bus: InMemoryEventBus,
    ) -> None:
        """Initialize conversation manager.

        Args:
            repository: Conversation repository
            streamer: Transcript streamer service
            event_bus: Event bus for publishing events
        """
        self.repository = repository
        self.streamer = streamer
        self.event_bus = event_bus

    async def start_conversation(self) -> UUID:
        """Start a new conversation.

        Creates conversation in database and starts transcript streaming.

        Returns:
            UUID of created conversation
        """
        # Create conversation
        conversation_id = await self.repository.create_conversation()

        logger.info("conversation_started", conversation_id=str(conversation_id))

        # Start transcript streaming
        await self.streamer.start_streaming(conversation_id)

        # Publish event
        await self.event_bus.publish(
            Event.create(
                event_type="conversation.started",
                source="conversation_manager",
                data={"conversation_id": str(conversation_id)},
                conversation_id=str(conversation_id),
            )
        )

        return conversation_id

    async def get_conversation_state(
        self, conversation_id: UUID
    ) -> ConversationStateResponse | None:
        """Get current state of conversation.

        Args:
            conversation_id: Conversation UUID

        Returns:
            ConversationStateResponse with full conversation data or None if not found
        """
        conversation = await self.repository.get_conversation(conversation_id)

        if not conversation:
            logger.warning(
                "conversation_not_found",
                conversation_id=str(conversation_id),
            )
            return None

        # Convert to response schema
        return ConversationStateResponse(
            conversation_id=conversation.id,
            status=conversation.status,
            started_at=conversation.started_at,
            ended_at=conversation.ended_at,
            transcript_lines=[
                TranscriptLineSchema(
                    line_id=line.line_id,
                    timestamp=line.timestamp,
                    speaker=line.speaker,
                    text=line.text,
                    sequence_number=line.sequence_number,
                    is_final=line.is_final,
                )
                for line in conversation.transcript_lines
            ],
            summaries=[
                SummarySchema(
                    version=summary.version,
                    summary_text=summary.summary_text,
                    transcript_line_count=summary.transcript_line_count,
                    generated_at=summary.generated_at,
                )
                for summary in conversation.summaries
            ],
            summary_interval=conversation.summary_interval,
            disposition_code=conversation.disposition_code,
            wrap_up_notes=conversation.wrap_up_notes,
            agent_feedback=conversation.agent_feedback,
            acw_duration_secs=conversation.acw_duration_secs,
            compliance_results=[
                ComplianceResultSchema(
                    item_label=item.item_label,
                    is_checked=item.is_checked,
                    auto_detected=item.auto_detected,
                    checked_at=item.checked_at,
                )
                for item in conversation.compliance_results
            ],
            crm_field_extractions=[
                CRMFieldExtractionSchema(
                    field_name=field.field_name,
                    extracted_value=field.extracted_value,
                    source=field.source,
                    confidence=field.confidence,
                    extracted_at=field.extracted_at,
                )
                for field in conversation.crm_field_extractions
            ],
        )

    async def complete_conversation(
        self,
        conversation_id: UUID,
        disposition_code: str | None = None,
        wrap_up_notes: str | None = None,
        agent_feedback: str | None = None,
        acw_duration_secs: int | None = None,
        compliance_checklist: list[dict] | None = None,
        crm_fields: list[dict] | None = None,
    ) -> ConversationStateResponse | None:
        """Complete a conversation with ACW (After-Call Work) data.

        Saves all ACW data and marks conversation as completed.

        Args:
            conversation_id: Conversation UUID
            disposition_code: Disposition code (e.g., RESOLVED, ESCALATED)
            wrap_up_notes: Agent's wrap-up notes
            agent_feedback: Agent rating ('up' or 'down')
            acw_duration_secs: ACW phase duration in seconds
            compliance_checklist: List of compliance items
            crm_fields: List of extracted CRM fields

        Returns:
            Updated ConversationStateResponse or None if not found
        """
        # Verify conversation exists
        conversation = await self.repository.get_conversation(conversation_id)
        if not conversation:
            logger.warning(
                "conversation_not_found_for_completion",
                conversation_id=str(conversation_id),
            )
            return None

        # Save ACW data
        if disposition_code:
            await self.repository.save_disposition(conversation_id, disposition_code)

        if wrap_up_notes:
            await self.repository.save_wrap_up_notes(conversation_id, wrap_up_notes)

        if agent_feedback:
            await self.repository.save_agent_feedback(conversation_id, agent_feedback)

        if compliance_checklist:
            await self.repository.save_compliance_results(
                conversation_id, compliance_checklist
            )

        if crm_fields:
            await self.repository.save_crm_fields(conversation_id, crm_fields)

        # Mark conversation as complete (with optional ACW duration)
        await self.repository.mark_complete(conversation_id, acw_duration_secs)

        logger.info(
            "conversation_completed",
            conversation_id=str(conversation_id),
            disposition_code=disposition_code,
        )

        # Return updated state
        return await self.get_conversation_state(conversation_id)
