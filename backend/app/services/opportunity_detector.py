"""Opportunity detection service for listening mode.

Analyzes transcript windows to detect MCP query opportunities using LLM.
Publishes events when high-confidence opportunities are detected.
"""
import asyncio
import json
from typing import Any
from uuid import UUID

from openai import AsyncOpenAI
import structlog

from app.repositories.conversation_repository import ConversationRepository
from app.services.event_bus import EventBus, Event
from app.services.cache import Cache

logger = structlog.get_logger(__name__)


class OpportunityDetector:
    """Detects MCP query opportunities from transcript analysis.

    Supports two modes:
    - Utterance mode (new): Event-driven, analyzes on utterance.complete events
    - Polling mode (legacy): Periodic polling of 45s transcript windows

    Attributes:
        repository: Database repository for transcript access
        event_bus: Event bus for pub/sub
        cache: Cache for deduplication
        api_key: OpenAI API key
        model: LLM model name
        use_utterances: Use utterance-based detection (True) or polling (False)
        analysis_interval: Seconds between analysis runs (polling mode only)
        window_seconds: Transcript window size (polling mode only)
        confidence_threshold: Minimum confidence to publish opportunity
        dedup_ttl: Cache TTL for deduplication in seconds
    """

    def __init__(
        self,
        repository: ConversationRepository,
        event_bus: EventBus,
        cache: Cache,
        api_key: str,
        model: str = "gpt-3.5-turbo",
        confidence_threshold: float = 0.7,
        dedup_ttl: int = 30,
        use_utterances: bool = True,  # NEW: toggle utterance vs polling mode
        # Polling mode parameters (only used if use_utterances=False)
        analysis_interval: int = 5,
        window_seconds: int = 45,
    ):
        """Initialize opportunity detector.

        Args:
            repository: Conversation repository
            event_bus: Event bus for events
            cache: Cache for deduplication
            api_key: OpenAI API key
            model: LLM model name
            confidence_threshold: Minimum confidence (0.0-1.0)
            dedup_ttl: Deduplication TTL in seconds
            use_utterances: Use utterance-based mode (True) or polling (False)
            analysis_interval: Seconds between analysis runs (polling only)
            window_seconds: Transcript window size (polling only)
        """
        self.repository = repository
        self.event_bus = event_bus
        self.cache = cache
        self.api_key = api_key
        self.model = model
        self._reasoning_effort: str | None = None
        self.confidence_threshold = confidence_threshold
        self.dedup_ttl = dedup_ttl
        self.use_utterances = use_utterances
        self.analysis_interval = analysis_interval
        self.window_seconds = window_seconds

        # Lazy-initialized OpenAI client
        self._client: AsyncOpenAI | None = None

        # Per-conversation analysis tasks (polling mode only)
        self._analysis_tasks: dict[UUID, asyncio.Task] = {}

        # Per-conversation utterance analysis tasks (utterance mode)
        # Tracks background tasks spawned by _on_utterance_complete so
        # shutdown() can cancel them and prevent post-bus-stop publishes.
        self._utterance_tasks: dict[UUID, asyncio.Task] = {}

        # Shutdown flag to prevent new work during shutdown
        self._shutting_down = False

        # Subscribe to appropriate events based on mode
        if use_utterances:
            # NEW: Event-driven mode - listen for complete utterances
            self.event_bus.subscribe("utterance.complete", self._on_utterance_complete)
            logger.info(
                "opportunity_detector_initialized",
                mode="utterance_based",
                model=model,
                confidence_threshold=confidence_threshold,
            )
        else:
            # OLD: Polling mode - listen for any transcript update
            self.event_bus.subscribe("transcript.word.final", self._on_transcript_word_final)
            logger.info(
                "opportunity_detector_initialized",
                mode="polling",
                model=model,
                analysis_interval=analysis_interval,
                window_seconds=window_seconds,
                confidence_threshold=confidence_threshold,
            )

    def set_model(self, model: str, reasoning_effort: str | None = None) -> None:
        """Update the LLM model used for opportunity detection.

        Args:
            model: OpenAI model name
            reasoning_effort: Optional reasoning effort level
        """
        self.model = model
        self._reasoning_effort = reasoning_effort
        logger.info(
            "opportunity_detector_model_updated",
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

    def _build_api_kwargs(self, base_temp: float, model: str, reasoning_effort: str | None, response_format: dict | None = None) -> dict:
        """Build API kwargs based on model type.

        o1-family models require reasoning_effort instead of temperature.

        Args:
            base_temp: Default temperature for non-o1 models
            model: Model name to use (captured atomically)
            reasoning_effort: Reasoning effort level (captured atomically)
            response_format: Optional response format dict

        Returns:
            Dict of API kwargs compatible with the current model
        """
        kwargs = {
            "model": model,
        }

        # o1 models (gpt-5, o1-preview, o1-mini) require reasoning_effort instead of temperature
        is_o1_model = model.startswith("o1-") or model == "gpt-5"

        if is_o1_model and reasoning_effort is not None:
            kwargs["reasoning_effort"] = reasoning_effort
        else:
            kwargs["temperature"] = base_temp

        if response_format:
            kwargs["response_format"] = response_format

        return kwargs

    @property
    def client(self) -> AsyncOpenAI:
        """Lazy-initialized OpenAI client."""
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self.api_key, timeout=60.0)  # 60 second timeout
        return self._client

    async def _on_utterance_complete(self, event: Event) -> None:
        """Handle complete utterance event (utterance mode).

        Spawns a background task for analysis to avoid blocking the event bus
        worker loop. The InMemoryEventBus processes events sequentially through
        a single worker — if this handler awaited the slow OpenAI API call
        directly, all subsequent events (transcript, summary, etc.) would be
        blocked until the call completes. For GPT-5 reasoning models, that
        can be 10-60 seconds, causing the frontend to see transcription freeze.

        Args:
            event: Utterance complete event
        """
        if self._shutting_down:
            logger.debug("skipping_utterance_analysis_shutting_down")
            return

        try:
            conversation_id = UUID(event.conversation_id)

            # Spawn analysis as a background task so this handler returns
            # immediately and the event bus can continue dispatching.
            task = asyncio.create_task(
                self._analyze_utterance(conversation_id, event.data)
            )
            self._utterance_tasks[conversation_id] = task

            # Auto-cleanup when task completes
            task.add_done_callback(
                lambda t: self._utterance_tasks.pop(conversation_id, None)
            )

        except Exception as e:
            logger.error(
                "utterance_handling_failed",
                error=str(e),
                exc_info=True,
            )

    async def _analyze_utterance(
        self, conversation_id: UUID, utterance_data: dict
    ) -> None:
        """Run utterance opportunity analysis in background.

        Fetches full conversation transcript and analyzes for opportunities.
        Runs as a background task spawned by _on_utterance_complete.

        Args:
            conversation_id: Conversation UUID
            utterance_data: Utterance event data
        """
        if self._shutting_down:
            return

        try:
            speaker = utterance_data.get("speaker", "")

            logger.info(
                "analyzing_utterance_for_opportunities",
                conversation_id=str(conversation_id),
                speaker=speaker,
                text=utterance_data.get("text", "")[:100],
                word_count=utterance_data.get("word_count"),
            )

            # Get FULL conversation transcript (not just 45s window!)
            transcript_lines = await self.repository.get_all_final_transcript_lines(
                conversation_id=conversation_id
            )

            if not transcript_lines:
                logger.debug(
                    "no_transcript_lines",
                    conversation_id=str(conversation_id),
                )
                return

            # Analyze for opportunities
            opportunity = await self._analyze_for_opportunities(
                conversation_id, transcript_lines
            )

            # Publish if valid opportunity found
            if opportunity:
                await self._publish_opportunity(conversation_id, opportunity)

        except asyncio.CancelledError:
            logger.info(
                "utterance_analysis_cancelled",
                conversation_id=str(conversation_id),
            )
            raise

        except Exception as e:
            logger.error(
                "utterance_analysis_failed",
                conversation_id=str(conversation_id),
                error=str(e),
                exc_info=True,
            )

    async def _on_transcript_word_final(self, event: Event) -> None:
        """Handle transcript word final event.

        Starts periodic analysis task if not already running for this conversation.

        Args:
            event: Transcript word final event
        """
        try:
            conversation_id = UUID(event.conversation_id)

            # Start analysis task if not already running
            if conversation_id not in self._analysis_tasks or self._analysis_tasks[conversation_id].done():
                logger.info(
                    "starting_opportunity_analysis",
                    conversation_id=str(conversation_id)
                )
                task = asyncio.create_task(self._periodic_analyze(conversation_id))
                self._analysis_tasks[conversation_id] = task

        except Exception as e:
            logger.error(
                "transcript_event_handling_failed",
                error=str(e),
                exc_info=True
            )

    async def _periodic_analyze(self, conversation_id: UUID) -> None:
        """Periodically analyze transcript for opportunities.

        Runs every analysis_interval seconds. Gracefully handles errors
        to avoid crashing the analysis loop.

        Args:
            conversation_id: Conversation UUID
        """
        logger.info(
            "periodic_analysis_started",
            conversation_id=str(conversation_id),
            interval_seconds=self.analysis_interval
        )

        while True:
            try:
                # Wait for next analysis cycle
                await asyncio.sleep(self.analysis_interval)

                # Get recent transcript lines
                transcript_lines = await self.repository.get_recent_transcript_window(
                    conversation_id=conversation_id,
                    seconds=self.window_seconds
                )

                # Skip if no transcript content
                if not transcript_lines:
                    logger.debug(
                        "no_transcript_content",
                        conversation_id=str(conversation_id)
                    )
                    continue

                # Analyze for opportunities
                opportunity = await self._analyze_for_opportunities(conversation_id, transcript_lines)

                # Publish if valid opportunity found
                if opportunity:
                    await self._publish_opportunity(conversation_id, opportunity)

            except asyncio.CancelledError:
                logger.info(
                    "periodic_analysis_cancelled",
                    conversation_id=str(conversation_id)
                )
                raise  # Propagate cancellation

            except Exception as e:
                # Log error but continue loop (graceful degradation)
                logger.error(
                    "analysis_cycle_error",
                    conversation_id=str(conversation_id),
                    error=str(e),
                    exc_info=True
                )
                # Don't crash - continue to next cycle

    async def _analyze_for_opportunities(
        self,
        conversation_id: UUID,
        transcript_lines: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Analyze transcript lines for MCP query opportunities.

        Args:
            conversation_id: Conversation UUID
            transcript_lines: Recent transcript lines

        Returns:
            Opportunity dict if detected, None otherwise
        """
        try:
            # Call LLM for opportunity detection
            result = await self._call_llm(transcript_lines)

            # Check if opportunity detected
            if not result.get("opportunity_detected", False):
                return None

            # Check confidence threshold
            confidence = result.get("confidence", 0.0)
            if confidence < self.confidence_threshold:
                logger.debug(
                    "opportunity_below_threshold",
                    conversation_id=str(conversation_id),
                    confidence=confidence,
                    threshold=self.confidence_threshold
                )
                return None

            # Check for duplicate (semantic fingerprint)
            fingerprint = result.get("semantic_fingerprint", "")
            if await self._is_duplicate(conversation_id, fingerprint):
                logger.debug(
                    "opportunity_duplicate_detected",
                    conversation_id=str(conversation_id),
                    fingerprint=fingerprint
                )
                return None

            # Valid opportunity - cache fingerprint
            await self._cache_fingerprint(conversation_id, fingerprint)

            logger.info(
                "opportunity_detected",
                conversation_id=str(conversation_id),
                opportunity_type=result.get("opportunity_type"),
                confidence=confidence,
                query_text=result.get("query_text"),
            )

            return result

        except Exception as e:
            logger.error(
                "opportunity_analysis_failed",
                conversation_id=str(conversation_id),
                error=str(e),
                exc_info=True
            )
            return None

    async def _call_llm(self, transcript_lines: list[dict[str, Any]]) -> dict[str, Any]:
        """Call LLM to analyze transcript for opportunities.

        Args:
            transcript_lines: Recent transcript lines

        Returns:
            LLM response as dict

        Raises:
            Exception: If LLM call fails
        """
        # Capture model config atomically at the start to avoid race conditions
        # when model changes mid-operation
        model, reasoning_effort = self._get_current_model_config()

        # Format transcript for LLM
        transcript_text = "\n".join([
            f"{line['speaker']}: {line['text']}"
            for line in transcript_lines
        ])

        # System prompt for opportunity detection
        system_prompt = """You detect opportunities for automated tool queries in customer service conversations.

OPPORTUNITIES TO DETECT:
- Product Search: "I need a ladder", "find safety gloves", "looking for respirators"
- Order Tracking: "order 771903", "my order status", "where is my shipment"
- Pricing Query: "how much does", "cost of", "price for"
- Availability: "is this in stock", "do you have", "when will it be available"

RESPOND WITH JSON ONLY (no markdown, no extra text):
{
  "opportunity_detected": true/false,
  "opportunity_type": "product_search" | "order_tracking" | "pricing" | "availability",
  "confidence": 0.0-1.0,
  "query_text": "extracted query to execute",
  "reasoning": "brief explanation",
  "semantic_fingerprint": "dedup hash (e.g. 'product_search_ladder_warehouse')"
}

Rules:
- High precision over recall (only detect clear, actionable opportunities)
- Confidence > 0.7 for product mentions without explicit request
- Confidence > 0.9 for explicit requests ("I need", "find me", "order")
- Semantic fingerprint: lowercase, no spaces, captures intent (e.g. "product_search_ladder_warehouse")
- If no clear opportunity, set opportunity_detected to false"""

        user_prompt = f"""Analyze this transcript excerpt and detect MCP query opportunities:

{transcript_text}

Return JSON only."""

        # Call OpenAI API - use captured model config to prevent race conditions
        api_kwargs = self._build_api_kwargs(
            base_temp=0.3,
            model=model,
            reasoning_effort=reasoning_effort,
            response_format={"type": "json_object"}
        )
        response = await self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            **api_kwargs
        )

        # Parse JSON response
        content = response.choices[0].message.content
        if not content:
            return {"opportunity_detected": False}

        result = json.loads(content)
        return result

    async def _is_duplicate(self, conversation_id: UUID, fingerprint: str) -> bool:
        """Check if opportunity fingerprint is duplicate.

        Args:
            conversation_id: Conversation UUID
            fingerprint: Semantic fingerprint

        Returns:
            True if duplicate (cached), False otherwise
        """
        if not fingerprint:
            return False

        cache_key = f"opportunity:{conversation_id}:{fingerprint}"
        cached = await self.cache.get(cache_key)
        return cached is not None

    async def _cache_fingerprint(self, conversation_id: UUID, fingerprint: str) -> None:
        """Cache opportunity fingerprint for deduplication.

        Args:
            conversation_id: Conversation UUID
            fingerprint: Semantic fingerprint
        """
        if not fingerprint:
            return

        cache_key = f"opportunity:{conversation_id}:{fingerprint}"
        await self.cache.set(cache_key, "detected", ttl=self.dedup_ttl)

    async def _publish_opportunity(self, conversation_id: UUID, opportunity: dict[str, Any]) -> None:
        """Publish opportunity detected event.

        Args:
            conversation_id: Conversation UUID
            opportunity: Opportunity dict from LLM
        """
        event = Event.create(
            event_type="listening_mode.opportunity.detected",
            source="opportunity_detector",
            conversation_id=str(conversation_id),
            data={
                "opportunity_type": opportunity.get("opportunity_type"),
                "confidence": opportunity.get("confidence"),
                "query_text": opportunity.get("query_text"),
                "reasoning": opportunity.get("reasoning"),
                "semantic_fingerprint": opportunity.get("semantic_fingerprint"),
            }
        )

        await self.event_bus.publish(event)

        logger.info(
            "opportunity_event_published",
            conversation_id=str(conversation_id),
            opportunity_type=opportunity.get("opportunity_type")
        )

    async def stop_analysis(self, conversation_id: UUID) -> None:
        """Stop opportunity analysis for conversation.

        Args:
            conversation_id: Conversation UUID
        """
        if conversation_id in self._analysis_tasks:
            task = self._analysis_tasks[conversation_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            del self._analysis_tasks[conversation_id]

            logger.info(
                "opportunity_analysis_stopped",
                conversation_id=str(conversation_id)
            )

    async def shutdown(self) -> None:
        """Shutdown opportunity detector and cancel all analysis tasks.

        Should be called during application shutdown before stopping event bus.
        Cancels both periodic analysis tasks and in-flight utterance tasks.
        """
        self._shutting_down = True

        all_tasks = {
            **{f"polling_{k}": v for k, v in self._analysis_tasks.items()},
            **{f"utterance_{k}": v for k, v in self._utterance_tasks.items()},
        }

        if not all_tasks:
            logger.info("opportunity_detector_shutdown_no_active_tasks")
            return

        logger.info(
            "opportunity_detector_shutting_down",
            polling_task_count=len(self._analysis_tasks),
            utterance_task_count=len(self._utterance_tasks),
        )

        tasks_to_cancel = [t for t in all_tasks.values() if not t.done()]

        for task in tasks_to_cancel:
            task.cancel()

        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)

        self._analysis_tasks.clear()
        self._utterance_tasks.clear()

        logger.info("opportunity_detector_shutdown_complete")
