"""Listening mode manager for session lifecycle and auto-query execution.

Manages listening mode sessions and orchestrates automated MCP queries
when opportunities are detected.
"""
import asyncio
from typing import Any
from uuid import UUID

import structlog

from app.repositories.conversation_repository import ConversationRepository
from app.services.event_bus import EventBus, Event
from app.services.mcp_orchestrator import MCPOrchestrator
from app.services.cache import Cache

logger = structlog.get_logger(__name__)


class ListeningModeManager:
    """Manages listening mode sessions and auto-query execution.

    Subscribes to opportunity.detected events and orchestrates automated
    MCP queries. Tracks session lifecycle and metrics.

    Attributes:
        repository: Database repository
        event_bus: Event bus for pub/sub
        mcp_orchestrator: MCP orchestrator for query execution
        cache: Cache for state management
    """

    def __init__(
        self,
        repository: ConversationRepository,
        event_bus: EventBus,
        mcp_orchestrator: MCPOrchestrator,
        cache: Cache,
    ):
        """Initialize listening mode manager.

        Args:
            repository: Conversation repository
            event_bus: Event bus for events
            mcp_orchestrator: MCP orchestrator
            cache: Cache for state
        """
        self.repository = repository
        self.event_bus = event_bus
        self.mcp_orchestrator = mcp_orchestrator
        self.cache = cache
        self._shutting_down = False
        self._background_tasks: set[asyncio.Task] = set()  # Track auto-query tasks

        # Subscribe to opportunity events
        self.event_bus.subscribe(
            "listening_mode.opportunity.detected",
            self._on_opportunity_detected
        )

        logger.info("listening_mode_manager_initialized")

    async def start_session(self, conversation_id: UUID) -> int:
        """Start a new listening mode session.

        Args:
            conversation_id: Conversation UUID

        Returns:
            Session ID of created session
        """
        # Check if session already exists
        existing_session = await self.repository.get_active_listening_mode_session(
            conversation_id
        )

        if existing_session:
            logger.info(
                "listening_mode_session_already_active",
                conversation_id=str(conversation_id),
                session_id=existing_session.id
            )
            return existing_session.id

        # Create new session
        session_id = await self.repository.create_listening_mode_session(conversation_id)

        # Publish session started event
        event = Event.create(
            event_type="listening_mode.session.started",
            source="listening_mode_manager",
            conversation_id=str(conversation_id),
            data={"session_id": session_id}
        )
        await self.event_bus.publish(event)

        logger.info(
            "listening_mode_session_started",
            conversation_id=str(conversation_id),
            session_id=session_id
        )

        return session_id

    async def stop_session(self, conversation_id: UUID) -> None:
        """Stop active listening mode session.

        Args:
            conversation_id: Conversation UUID
        """
        # Get active session
        session = await self.repository.get_active_listening_mode_session(conversation_id)

        if not session:
            logger.warning(
                "no_active_listening_mode_session",
                conversation_id=str(conversation_id)
            )
            return

        # End session
        await self.repository.end_listening_mode_session(session.id)

        # Publish session ended event
        event = Event.create(
            event_type="listening_mode.session.ended",
            source="listening_mode_manager",
            conversation_id=str(conversation_id),
            data={
                "session_id": session.id,
                "auto_queries_count": session.auto_queries_count,
                "opportunities_detected": session.opportunities_detected,
            }
        )
        await self.event_bus.publish(event)

        logger.info(
            "listening_mode_session_ended",
            conversation_id=str(conversation_id),
            session_id=session.id,
            auto_queries=session.auto_queries_count,
            opportunities=session.opportunities_detected,
        )

    async def _on_opportunity_detected(self, event: Event) -> None:
        """Handle opportunity detected event.

        Creates session if needed and executes auto-query.

        Args:
            event: Opportunity detected event
        """
        try:
            # Skip processing if shutting down
            if self._shutting_down:
                logger.debug("skipping_opportunity_shutting_down")
                return

            conversation_id = UUID(event.conversation_id)
            opportunity = event.data

            logger.info(
                "opportunity_received",
                conversation_id=str(conversation_id),
                opportunity_type=opportunity.get("opportunity_type"),
                confidence=opportunity.get("confidence"),
            )

            # Ensure session exists (create if needed)
            session = await self.repository.get_active_listening_mode_session(conversation_id)
            if not session:
                session_id = await self.start_session(conversation_id)
                # Refresh session object
                session = await self.repository.get_active_listening_mode_session(conversation_id)

            # Execute auto-query in background task to avoid blocking (with tracking)
            task = asyncio.create_task(
                self._execute_auto_query(conversation_id, session.id, opportunity)
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)  # Auto-remove when done

        except Exception as e:
            logger.error(
                "opportunity_handling_failed",
                error=str(e),
                exc_info=True
            )

    async def _execute_auto_query(
        self,
        conversation_id: UUID,
        session_id: int,
        opportunity: dict[str, Any]
    ) -> None:
        """Execute automated MCP query for opportunity.

        Args:
            conversation_id: Conversation UUID
            session_id: Listening mode session ID
            opportunity: Opportunity data
        """
        # Skip if shutting down
        if self._shutting_down:
            logger.debug("skipping_auto_query_shutting_down")
            return

        query_text = opportunity.get("query_text", "")
        opportunity_type = opportunity.get("opportunity_type", "unknown")

        try:
            # Publish query started event
            started_event = Event.create(
                event_type="listening_mode.query.started",
                source="listening_mode_manager",
                conversation_id=str(conversation_id),
                data={
                    "query_text": query_text,
                    "opportunity_type": opportunity_type,
                    "session_id": session_id,
                }
            )
            await self.event_bus.publish(started_event)

            logger.info(
                "auto_query_started",
                conversation_id=str(conversation_id),
                query_text=query_text,
                opportunity_type=opportunity_type,
            )

            # Execute MCP query (let orchestrator select best tool)
            result = await self.mcp_orchestrator.query(
                user_query=query_text,
                preferred_server=None,  # Let LLM select
            )

            # Log agent interaction
            import json
            await self.repository.save_agent_interaction(
                conversation_id=conversation_id,
                interaction_type="mcp_query_auto",
                query_text=query_text,
                context_data=json.dumps({
                    "opportunity_type": opportunity_type,
                    "tool_used": result.get("tool_used"),
                    "mcp_server_used": result.get("server_used"),
                }),
            )

            # Get current session state
            session = await self.repository.get_active_listening_mode_session(conversation_id)
            if session:
                # Increment metrics
                new_auto_queries = session.auto_queries_count + 1
                new_opportunities = session.opportunities_detected + 1

                # Update session
                await self.repository.update_listening_mode_session(
                    session_id=session_id,
                    auto_queries_count=new_auto_queries,
                    opportunities_detected=new_opportunities,
                )

            # Publish query complete event
            complete_event = Event.create(
                event_type="listening_mode.query.complete",
                source="listening_mode_manager",
                conversation_id=str(conversation_id),
                data={
                    "query_text": query_text,
                    "opportunity_type": opportunity_type,
                    "session_id": session_id,
                    "result": result,
                }
            )
            await self.event_bus.publish(complete_event)

            logger.info(
                "auto_query_completed",
                conversation_id=str(conversation_id),
                query_text=query_text,
                success=result.get("success", False),
                tool_used=result.get("tool_used"),
            )

        except asyncio.CancelledError:
            logger.debug(
                "auto_query_cancelled",
                conversation_id=str(conversation_id),
                query_text=query_text,
            )
            raise  # Re-raise to properly cancel the task

        except Exception as e:
            logger.error(
                "auto_query_failed",
                conversation_id=str(conversation_id),
                query_text=query_text,
                error=str(e),
                exc_info=True
            )

            # Still increment opportunities_detected (opportunity was valid even if query failed)
            session = await self.repository.get_active_listening_mode_session(conversation_id)
            if session:
                await self.repository.update_listening_mode_session(
                    session_id=session_id,
                    opportunities_detected=session.opportunities_detected + 1,
                )

            # Publish error event
            error_event = Event.create(
                event_type="listening_mode.query.error",
                source="listening_mode_manager",
                conversation_id=str(conversation_id),
                data={
                    "query_text": query_text,
                    "opportunity_type": opportunity_type,
                    "session_id": session_id,
                    "error": str(e),
                }
            )
            await self.event_bus.publish(error_event)

    async def shutdown(self) -> None:
        """Shutdown listening mode manager.

        Should be called during application shutdown before stopping event bus.
        Cancels all background auto-query tasks to prevent them from trying to
        use the event bus or HTTP clients after they've been shut down.
        """
        self._shutting_down = True

        if not self._background_tasks:
            logger.info("listening_mode_manager_shutdown_no_tasks")
            return

        logger.info(
            "listening_mode_manager_shutting_down",
            active_task_count=len(self._background_tasks),
        )

        # Cancel all background tasks
        tasks_to_cancel = list(self._background_tasks)
        for task in tasks_to_cancel:
            task.cancel()

        # Wait for all tasks to complete cancellation (with timeout)
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)

        # Clear the set
        self._background_tasks.clear()

        logger.info(
            "listening_mode_manager_shutdown_complete",
            cancelled_task_count=len(tasks_to_cancel),
        )
