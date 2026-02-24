"""Utterance lifecycle management for listening mode.

Stateful service that accumulates transcript text as it arrives, detects
utterance boundaries using heuristics, and publishes complete utterances
for LLM analysis.

Pattern based on demo_voice_assistant/src/gateway/utterance_manager.py
"""
import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

import structlog

from app.services.event_bus import EventBus, Event
from app.services.utterance_boundary_detector import (
    UtteranceBoundaryDetector,
    BoundaryDecision,
)

logger = structlog.get_logger(__name__)


@dataclass
class UtteranceState:
    """State for an active utterance.

    Tracks accumulated text, timing, and pending finalization tasks
    for a single speaker in a single conversation.
    """

    text: str = ""
    start_time: float | None = None
    last_update_time: float | None = None
    confidence: float = 0.0
    finalize_task: asyncio.Task | None = None
    update_count: int = 0


class UtteranceManager:
    """Manages utterance lifecycle and boundary detection.

    Subscribes to transcript events, accumulates text, detects boundaries
    using UtteranceBoundaryDetector, and publishes complete utterances.

    Each conversation + speaker combination has independent state.
    Utterances are finalized when boundary detector determines completion
    or hard max timeout is reached.

    Attributes:
        event_bus: Event bus for pub/sub
        boundary_detector: Heuristic boundary detection
        short_timeout: Timeout for high-confidence complete utterances
        medium_timeout: Timeout for medium-confidence utterances
        long_timeout: Timeout for low-confidence/incomplete utterances
        hard_max_timeout: Force finalization after this duration
        confidence_high: Threshold for short timeout
        confidence_good: Threshold for medium timeout
    """

    def __init__(
        self,
        event_bus: EventBus,
        boundary_detector: UtteranceBoundaryDetector,
        short_timeout: float,
        medium_timeout: float,
        long_timeout: float,
        hard_max_timeout: float,
        confidence_high: float,
        confidence_good: float,
        semantic_checker: Optional[object] = None,
        semantic_confidence_threshold: float = 0.85,
    ):
        """Initialize utterance manager.

        Args:
            event_bus: Event bus for events
            boundary_detector: Boundary detection service
            short_timeout: High-confidence timeout (seconds)
            medium_timeout: Medium-confidence timeout (seconds)
            long_timeout: Low-confidence timeout (seconds)
            hard_max_timeout: Hard maximum timeout (seconds)
            confidence_high: High confidence threshold
            confidence_good: Good confidence threshold
            semantic_checker: Optional SpacySemanticChecker instance.
                If provided, consulted after heuristics for edge cases.
                Can only delay finalization, never accelerate it.
            semantic_confidence_threshold: Minimum semantic confidence
                for override (default 0.85).
        """
        self.event_bus = event_bus
        self.boundary_detector = boundary_detector
        self.short_timeout = short_timeout
        self.medium_timeout = medium_timeout
        self.long_timeout = long_timeout
        self.hard_max_timeout = hard_max_timeout
        self.confidence_high = confidence_high
        self.confidence_good = confidence_good
        self.semantic_checker = semantic_checker
        self.semantic_confidence_threshold = semantic_confidence_threshold

        # Per-conversation, per-speaker state
        # Key: (conversation_id, speaker)
        self._states: dict[tuple[UUID, str], UtteranceState] = {}

        # Subscribe to transcript events
        self.event_bus.subscribe("transcript.word.interim", self._on_transcript_event)
        self.event_bus.subscribe("transcript.word.final", self._on_transcript_event)

        logger.info(
            "utterance_manager_initialized",
            short_timeout=short_timeout,
            medium_timeout=medium_timeout,
            long_timeout=long_timeout,
            hard_max_timeout=hard_max_timeout,
        )

    async def _on_transcript_event(self, event: Event) -> None:
        """Handle transcript event (interim or final).

        Accumulates text, merges overlapping segments, cancels pending
        finalization, and schedules new finalization if final event.

        Args:
            event: Transcript event (interim or final)
        """
        try:
            conversation_id = UUID(event.conversation_id)
            data = event.data

            speaker = data.get("speaker", "Unknown")
            text = data.get("text", "").strip()
            confidence = float(data.get("confidence", 0.0))
            is_final = data.get("is_final", False)

            # Skip empty text
            if not text:
                return

            # Get or create state for this conversation + speaker
            state_key = (conversation_id, speaker)
            if state_key not in self._states:
                self._states[state_key] = UtteranceState()

            state = self._states[state_key]
            now = time.time()

            # Initialize timing if first update
            if state.start_time is None:
                state.start_time = now

            state.last_update_time = now
            state.update_count += 1

            # Merge new text with existing (handle overlaps)
            state.text = self._merge_transcript_text(state.text, text)
            state.confidence = max(state.confidence, confidence)

            # Cancel pending finalization (new text arrived)
            if state.finalize_task and not state.finalize_task.done():
                state.finalize_task.cancel()
                state.finalize_task = None
                logger.debug(
                    "cancelled_pending_finalization",
                    conversation_id=str(conversation_id),
                    speaker=speaker,
                    update_count=state.update_count,
                )

            # Check hard max timeout
            if state.start_time and (now - state.start_time) >= self.hard_max_timeout:
                logger.info(
                    "hard_max_timeout_reached",
                    conversation_id=str(conversation_id),
                    speaker=speaker,
                    duration=now - state.start_time,
                )
                await self._finalize_now(
                    conversation_id=conversation_id,
                    speaker=speaker,
                    state=state,
                    reason="timeout_hard_max",
                )
                return

            # If final event, schedule boundary check
            if is_final:
                # Use boundary detector to determine timeout
                decision = self.boundary_detector.is_complete(
                    text=state.text, speaker=speaker
                )

                # Determine timeout based on confidence and boundary decision
                timeout = self._determine_timeout(
                    decision=decision, confidence=state.confidence, text=state.text
                )

                logger.debug(
                    "scheduling_finalization",
                    conversation_id=str(conversation_id),
                    speaker=speaker,
                    text=state.text[:100],
                    confidence=state.confidence,
                    boundary_reason=decision.reason,
                    boundary_confidence=decision.confidence,
                    timeout=timeout,
                )

                await self._schedule_finalize(
                    conversation_id=conversation_id,
                    speaker=speaker,
                    state=state,
                    timeout=timeout,
                    decision=decision,
                )

        except Exception as e:
            logger.error(
                "transcript_event_handling_failed", error=str(e), exc_info=True
            )

    def _determine_timeout(
        self, decision: BoundaryDecision, confidence: float, text: str = ""
    ) -> float:
        """Determine finalization timeout based on boundary decision, confidence, and optional semantic analysis.

        After heuristic decision, if semantic_checker is available and
        heuristics say complete, the semantic layer may override to delay
        finalization for incomplete phrases.

        Critical invariant: semantic can only DELAY, never accelerate.

        Args:
            decision: Boundary detection decision
            confidence: Transcript confidence (0.0-1.0)
            text: Utterance text (needed for semantic analysis)

        Returns:
            Timeout in seconds
        """
        # Heuristic-based timeout determination
        if confidence >= self.confidence_high and decision.is_complete:
            timeout = self.short_timeout
        elif confidence >= self.confidence_good and decision.is_complete:
            timeout = self.medium_timeout
        elif not decision.is_complete:
            # Already incomplete — no need to consult semantic
            return self.long_timeout
        else:
            timeout = self.medium_timeout

        # Semantic layer consultation (only when heuristics say complete)
        if self.semantic_checker and text:
            timeout = self._apply_semantic_layer(text=text, timeout=timeout)

        return timeout

    def _apply_semantic_layer(self, *, text: str, timeout: float) -> float:
        """Consult semantic checker and potentially delay finalization.

        Only called when heuristics say complete. If semantic says
        incomplete with high confidence, bumps timeout up.
        If semantic says complete or has low confidence, returns
        the original timeout unchanged.

        Args:
            text: Utterance text to analyze.
            timeout: Heuristic-determined timeout.

        Returns:
            Possibly increased timeout.
        """
        try:
            result = self.semantic_checker.is_complete(text)
        except Exception:
            logger.warning(
                "semantic_checker_error",
                text=text[:100],
                exc_info=True,
            )
            return timeout

        logger.debug(
            "semantic_consultation",
            text=text[:100],
            is_complete=result.is_complete,
            confidence=result.confidence,
            reason=result.reason,
            threshold=self.semantic_confidence_threshold,
            processing_time_ms=result.processing_time_ms,
        )

        if result.confidence < self.semantic_confidence_threshold:
            return timeout

        if not result.is_complete:
            # Semantic says incomplete → delay finalization
            delayed = max(self.medium_timeout, self.long_timeout)
            logger.info(
                "semantic_delay_applied",
                text=text[:100],
                original_timeout=timeout,
                delayed_timeout=delayed,
                semantic_reason=result.reason,
            )
            return delayed

        # Semantic says complete → do NOT accelerate (trust heuristics)
        return timeout

    async def _schedule_finalize(
        self,
        conversation_id: UUID,
        speaker: str,
        state: UtteranceState,
        timeout: float,
        decision: BoundaryDecision,
    ) -> None:
        """Schedule utterance finalization after timeout.

        Creates background task that sleeps for timeout duration,
        then finalizes the utterance if not cancelled.

        Args:
            conversation_id: Conversation UUID
            speaker: Speaker label
            state: Utterance state
            timeout: Timeout duration in seconds
            decision: Boundary decision
        """

        async def _finalize_task():
            try:
                await asyncio.sleep(timeout)

                # Check if this task is still current (not cancelled)
                state_key = (conversation_id, speaker)
                if state_key in self._states:
                    current_state = self._states[state_key]
                    if current_state.finalize_task and not current_state.finalize_task.done():
                        # Still pending, finalize now
                        finalization_reason = self._timeout_to_reason(timeout)
                        await self._finalize_now(
                            conversation_id=conversation_id,
                            speaker=speaker,
                            state=current_state,
                            reason=finalization_reason,
                        )
            except asyncio.CancelledError:
                # Task was cancelled (new text arrived)
                pass
            except Exception as e:
                logger.error(
                    "finalization_task_failed", error=str(e), exc_info=True
                )

        # Create and store finalization task
        state.finalize_task = asyncio.create_task(_finalize_task())

    def _timeout_to_reason(self, timeout: float) -> str:
        """Convert timeout duration to finalization reason.

        Args:
            timeout: Timeout duration

        Returns:
            Finalization reason string
        """
        if timeout <= self.short_timeout + 0.01:
            return "timeout_short"
        elif timeout <= self.medium_timeout + 0.01:
            return "timeout_medium"
        elif timeout <= self.long_timeout + 0.01:
            return "timeout_long"
        else:
            return "timeout_hard_max"

    async def _finalize_now(
        self,
        conversation_id: UUID,
        speaker: str,
        state: UtteranceState,
        reason: str,
    ) -> None:
        """Finalize utterance immediately and publish event.

        Args:
            conversation_id: Conversation UUID
            speaker: Speaker label
            state: Utterance state
            reason: Finalization reason
        """
        text = state.text.strip()
        if not text:
            # Clean up empty state
            state_key = (conversation_id, speaker)
            if state_key in self._states:
                del self._states[state_key]
            return

        # Calculate metrics
        words = text.split()
        word_count = len(words)

        # Get boundary decision for final check
        decision = self.boundary_detector.is_complete(text=text, speaker=speaker)

        logger.info(
            "utterance_finalized",
            conversation_id=str(conversation_id),
            speaker=speaker,
            text=text[:100],
            word_count=word_count,
            confidence=state.confidence,
            boundary_reason=decision.reason,
            finalization_reason=reason,
            update_count=state.update_count,
        )

        # Publish utterance.complete event
        await self.event_bus.publish(
            Event.create(
                event_type="utterance.complete",
                source="utterance_manager",
                conversation_id=str(conversation_id),
                data={
                    "speaker": speaker,
                    "text": text,
                    "word_count": word_count,
                    "confidence": state.confidence,
                    "reason": decision.reason,
                    "finalization_reason": reason,
                },
            )
        )

        # Clean up state
        state_key = (conversation_id, speaker)
        if state_key in self._states:
            del self._states[state_key]

    def _merge_transcript_text(self, existing: str, incoming: str) -> str:
        """Merge overlapping transcript segments.

        Handles cases where ASR updates overlap (e.g., "Hello how" + "how are you").
        Based on demo_voice_assistant pattern.

        Args:
            existing: Existing accumulated text
            incoming: New text to merge

        Returns:
            Merged text
        """
        a = existing.strip()
        b = incoming.strip()

        if not a:
            return b
        if not b:
            return a

        # Check for prefix/suffix relationships
        if b.startswith(a):
            return b
        if a.startswith(b):
            return a
        if b in a:
            return a
        if a in b:
            return b

        # Check for token-level overlap
        a_tokens = a.split()
        b_tokens = b.split()
        max_overlap = min(len(a_tokens), len(b_tokens))

        for k in range(max_overlap, 0, -1):
            if a_tokens[-k:] == b_tokens[:k]:
                # Found overlap, merge
                merged = a_tokens + b_tokens[k:]
                return " ".join(merged).strip()

        # No overlap, concatenate
        return f"{a} {b}".strip()

    async def shutdown(self) -> None:
        """Cancel all pending finalization tasks.

        Should be called during application shutdown to clean up.
        """
        logger.info("shutting_down_utterance_manager", pending_states=len(self._states))

        for state_key, state in list(self._states.items()):
            if state.finalize_task and not state.finalize_task.done():
                state.finalize_task.cancel()

        self._states.clear()
        logger.info("utterance_manager_shutdown_complete")
