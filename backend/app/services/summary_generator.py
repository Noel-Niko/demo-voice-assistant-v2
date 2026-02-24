"""Summary generator service using OpenAI for streaming summarization.

Generates rolling summaries every N seconds with token-by-token streaming.
Follows Single Responsibility Principle - only handles summary generation.
"""
import asyncio
import time
from uuid import UUID

from openai import AsyncOpenAI

from app.services.event_bus import Event, InMemoryEventBus
from app.repositories.conversation_repository import ConversationRepository
from app.utils.cost import estimate_cost

import structlog

logger = structlog.get_logger(__name__)


class SummaryGenerator:
    """Generates rolling LLM summaries with OpenAI streaming.

    Subscribes to transcript.word.final events and generates summaries periodically.
    Uses rolling context (previous summary + new transcript) for token efficiency.

    Follows Observer Pattern (subscribes to events) and Lazy Initialization Pattern.
    """

    def __init__(
        self,
        repository: ConversationRepository,
        event_bus: InMemoryEventBus,
        api_key: str,
        model: str = "gpt-3.5-turbo",
        interval_seconds: int = 30,
    ) -> None:
        """Initialize summary generator.

        Args:
            repository: Conversation repository
            event_bus: Event bus for subscribing/publishing
            api_key: OpenAI API key
            model: OpenAI model to use (default: gpt-3.5-turbo)
            interval_seconds: Seconds between summaries (default: 30)
        """
        self.repository = repository
        self.event_bus = event_bus
        self.model = model
        self._reasoning_effort: str | None = None
        self.default_interval = interval_seconds
        self._api_key = api_key
        self.client: AsyncOpenAI | None = None  # Lazy initialization
        self._active_tasks: dict[UUID, asyncio.Task] = {}
        self._intervals: dict[UUID, int] = {}  # Per-conversation intervals

        # Subscribe to events
        event_bus.subscribe("transcript.word.final", self._on_transcript_word_final)
        event_bus.subscribe("streaming.complete", self._on_streaming_complete)

        logger.info(
            "summary_generator_initialized",
            model=model,
            interval=interval_seconds,
        )

    def get_interval(self, conversation_id: UUID) -> int:
        """Get current interval for a conversation.

        Args:
            conversation_id: Conversation UUID

        Returns:
            Interval in seconds
        """
        return self._intervals.get(conversation_id, self.default_interval)

    def set_interval(self, conversation_id: UUID, interval_seconds: int) -> None:
        """Update summary interval for a conversation.

        Args:
            conversation_id: Conversation UUID
            interval_seconds: New interval in seconds
        """
        self._intervals[conversation_id] = interval_seconds
        logger.info(
            "summary_interval_updated",
            conversation_id=str(conversation_id),
            interval=interval_seconds,
        )

    def set_model(self, model: str, reasoning_effort: str | None = None) -> None:
        """Update the LLM model used for summary generation.

        Args:
            model: OpenAI model name
            reasoning_effort: Optional reasoning effort level
        """
        self.model = model
        self._reasoning_effort = reasoning_effort
        logger.info(
            "summary_generator_model_updated",
            model=model,
            reasoning_effort=reasoning_effort,
        )

    def _get_current_model_config(self) -> tuple[str, str | None]:
        """Get current model config atomically.

        Returns model and reasoning_effort as a tuple to avoid race conditions
        when model is changed mid-operation.

        Returns:
            Tuple of (model, reasoning_effort)
        """
        return (self.model, self._reasoning_effort)

    # Reasoning models (GPT-5, o1-*) share max_completion_tokens between
    # internal reasoning and visible output. Without a multiplier, the model
    # exhausts its budget on reasoning and produces empty output.
    REASONING_TOKEN_MULTIPLIER = 4

    def _build_api_kwargs(self, base_temp: float, base_max_tokens: int, model: str, reasoning_effort: str | None) -> dict:
        """Build API kwargs based on model type.

        o1-family models have different parameter requirements:
        - Use reasoning_effort instead of temperature
        - Use max_completion_tokens instead of max_tokens
        - max_completion_tokens is multiplied by REASONING_TOKEN_MULTIPLIER
          because reasoning tokens consume part of the budget

        Args:
            base_temp: Default temperature for non-o1 models
            base_max_tokens: Max tokens for response
            model: Model name to use (captured atomically)
            reasoning_effort: Reasoning effort level (captured atomically)

        Returns:
            Dict of API kwargs compatible with the current model
        """
        is_o1_model = model.startswith("o1-") or model == "gpt-5"

        kwargs = {
            "model": model,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        if is_o1_model:
            kwargs["max_completion_tokens"] = base_max_tokens * self.REASONING_TOKEN_MULTIPLIER
            if reasoning_effort is not None:
                kwargs["reasoning_effort"] = reasoning_effort
        else:
            kwargs["max_tokens"] = base_max_tokens
            kwargs["temperature"] = base_temp

        return kwargs

    def _ensure_client(self) -> AsyncOpenAI:
        """Lazy initialization of OpenAI client.

        Returns:
            Initialized AsyncOpenAI client
        """
        if not self.client:
            self.client = AsyncOpenAI(api_key=self._api_key, timeout=60.0)  # 60 second timeout
            logger.info("openai_client_initialized")
        return self.client

    async def _on_transcript_word_final(self, event: Event) -> None:
        """Handle transcript.word.final event by starting periodic summarization.

        Args:
            event: transcript.word.final event
        """
        conversation_id = UUID(event.conversation_id)

        # Start periodic summarization on first batch
        if conversation_id not in self._active_tasks:
            task = asyncio.create_task(
                self._periodic_summarize(conversation_id)
            )
            self._active_tasks[conversation_id] = task

            logger.info(
                "periodic_summarization_started",
                conversation_id=str(conversation_id),
                interval=self.get_interval(conversation_id),
            )

    async def _periodic_summarize(self, conversation_id: UUID) -> None:
        """Periodically generate summaries for conversation.

        Runs as background task, generating summary every N seconds.
        Interval can be updated dynamically via set_interval().

        Uses 1-second sleep increments to allow immediate response to interval changes.

        Args:
            conversation_id: Conversation UUID
        """
        try:
            elapsed = 0
            target_interval = self.get_interval(conversation_id)

            while True:
                # Sleep for 1 second (allows responsive interval changes)
                await asyncio.sleep(1)
                elapsed += 1

                # Check if conversation still active
                if conversation_id not in self._active_tasks:
                    break

                # Check if interval changed
                current_interval = self.get_interval(conversation_id)
                if current_interval != target_interval:
                    logger.info(
                        "summary_interval_changed_during_wait",
                        conversation_id=str(conversation_id),
                        old_interval=target_interval,
                        new_interval=current_interval,
                        elapsed=elapsed,
                    )
                    # If new interval is shorter and we've already waited long enough, generate now
                    if elapsed >= current_interval:
                        logger.info(
                            "generating_summary_immediately_due_to_interval_change",
                            conversation_id=str(conversation_id),
                        )
                        try:
                            await self._generate_summary(conversation_id)
                        except Exception as e:
                            logger.error(
                                "summary_generation_failed_continuing",
                                conversation_id=str(conversation_id),
                                error=str(e),
                                exc_info=True,
                            )
                        elapsed = 0
                        target_interval = current_interval
                        continue
                    # Otherwise, adjust target and continue waiting
                    target_interval = current_interval

                # Check if it's time to generate
                if elapsed >= target_interval:
                    try:
                        await self._generate_summary(conversation_id)
                    except Exception as e:
                        logger.error(
                            "summary_generation_failed_continuing",
                            conversation_id=str(conversation_id),
                            error=str(e),
                            exc_info=True,
                        )
                    elapsed = 0
                    target_interval = self.get_interval(conversation_id)

        except asyncio.CancelledError:
            logger.info(
                "periodic_summarization_cancelled",
                conversation_id=str(conversation_id),
            )
            raise

    async def _generate_summary(self, conversation_id: UUID) -> None:
        """Generate and stream summary for conversation.

        Uses rolling context: previous summary + new transcript lines.

        Args:
            conversation_id: Conversation UUID
        """
        # Capture model config atomically at the start to avoid race conditions
        # when model changes mid-operation
        model, reasoning_effort = self._get_current_model_config()

        # Get recent transcript lines (last N seconds)
        recent_lines = await self.repository.get_recent_transcript_lines(
            conversation_id,
            seconds=self.get_interval(conversation_id),
        )

        if not recent_lines:
            logger.debug(
                "no_recent_lines_for_summary",
                conversation_id=str(conversation_id),
            )
            return

        # Get previous summary for rolling context
        previous_summary = await self.repository.get_latest_summary(conversation_id)

        # Build prompt
        transcript_text = "\n".join(
            [f"{line.speaker.upper()}: {line.text}" for line in recent_lines]
        )

        # Research-backed structured format for real-time summaries
        # Source: project_research/summary-formatting-implementation-guide.md
        system_prompt = (
            "You are a real-time note-taker for a customer service agent during a live conversation. "
            "Your output appears in a small sidebar panel that the agent glances at while multitasking.\n\n"
            "RULES:\n"
            "- Use the EXACT section headers with bold markdown: **CUSTOMER INTENT:**, **KEY DETAILS:**, **ACTIONS TAKEN:**, **OPEN ITEMS:**\n"
            "- CRITICAL: Headers MUST have double asterisks (**HEADER:**) for proper formatting\n"
            "- Telegraphic style: no articles (a, the), no filler words, no hedging\n"
            "- Each bullet under 80 characters\n"
            "- KEY DETAILS as label: value pairs\n"
            "- ACTIONS TAKEN must be concrete past-tense actions from the transcript (e.g., 'Verified account status', 'Issued refund #12345')\n"
            "- NEVER use generic prescriptive statements (e.g., 'Address concerns', 'Provide assistance')\n"
            "- OPEN ITEMS only for genuinely unresolved issues; omit section if none\n\n"
            "CRITICAL CONCISENESS RULES (strictly enforced):\n"
            "- **CUSTOMER INTENT:** 1 line only (no bullets)\n"
            "- **KEY DETAILS:** 3 bullets maximum\n"
            "- **ACTIONS TAKEN:** 4 bullets maximum - consolidate related actions into single bullets\n"
            "- **OPEN ITEMS:** 2 bullets maximum or omit if none\n"
            "- TOTAL LIMIT: 10 bullets maximum across entire summary\n"
            "- Merge related items instead of listing separately"
        )

        if previous_summary:
            # Rolling update: consolidate for conciseness
            user_prompt = (
                f"PREVIOUS SUMMARY:\n{previous_summary.summary_text}\n\n"
                f"NEW TRANSCRIPT SINCE LAST UPDATE:\n{transcript_text}\n\n"
                "Update the summary. RULES:\n"
                "- Keep the EXACT format: **CUSTOMER INTENT:**, **KEY DETAILS:**, **ACTIONS TAKEN:**, **OPEN ITEMS:** (with double asterisks)\n"
                "- **CUSTOMER INTENT:** only change if intent genuinely shifted\n"
                "- **KEY DETAILS:** add new entities, update changed values, keep unchanged ones. MAX 3 bullets.\n"
                "- **ACTIONS TAKEN:** Extract concrete past-tense actions from NEW TRANSCRIPT (e.g., 'Checked order status', 'Sent password reset link'). "
                "Use specific verbs (verified, updated, issued, sent). State what HAS ALREADY been done. "
                "Consolidate with existing actions. MAX 4 bullets total.\n"
                "- **OPEN ITEMS:** add new unresolved items, remove resolved items. MAX 2 bullets or omit if none.\n"
                "- ENFORCE: 10 bullet maximum across entire summary. Consolidate ruthlessly.\n\n"
                "Output the full updated summary with bold headers (**HEADER:**):\n"
            )
        else:
            # First summary: establish initial structure
            user_prompt = (
                f"TRANSCRIPT:\n{transcript_text}\n\n"
                "Generate a scannable summary using this exact format:\n\n"
                "**CUSTOMER INTENT:** <one line — what the customer needs>\n\n"
                "**KEY DETAILS:**\n"
                "• <label>: <value> (MAX 3 bullets)\n\n"
                "**ACTIONS TAKEN:**\n"
                "• <concrete past-tense action from transcript> (e.g., 'Verified account details', 'Updated shipping address')\n"
                "• Use specific verbs: verified, updated, issued, sent, checked, confirmed\n"
                "• State what HAS ALREADY been done'\n"
                "• MAX 4 bullets - consolidate related items\n\n"
                "**OPEN ITEMS:**\n"
                "• <unresolved item> (MAX 2 bullets or omit if none)\n\n"
                "ENFORCE: 10 bullet maximum total. Be ruthlessly concise.\n"
            )

        # Stream from OpenAI
        client = self._ensure_client()

        # Get version number
        version = await self.repository.get_summary_count(conversation_id) + 1

        # Publish start event
        await self.event_bus.publish(
            Event.create(
                event_type="summary.start",
                source="summary_generator",
                data={
                    "conversation_id": str(conversation_id),
                    "version": version,
                },
                conversation_id=str(conversation_id),
            )
        )

        logger.info(
            "generating_summary",
            conversation_id=str(conversation_id),
            version=version,
            line_count=len(recent_lines),
        )

        # Stream tokens from OpenAI (with timing and usage tracking)
        full_text = ""
        total_tokens = 0
        start_time = time.monotonic()

        try:
            # Use captured model config to prevent race conditions
            api_kwargs = self._build_api_kwargs(
                base_temp=0.3,
                base_max_tokens=500,
                model=model,
                reasoning_effort=reasoning_effort
            )
            async with await client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                **api_kwargs
            ) as stream:
                async for chunk in stream:
                    # Capture token usage from final chunk
                    if hasattr(chunk, 'usage') and chunk.usage:
                        total_tokens = chunk.usage.total_tokens

                    if chunk.choices and chunk.choices[0].delta.content:
                        token = chunk.choices[0].delta.content
                        full_text += token

                        # Publish token event
                        await self.event_bus.publish(
                            Event.create(
                                event_type="summary.token",
                                source="summary_generator",
                                data={
                                    "conversation_id": str(conversation_id),
                                    "token": token,
                                    "version": version,
                                },
                                conversation_id=str(conversation_id),
                            )
                        )

            # Calculate latency
            latency_ms = int((time.monotonic() - start_time) * 1000)

            # Save to database
            await self.repository.save_summary(
                conversation_id,
                version,
                full_text.strip(),
                len(recent_lines),
            )

            # Track AI costs (fire-and-forget)
            try:
                await self.repository.save_ai_interaction(
                    conversation_id=conversation_id,
                    interaction_type="summary",
                    prompt_text=user_prompt[:500],  # Truncate for storage
                    response_text=full_text.strip()[:500],
                    model_name=model,  # Use captured model to avoid race
                    tokens_used=total_tokens,
                    cost_usd=estimate_cost(total_tokens),
                    latency_ms=latency_ms,
                )
            except Exception as tracking_err:
                logger.warning(
                    "summary_ai_interaction_tracking_failed",
                    conversation_id=str(conversation_id),
                    error=str(tracking_err),
                )

            # Publish complete event
            await self.event_bus.publish(
                Event.create(
                    event_type="summary.complete",
                    source="summary_generator",
                    data={
                        "conversation_id": str(conversation_id),
                        "version": version,
                        "summary_text": full_text.strip(),
                    },
                    conversation_id=str(conversation_id),
                )
            )

            logger.info(
                "summary_generated",
                conversation_id=str(conversation_id),
                version=version,
                token_count=len(full_text),
            )

        except Exception as e:
            logger.error(
                "summary_generation_error",
                conversation_id=str(conversation_id),
                error=str(e),
                exc_info=True,
            )

    async def _on_streaming_complete(self, event: Event) -> None:
        """Handle streaming.complete event by stopping summarization.

        Args:
            event: streaming.complete event
        """
        conversation_id = UUID(event.conversation_id)
        await self._stop_summarization(conversation_id)

    async def _stop_summarization(self, conversation_id: UUID) -> None:
        """Stop periodic summarization for conversation.

        Args:
            conversation_id: Conversation UUID
        """
        if conversation_id in self._active_tasks:
            task = self._active_tasks[conversation_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self._active_tasks[conversation_id]

            logger.info(
                "periodic_summarization_stopped",
                conversation_id=str(conversation_id),
            )

    async def shutdown(self) -> None:
        """Shutdown summary generator and cancel all active tasks.

        Should be called during application shutdown before stopping event bus.
        Cancels all periodic summarization tasks to prevent race conditions.
        """
        if not self._active_tasks:
            logger.info("summary_generator_shutdown_no_active_tasks")
            return

        logger.info(
            "summary_generator_shutting_down",
            active_task_count=len(self._active_tasks),
        )

        # Cancel all active tasks
        tasks_to_cancel = list(self._active_tasks.values())
        conversation_ids = list(self._active_tasks.keys())

        for task in tasks_to_cancel:
            task.cancel()

        # Wait for all tasks to complete cancellation
        await asyncio.gather(*tasks_to_cancel, return_exceptions=True)

        # Clear the active tasks dictionary
        self._active_tasks.clear()
        self._intervals.clear()

        logger.info(
            "summary_generator_shutdown_complete",
            cancelled_conversations=len(conversation_ids),
        )
