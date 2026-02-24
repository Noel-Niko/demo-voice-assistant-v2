"""Repository for conversation data access.

Follows Repository Pattern for clean separation between domain and data access.
All database operations are centralized here.
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.models.domain import (
    Conversation,
    TranscriptLine as TranscriptLineModel,
    Summary,
    ComplianceResult,
    CRMFieldExtraction,
    AIInteraction,
    DispositionSuggestion,
    ComplianceDetectionAttempt,
    AgentInteraction,
    ListeningModeSession,
)
from app.services.transcript_parser import TranscriptLine

import structlog

logger = structlog.get_logger(__name__)


class ConversationRepository:
    """Repository for conversation-related database operations.

    Follows Repository Pattern and Single Responsibility Principle.
    """

    def __init__(self, session_maker: async_sessionmaker) -> None:
        """Initialize repository.

        Args:
            session_maker: Async session maker factory
        """
        self.session_maker = session_maker

    async def create_conversation(self, summary_interval: int | None = None) -> UUID:
        """Create a new conversation.

        Args:
            summary_interval: Summary interval in seconds (defaults to config setting)

        Returns:
            UUID of created conversation
        """
        from app.config import settings

        interval = summary_interval if summary_interval is not None else settings.SUMMARY_INTERVAL_SECONDS

        async with self.session_maker() as session:
            conversation = Conversation(status="active", summary_interval=interval)
            session.add(conversation)
            await session.commit()
            await session.refresh(conversation)

            conversation_id = UUID(conversation.id)
            logger.info(
                "conversation_created",
                conversation_id=str(conversation_id),
                summary_interval=interval,
            )
            return conversation_id

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        """Get conversation by ID with all related data.

        Args:
            conversation_id: Conversation UUID

        Returns:
            Conversation entity or None if not found
        """
        async with self.session_maker() as session:
            stmt = (
                select(Conversation)
                .where(Conversation.id == str(conversation_id))
                .options(
                    selectinload(Conversation.transcript_lines),
                    selectinload(Conversation.summaries),
                    selectinload(Conversation.compliance_results),
                    selectinload(Conversation.crm_field_extractions),
                )
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def add_transcript_lines(
        self, conversation_id: UUID, lines: list[TranscriptLine]
    ) -> None:
        """Add transcript lines to conversation.

        Args:
            conversation_id: Conversation UUID
            lines: List of parsed transcript lines
        """
        async with self.session_maker() as session:
            for line in lines:
                # For batch adding (non-streaming), each line gets unique line_id and is final
                line_id = f"{conversation_id}-seq-{line.sequence_number}"

                transcript_line = TranscriptLineModel(
                    conversation_id=str(conversation_id),
                    line_id=line_id,
                    timestamp=line.timestamp,
                    speaker=line.speaker,
                    text=line.text,
                    sequence_number=line.sequence_number,
                    is_final=True,  # Batch-added lines are complete
                )
                session.add(transcript_line)

            await session.commit()

            logger.debug(
                "transcript_lines_added",
                conversation_id=str(conversation_id),
                line_count=len(lines),
            )

    async def upsert_transcript_line(
        self,
        conversation_id: UUID,
        line: "TranscriptLine",
        line_id: str,
        is_final: bool,
    ) -> None:
        """Insert or update a transcript line (for word streaming).

        Used by WordStreamer to emit interim and final updates.
        If a line with the same line_id exists, update it. Otherwise, insert new.

        Args:
            conversation_id: Conversation UUID
            line: Parsed transcript line
            line_id: Unique identifier for this logical line
            is_final: Whether this is the final version
        """
        from app.services.transcript_parser import TranscriptLine

        async with self.session_maker() as session:
            # Check if line already exists
            stmt = (
                select(TranscriptLineModel)
                .where(TranscriptLineModel.conversation_id == str(conversation_id))
                .where(TranscriptLineModel.line_id == line_id)
            )
            result = await session.execute(stmt)
            existing_line = result.scalar_one_or_none()

            if existing_line:
                # Update existing line
                existing_line.text = line.text
                existing_line.is_final = is_final
                existing_line.timestamp = line.timestamp
                logger.debug(
                    "transcript_line_updated",
                    conversation_id=str(conversation_id),
                    line_id=line_id,
                    is_final=is_final,
                )
            else:
                # Insert new line
                transcript_line = TranscriptLineModel(
                    conversation_id=str(conversation_id),
                    line_id=line_id,
                    timestamp=line.timestamp,
                    speaker=line.speaker,
                    text=line.text,
                    sequence_number=line.sequence_number,
                    is_final=is_final,
                )
                session.add(transcript_line)
                logger.debug(
                    "transcript_line_inserted",
                    conversation_id=str(conversation_id),
                    line_id=line_id,
                    is_final=is_final,
                )

            await session.commit()

    async def get_all_transcript_lines(
        self, conversation_id: UUID
    ) -> list[TranscriptLineModel]:
        """Get all final transcript lines for conversation.

        Only returns lines where is_final=True so API state endpoint
        only shows complete lines (not interim word-streaming updates).

        Args:
            conversation_id: Conversation UUID

        Returns:
            List of transcript line models, ordered by sequence
        """
        async with self.session_maker() as session:
            stmt = (
                select(TranscriptLineModel)
                .where(TranscriptLineModel.conversation_id == str(conversation_id))
                .where(TranscriptLineModel.is_final == True)
                .order_by(TranscriptLineModel.sequence_number)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_recent_transcript_lines(
        self, conversation_id: UUID, seconds: int
    ) -> list[TranscriptLineModel]:
        """Get final transcript lines from last N seconds.

        Uses added_at (DB insertion time) instead of timestamp (file time)
        so the cutoff reflects when lines were actually streamed.
        Only returns is_final=True lines for summarization.

        Args:
            conversation_id: Conversation UUID
            seconds: Number of seconds to look back

        Returns:
            List of recent final transcript lines, ordered by added_at
        """
        async with self.session_maker() as session:
            cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=seconds)

            stmt = (
                select(TranscriptLineModel)
                .where(TranscriptLineModel.conversation_id == str(conversation_id))
                .where(TranscriptLineModel.is_final == True)
                .where(TranscriptLineModel.added_at >= cutoff_time)
                .order_by(TranscriptLineModel.added_at)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def save_summary(
        self,
        conversation_id: UUID,
        version: int,
        summary_text: str,
        transcript_line_count: int,
    ) -> None:
        """Save a summary for conversation.

        Args:
            conversation_id: Conversation UUID
            version: Summary version number
            summary_text: Generated summary content
            transcript_line_count: Number of lines summarized
        """
        async with self.session_maker() as session:
            summary = Summary(
                conversation_id=str(conversation_id),
                version=version,
                summary_text=summary_text,
                transcript_line_count=transcript_line_count,
            )
            session.add(summary)
            await session.commit()

            logger.info(
                "summary_saved",
                conversation_id=str(conversation_id),
                version=version,
                line_count=transcript_line_count,
            )

    async def get_latest_summary(self, conversation_id: UUID) -> Summary | None:
        """Get latest summary for conversation.

        Args:
            conversation_id: Conversation UUID

        Returns:
            Latest Summary entity or None if no summaries exist
        """
        async with self.session_maker() as session:
            stmt = (
                select(Summary)
                .where(Summary.conversation_id == str(conversation_id))
                .order_by(Summary.version.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_summary_count(self, conversation_id: UUID) -> int:
        """Get count of summaries for conversation.

        Args:
            conversation_id: Conversation UUID

        Returns:
            Number of summaries
        """
        async with self.session_maker() as session:
            stmt = (
                select(func.count())
                .select_from(Summary)
                .where(Summary.conversation_id == str(conversation_id))
            )
            result = await session.execute(stmt)
            return result.scalar() or 0

    async def get_all_summaries(self, conversation_id: UUID) -> list[Summary]:
        """Get all summaries for conversation.

        Args:
            conversation_id: Conversation UUID

        Returns:
            List of Summary entities, ordered by version
        """
        async with self.session_maker() as session:
            stmt = (
                select(Summary)
                .where(Summary.conversation_id == str(conversation_id))
                .order_by(Summary.version)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def update_summary_interval(self, conversation_id: UUID, interval_seconds: int) -> None:
        """Update summary interval for conversation.

        Args:
            conversation_id: Conversation UUID
            interval_seconds: New summary interval in seconds
        """
        async with self.session_maker() as session:
            stmt = select(Conversation).where(Conversation.id == str(conversation_id))
            result = await session.execute(stmt)
            conversation = result.scalar_one_or_none()

            if conversation:
                conversation.summary_interval = interval_seconds
                await session.commit()

                logger.info(
                    "summary_interval_updated_in_db",
                    conversation_id=str(conversation_id),
                    interval_seconds=interval_seconds,
                )
            else:
                logger.warning(
                    "cannot_update_interval_conversation_not_found",
                    conversation_id=str(conversation_id),
                )

    async def get_summary_interval(self, conversation_id: UUID) -> int | None:
        """Get summary interval for conversation.

        Args:
            conversation_id: Conversation UUID

        Returns:
            Summary interval in seconds, or None if conversation not found
        """
        async with self.session_maker() as session:
            stmt = select(Conversation.summary_interval).where(
                Conversation.id == str(conversation_id)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    # ===== ACW (After-Call Work) Methods =====

    async def mark_complete(
        self, conversation_id: UUID, acw_duration_secs: int | None = None
    ) -> None:
        """Mark conversation as completed.

        Sets status to 'completed' and records ended_at timestamp.
        Optionally records ACW phase duration.

        Args:
            conversation_id: Conversation UUID
            acw_duration_secs: ACW phase duration in seconds (optional)
        """
        async with self.session_maker() as session:
            stmt = select(Conversation).where(Conversation.id == str(conversation_id))
            result = await session.execute(stmt)
            conversation = result.scalar_one_or_none()

            if conversation:
                conversation.status = "completed"
                conversation.ended_at = datetime.now(timezone.utc)
                if acw_duration_secs is not None:
                    conversation.acw_duration_secs = acw_duration_secs
                await session.commit()

                logger.info(
                    "conversation_completed",
                    conversation_id=str(conversation_id),
                    ended_at=conversation.ended_at.isoformat(),
                    acw_duration_secs=acw_duration_secs,
                )

    async def save_disposition(self, conversation_id: UUID, code: str) -> None:
        """Save disposition code for conversation.

        Args:
            conversation_id: Conversation UUID
            code: Disposition code (e.g., 'RESOLVED', 'ESCALATED')
        """
        async with self.session_maker() as session:
            stmt = select(Conversation).where(Conversation.id == str(conversation_id))
            result = await session.execute(stmt)
            conversation = result.scalar_one_or_none()

            if conversation:
                conversation.disposition_code = code
                await session.commit()

                logger.info(
                    "disposition_saved",
                    conversation_id=str(conversation_id),
                    disposition_code=code,
                )

    async def save_wrap_up_notes(self, conversation_id: UUID, notes: str) -> None:
        """Save wrap-up notes for conversation.

        Args:
            conversation_id: Conversation UUID
            notes: Agent's wrap-up notes
        """
        async with self.session_maker() as session:
            stmt = select(Conversation).where(Conversation.id == str(conversation_id))
            result = await session.execute(stmt)
            conversation = result.scalar_one_or_none()

            if conversation:
                conversation.wrap_up_notes = notes
                await session.commit()

                logger.debug(
                    "wrap_up_notes_saved",
                    conversation_id=str(conversation_id),
                    notes_length=len(notes),
                )

    async def save_agent_feedback(self, conversation_id: UUID, rating: str) -> None:
        """Save agent feedback rating for conversation.

        Args:
            conversation_id: Conversation UUID
            rating: Agent rating ('up' or 'down')
        """
        async with self.session_maker() as session:
            stmt = select(Conversation).where(Conversation.id == str(conversation_id))
            result = await session.execute(stmt)
            conversation = result.scalar_one_or_none()

            if conversation:
                conversation.agent_feedback = rating
                await session.commit()

                logger.info(
                    "agent_feedback_saved",
                    conversation_id=str(conversation_id),
                    rating=rating,
                )

    async def save_compliance_results(
        self, conversation_id: UUID, items: list[dict]
    ) -> None:
        """Save compliance checklist results for conversation.

        Args:
            conversation_id: Conversation UUID
            items: List of compliance items with keys:
                - label: str
                - checked: bool
                - auto_detected: bool
        """
        async with self.session_maker() as session:
            for item in items:
                compliance_result = ComplianceResult(
                    conversation_id=str(conversation_id),
                    item_label=item["label"],
                    is_checked=item["checked"],
                    auto_detected=item["auto_detected"],
                )
                session.add(compliance_result)

            await session.commit()

            logger.info(
                "compliance_results_saved",
                conversation_id=str(conversation_id),
                item_count=len(items),
            )

    async def save_crm_fields(
        self, conversation_id: UUID, fields: list[dict]
    ) -> None:
        """Save CRM field extractions for conversation.

        Args:
            conversation_id: Conversation UUID
            fields: List of CRM fields with keys:
                - field_name: str
                - extracted_value: str
                - source: str ('AI' or 'Transcript')
                - confidence: float (0.0 to 1.0)
        """
        async with self.session_maker() as session:
            for field in fields:
                crm_field = CRMFieldExtraction(
                    conversation_id=str(conversation_id),
                    field_name=field["field_name"],
                    extracted_value=field["extracted_value"],
                    source=field["source"],
                    confidence=field["confidence"],
                )
                session.add(crm_field)

            await session.commit()

            logger.info(
                "crm_fields_saved",
                conversation_id=str(conversation_id),
                field_count=len(fields),
            )

    # ===== Audit Trail Methods (Tier 1) =====

    async def save_ai_interaction(
        self,
        conversation_id: UUID,
        interaction_type: str,
        prompt_text: str,
        response_text: str,
        model_name: str,
        tokens_used: int,
        cost_usd: float,
        latency_ms: int,
        agent_edited: bool = False,
        final_value: str | None = None,
    ) -> None:
        """Save AI/LLM interaction to audit trail.

        Args:
            conversation_id: Conversation UUID
            interaction_type: Type of interaction ('summary', 'disposition', 'compliance', 'crm')
            prompt_text: Full prompt sent to LLM
            response_text: Full response from LLM
            model_name: Model used (e.g., 'gpt-3.5-turbo')
            tokens_used: Total tokens consumed
            cost_usd: Cost in USD
            latency_ms: Response time in milliseconds
            agent_edited: Whether agent modified the AI output
            final_value: What agent actually used (if different)
        """
        async with self.session_maker() as session:
            ai_interaction = AIInteraction(
                conversation_id=str(conversation_id),
                interaction_type=interaction_type,
                prompt_text=prompt_text,
                response_text=response_text,
                model_name=model_name,
                tokens_used=tokens_used,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                agent_edited=agent_edited,
                final_value=final_value,
            )
            session.add(ai_interaction)
            await session.commit()

            logger.info(
                "ai_interaction_logged",
                conversation_id=str(conversation_id),
                interaction_type=interaction_type,
                tokens_used=tokens_used,
                cost_usd=cost_usd,
            )

    async def save_disposition_suggestions(
        self, conversation_id: UUID, suggestions: list[dict]
    ) -> None:
        """Save AI disposition suggestions to database.

        Args:
            conversation_id: Conversation UUID
            suggestions: List of suggestions with keys:
                - code: str
                - label: str (human-readable)
                - confidence: float
                - reasoning: str
                - rank: int (1, 2, or 3)
        """
        async with self.session_maker() as session:
            for suggestion in suggestions:
                disp_suggestion = DispositionSuggestion(
                    conversation_id=str(conversation_id),
                    suggested_code=suggestion["code"],
                    suggested_label=suggestion.get("label", suggestion["code"]),
                    confidence=suggestion["confidence"],
                    reasoning=suggestion["reasoning"],
                    rank=suggestion["rank"],
                )
                session.add(disp_suggestion)

            await session.commit()

            logger.info(
                "disposition_suggestions_saved",
                conversation_id=str(conversation_id),
                suggestion_count=len(suggestions),
            )

    async def save_compliance_attempts(
        self, conversation_id: UUID, attempts: list[dict]
    ) -> None:
        """Save compliance detection attempts to database.

        Args:
            conversation_id: Conversation UUID
            attempts: List of attempts with keys:
                - item_label: str
                - ai_detected: bool
                - ai_confidence: float
                - agent_override: bool
                - final_status: bool
        """
        async with self.session_maker() as session:
            for attempt in attempts:
                compliance_attempt = ComplianceDetectionAttempt(
                    conversation_id=str(conversation_id),
                    item_label=attempt["item_label"],
                    ai_detected=attempt["ai_detected"],
                    ai_confidence=attempt["ai_confidence"],
                    agent_override=attempt["agent_override"],
                    final_status=attempt["final_status"],
                )
                session.add(compliance_attempt)

            await session.commit()

            logger.info(
                "compliance_attempts_saved",
                conversation_id=str(conversation_id),
                attempt_count=len(attempts),
            )

    # ===== Agent Interaction Metrics Methods (Tier 3) =====

    async def get_agent_interactions(self, conversation_id: UUID) -> list[AgentInteraction]:
        """Retrieve all agent interactions for a conversation.

        Args:
            conversation_id: Conversation UUID

        Returns:
            List of AgentInteraction records
        """
        async with self.session_maker() as session:
            stmt = (
                select(AgentInteraction)
                .where(AgentInteraction.conversation_id == str(conversation_id))
                .order_by(AgentInteraction.timestamp)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_ai_interactions(self, conversation_id: UUID) -> list[AIInteraction]:
        """Retrieve all AI/LLM interactions for a conversation.

        Args:
            conversation_id: Conversation UUID

        Returns:
            List of AIInteraction records
        """
        async with self.session_maker() as session:
            stmt = (
                select(AIInteraction)
                .where(AIInteraction.conversation_id == str(conversation_id))
                .order_by(AIInteraction.created_at)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def save_agent_interaction(
        self,
        conversation_id: UUID,
        interaction_type: str,
        query_text: str | None = None,
        llm_request: str | None = None,
        llm_response: str | None = None,
        mcp_request: str | None = None,
        mcp_response: str | None = None,
        user_rating: str | None = None,
        manually_edited: bool = False,
        edit_details: str | None = None,
        context_data: str | None = None,
    ) -> int:
        """Save agent interaction to metrics table.

        Args:
            conversation_id: Conversation UUID
            interaction_type: Type of interaction (see AgentInteraction model for values)
            query_text: Original query text (for MCP queries)
            llm_request: Raw LLM request payload (JSON string)
            llm_response: Raw LLM response payload (JSON string)
            mcp_request: Raw MCP request payload (JSON string)
            mcp_response: Raw MCP response payload (JSON string)
            user_rating: Agent rating ('up', 'down', null)
            manually_edited: Whether agent edited AI output
            edit_details: Before/after edit information (JSON string)
            context_data: Additional context (JSON string)

        Returns:
            interaction_id: Auto-incremented integer primary key
        """
        async with self.session_maker() as session:
            interaction = AgentInteraction(
                conversation_id=str(conversation_id),
                interaction_type=interaction_type,
                query_text=query_text,
                llm_request=llm_request,
                llm_response=llm_response,
                mcp_request=mcp_request,
                mcp_response=mcp_response,
                user_rating=user_rating,
                manually_edited=manually_edited,
                edit_details=edit_details,
                context_data=context_data,
            )
            session.add(interaction)
            await session.commit()
            await session.refresh(interaction)

            logger.info(
                "agent_interaction_saved",
                conversation_id=str(conversation_id),
                interaction_type=interaction_type,
                interaction_id=interaction.id,
            )

            return interaction.id

    async def get_agent_interaction(self, interaction_id: int) -> AgentInteraction | None:
        """Get agent interaction by ID.

        Args:
            interaction_id: Integer primary key of the interaction

        Returns:
            AgentInteraction object or None if not found
        """
        async with self.session_maker() as session:
            stmt = select(AgentInteraction).where(AgentInteraction.id == interaction_id)
            result = await session.execute(stmt)
            return result.scalars().first()

    async def update_agent_interaction_rating(
        self, interaction_id: int, rating: str
    ) -> None:
        """Update user rating for an agent interaction.

        Args:
            interaction_id: Integer primary key of the interaction
            rating: User rating value ("up" or "down")
        """
        async with self.session_maker() as session:
            stmt = (
                update(AgentInteraction)
                .where(AgentInteraction.id == interaction_id)
                .values(user_rating=rating)
            )
            await session.execute(stmt)
            await session.commit()

            logger.info(
                "agent_interaction_rating_updated",
                interaction_id=interaction_id,
                rating=rating,
            )

    # ===== Listening Mode Session Methods (Tier 3) =====

    async def create_listening_mode_session(self, conversation_id: UUID) -> int:
        """Create new listening mode session.

        Args:
            conversation_id: Conversation UUID

        Returns:
            Session ID of created session
        """
        async with self.session_maker() as session:
            listening_session = ListeningModeSession(
                conversation_id=str(conversation_id),
                started_at=datetime.now(timezone.utc),
                auto_queries_count=0,
                opportunities_detected=0,
                products_suggested=json.dumps([]),
                orders_tracked=json.dumps([]),
            )
            session.add(listening_session)
            await session.commit()
            await session.refresh(listening_session)

            logger.info(
                "listening_mode_session_created",
                conversation_id=str(conversation_id),
                session_id=listening_session.id,
            )

            return listening_session.id

    async def get_active_listening_mode_session(
        self, conversation_id: UUID
    ) -> ListeningModeSession | None:
        """Get active listening mode session (ended_at is null).

        Args:
            conversation_id: Conversation UUID

        Returns:
            ListeningModeSession if active, None otherwise
        """
        async with self.session_maker() as session:
            stmt = (
                select(ListeningModeSession)
                .where(ListeningModeSession.conversation_id == str(conversation_id))
                .where(ListeningModeSession.ended_at.is_(None))
                .order_by(ListeningModeSession.started_at.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def update_listening_mode_session(
        self, session_id: int, **updates
    ) -> None:
        """Update listening mode session fields.

        Args:
            session_id: Session ID
            **updates: Fields to update (auto_queries_count, opportunities_detected, etc.)
        """
        async with self.session_maker() as session:
            stmt = (
                select(ListeningModeSession)
                .where(ListeningModeSession.id == session_id)
            )
            result = await session.execute(stmt)
            listening_session = result.scalar_one_or_none()

            if listening_session:
                for key, value in updates.items():
                    setattr(listening_session, key, value)

                await session.commit()

                logger.info(
                    "listening_mode_session_updated",
                    session_id=session_id,
                    updates=list(updates.keys()),
                )

    async def end_listening_mode_session(self, session_id: int) -> None:
        """End listening mode session by setting ended_at timestamp.

        Args:
            session_id: Session ID
        """
        async with self.session_maker() as session:
            stmt = (
                select(ListeningModeSession)
                .where(ListeningModeSession.id == session_id)
            )
            result = await session.execute(stmt)
            listening_session = result.scalar_one_or_none()

            if listening_session:
                listening_session.ended_at = datetime.now(timezone.utc)
                await session.commit()

                logger.info(
                    "listening_mode_session_ended",
                    session_id=session_id,
                    conversation_id=listening_session.conversation_id,
                )

    async def append_to_session_tracking(
        self, session_id: int, field: str, items: list[dict]
    ) -> None:
        """Append items to session tracking lists (products_suggested or orders_tracked).

        Args:
            session_id: Session ID
            field: Field name ('products_suggested' or 'orders_tracked')
            items: List of dict items to append
        """
        async with self.session_maker() as session:
            stmt = (
                select(ListeningModeSession)
                .where(ListeningModeSession.id == session_id)
            )
            result = await session.execute(stmt)
            listening_session = result.scalar_one_or_none()

            if listening_session:
                # Get current list from JSON field
                current_json = getattr(listening_session, field)
                current_list = json.loads(current_json) if current_json else []

                # Append new items
                current_list.extend(items)

                # Save back as JSON
                setattr(listening_session, field, json.dumps(current_list))

                await session.commit()

                logger.info(
                    "session_tracking_updated",
                    session_id=session_id,
                    field=field,
                    items_added=len(items),
                )

    async def get_recent_transcript_window(
        self, conversation_id: UUID, seconds: int = 45
    ) -> list[dict[str, Any]]:
        """Get transcript lines from the last N seconds as dicts.

        Used by OpportunityDetector for lightweight transcript analysis.
        Uses timestamp field (conversation time) to filter lines.

        Args:
            conversation_id: Conversation UUID
            seconds: Number of seconds to look back (default 45 for OpportunityDetector)

        Returns:
            List of transcript line dicts with speaker, text, timestamp
        """
        async with self.session_maker() as session:
            cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=seconds)

            stmt = (
                select(TranscriptLineModel)
                .where(TranscriptLineModel.conversation_id == str(conversation_id))
                .where(TranscriptLineModel.timestamp >= cutoff_time)
                .order_by(TranscriptLineModel.timestamp.asc())
            )

            result = await session.execute(stmt)
            lines = result.scalars().all()

            return [
                {
                    "speaker": line.speaker,
                    "text": line.text,
                    "timestamp": line.timestamp,
                }
                for line in lines
            ]

    # ===== Dashboard Data Retrieval Methods (Phase 10) =====

    async def get_compliance_attempts(
        self, conversation_id: UUID
    ) -> list[ComplianceDetectionAttempt]:
        """Retrieve all compliance detection attempts for a conversation.

        Args:
            conversation_id: Conversation UUID

        Returns:
            List of ComplianceDetectionAttempt records ordered by detected_at
        """
        async with self.session_maker() as session:
            stmt = (
                select(ComplianceDetectionAttempt)
                .where(ComplianceDetectionAttempt.conversation_id == str(conversation_id))
                .order_by(ComplianceDetectionAttempt.detected_at)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_content_edits(
        self, conversation_id: UUID
    ) -> list:
        """Retrieve all content edits for a conversation.

        Args:
            conversation_id: Conversation UUID

        Returns:
            List of ContentEdit records ordered by edited_at
        """
        from app.models.domain import ContentEdit

        async with self.session_maker() as session:
            stmt = (
                select(ContentEdit)
                .where(ContentEdit.conversation_id == str(conversation_id))
                .order_by(ContentEdit.edited_at)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_disposition_suggestions(
        self, conversation_id: UUID
    ) -> list[DispositionSuggestion]:
        """Retrieve all disposition suggestions for a conversation.

        Args:
            conversation_id: Conversation UUID

        Returns:
            List of DispositionSuggestion records ordered by rank
        """
        async with self.session_maker() as session:
            stmt = (
                select(DispositionSuggestion)
                .where(DispositionSuggestion.conversation_id == str(conversation_id))
                .order_by(DispositionSuggestion.rank)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_listening_mode_sessions(
        self, conversation_id: UUID
    ) -> list[ListeningModeSession]:
        """Retrieve all listening mode sessions for a conversation.

        Args:
            conversation_id: Conversation UUID

        Returns:
            List of ListeningModeSession records ordered by started_at
        """
        async with self.session_maker() as session:
            stmt = (
                select(ListeningModeSession)
                .where(ListeningModeSession.conversation_id == str(conversation_id))
                .order_by(ListeningModeSession.started_at)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_crm_field_extractions(
        self, conversation_id: UUID
    ) -> list[CRMFieldExtraction]:
        """Retrieve all CRM field extractions for a conversation.

        Args:
            conversation_id: Conversation UUID

        Returns:
            List of CRMFieldExtraction records ordered by extracted_at
        """
        async with self.session_maker() as session:
            stmt = (
                select(CRMFieldExtraction)
                .where(CRMFieldExtraction.conversation_id == str(conversation_id))
                .order_by(CRMFieldExtraction.extracted_at)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_all_final_transcript_lines(
        self, conversation_id: UUID
    ) -> list[dict[str, Any]]:
        """Get all final transcript lines for conversation (full context).

        Returns complete conversation history for LLM context.
        Used by utterance-based opportunity detection to provide full
        conversation context instead of sliding window.

        Filters for is_final=True to exclude interim word-streaming updates.

        Args:
            conversation_id: Conversation UUID

        Returns:
            List of dicts: {speaker, text, timestamp, sequence_number}
            Ordered by sequence_number ascending.
        """
        async with self.session_maker() as session:
            stmt = (
                select(TranscriptLineModel)
                .where(
                    TranscriptLineModel.conversation_id == str(conversation_id),
                    TranscriptLineModel.is_final == True,
                )
                .order_by(TranscriptLineModel.sequence_number.asc())
            )
            result = await session.execute(stmt)
            lines = result.scalars().all()

            return [
                {
                    "speaker": line.speaker,
                    "text": line.text,
                    "timestamp": line.timestamp.isoformat(),
                    "sequence_number": line.sequence_number,
                }
                for line in lines
            ]
