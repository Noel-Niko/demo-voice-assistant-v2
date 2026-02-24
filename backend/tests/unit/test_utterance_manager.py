"""Unit tests for UtteranceManager.

Following TDD: Tests written FIRST, then implementation.

UtteranceManager accumulates transcript text, detects utterance boundaries,
and publishes complete utterances for LLM analysis.
"""
import asyncio
import pytest
import pytest_asyncio
from uuid import UUID, uuid4
from datetime import datetime

from app.services.utterance_manager import UtteranceManager
from app.services.utterance_boundary_detector import UtteranceBoundaryDetector, BoundaryDecision
from app.services.event_bus import Event, InMemoryEventBus


@pytest_asyncio.fixture
async def event_bus():
    """Create event bus for testing."""
    bus = InMemoryEventBus()
    await bus.start()
    yield bus
    await bus.stop()


@pytest.fixture
def boundary_detector():
    """Create boundary detector with default settings."""
    return UtteranceBoundaryDetector(
        min_words_complete=4,
        min_words_question=3,
        min_words_command=3,
        confidence_threshold=0.7,
    )


@pytest_asyncio.fixture
async def utterance_manager(event_bus, boundary_detector):
    """Create utterance manager for testing."""
    manager = UtteranceManager(
        event_bus=event_bus,
        boundary_detector=boundary_detector,
        short_timeout=0.1,  # Fast timeouts for testing
        medium_timeout=0.2,
        long_timeout=0.3,
        hard_max_timeout=0.5,
        confidence_high=0.85,
        confidence_good=0.70,
    )
    yield manager
    # Cleanup
    await manager.shutdown()


@pytest.mark.asyncio
class TestUtteranceManager:
    """Test suite for UtteranceManager."""

    async def test_accumulates_text_from_interim_updates(self, utterance_manager, event_bus):
        """Test that manager accumulates text from interim transcript updates."""
        conversation_id = uuid4()
        utterance_complete_events = []

        # Subscribe to utterance.complete events
        async def capture_event(event: Event):
            utterance_complete_events.append(event)

        event_bus.subscribe("utterance.complete", capture_event)

        # Emit interim updates (simulating word-by-word streaming)
        await event_bus.publish(Event.create(
            event_type="transcript.word.interim",
            source="test",
            conversation_id=str(conversation_id),
            data={
                "speaker": "Customer",
                "text": "I",
                "confidence": 0.6,
                "is_final": False,
            }
        ))
        await asyncio.sleep(0.01)

        await event_bus.publish(Event.create(
            event_type="transcript.word.interim",
            source="test",
            conversation_id=str(conversation_id),
            data={
                "speaker": "Customer",
                "text": "I need",
                "confidence": 0.7,
                "is_final": False,
            }
        ))
        await asyncio.sleep(0.01)

        await event_bus.publish(Event.create(
            event_type="transcript.word.final",
            source="test",
            conversation_id=str(conversation_id),
            data={
                "speaker": "Customer",
                "text": "I need safety gloves",
                "confidence": 0.9,
                "is_final": True,
            }
        ))

        # Wait for finalization
        await asyncio.sleep(0.3)

        # Should have published one utterance.complete event
        assert len(utterance_complete_events) > 0
        event = utterance_complete_events[0]
        assert event.event_type == "utterance.complete"
        assert event.data["text"] == "I need safety gloves"
        assert event.data["speaker"] == "Customer"

    async def test_finalizes_on_short_timeout_high_confidence(self, utterance_manager, event_bus):
        """Test short timeout for high-confidence complete utterances."""
        conversation_id = uuid4()
        utterance_complete_events = []

        def capture_event(event: Event):
            utterance_complete_events.append(event)

        event_bus.subscribe("utterance.complete", capture_event)

        # Emit complete question with high confidence
        await event_bus.publish(Event.create(
            event_type="transcript.word.final",
            source="test",
            conversation_id=str(conversation_id),
            data={
                "speaker": "Customer",
                "text": "Where is my order?",
                "confidence": 0.95,  # High confidence
                "is_final": True,
            }
        ))

        # Should finalize quickly (short timeout = 0.1s)
        await asyncio.sleep(0.2)

        assert len(utterance_complete_events) == 1
        event = utterance_complete_events[0]
        assert event.data["text"] == "Where is my order?"
        assert event.data["confidence"] >= 0.9

    async def test_finalizes_on_hard_max_timeout(self, utterance_manager, event_bus):
        """Test hard max timeout forces finalization."""
        conversation_id = uuid4()
        utterance_complete_events = []

        async def capture_event(event: Event):
            utterance_complete_events.append(event)

        event_bus.subscribe("utterance.complete", capture_event)

        # Emit incomplete phrase (should get long timeout)
        await event_bus.publish(Event.create(
            event_type="transcript.word.final",
            source="test",
            conversation_id=str(conversation_id),
            data={
                "speaker": "Customer",
                "text": "I need a",  # Incomplete
                "confidence": 0.8,
                "is_final": True,
            }
        ))

        # Wait for hard max timeout (0.5s)
        await asyncio.sleep(0.6)

        # Should finalize after hard max
        assert len(utterance_complete_events) == 1
        assert utterance_complete_events[0].data["finalization_reason"] in ["timeout_long", "timeout_hard_max"]

    async def test_cancels_pending_finalization_on_new_text(self, utterance_manager, event_bus):
        """Test that new text cancels pending finalization."""
        conversation_id = uuid4()
        utterance_complete_events = []

        async def capture_event(event: Event):
            utterance_complete_events.append(event)

        event_bus.subscribe("utterance.complete", capture_event)

        # First update
        await event_bus.publish(Event.create(
            event_type="transcript.word.final",
            source="test",
            conversation_id=str(conversation_id),
            data={
                "speaker": "Customer",
                "text": "I need",
                "confidence": 0.7,
                "is_final": True,
            }
        ))
        await asyncio.sleep(0.05)  # Wait a bit but not enough to finalize

        # Second update (should cancel first finalization)
        await event_bus.publish(Event.create(
            event_type="transcript.word.final",
            source="test",
            conversation_id=str(conversation_id),
            data={
                "speaker": "Customer",
                "text": "I need safety gloves",
                "confidence": 0.9,
                "is_final": True,
            }
        ))

        # Wait for finalization
        await asyncio.sleep(0.3)

        # Should only have one event with full text
        assert len(utterance_complete_events) == 1
        assert utterance_complete_events[0].data["text"] == "I need safety gloves"

    async def test_separates_customer_and_agent_utterances(self, utterance_manager, event_bus):
        """Test that manager tracks customer and agent separately."""
        conversation_id = uuid4()
        utterance_complete_events = []

        async def capture_event(event: Event):
            utterance_complete_events.append(event)

        event_bus.subscribe("utterance.complete", capture_event)

        # Emit customer utterance
        await event_bus.publish(Event.create(
            event_type="transcript.word.final",
            source="test",
            conversation_id=str(conversation_id),
            data={
                "speaker": "Customer",
                "text": "I need help with my order",
                "confidence": 0.9,
                "is_final": True,
            }
        ))

        # Emit agent utterance
        await event_bus.publish(Event.create(
            event_type="transcript.word.final",
            source="test",
            conversation_id=str(conversation_id),
            data={
                "speaker": "Agent",
                "text": "Sure I can help with that",
                "confidence": 0.9,
                "is_final": True,
            }
        ))

        # Wait for both to finalize (Agent gets 0.3s timeout + buffer)
        await asyncio.sleep(0.5)

        # Should have two separate utterances
        assert len(utterance_complete_events) == 2
        customer_event = [e for e in utterance_complete_events if e.data["speaker"] == "Customer"][0]
        agent_event = [e for e in utterance_complete_events if e.data["speaker"] == "Agent"][0]

        assert customer_event.data["text"] == "I need help with my order"
        assert agent_event.data["text"] == "Sure I can help with that"

    async def test_merges_overlapping_segments(self, utterance_manager):
        """Test that manager merges overlapping transcript segments."""
        # Test the _merge_transcript_text method directly
        merged = utterance_manager._merge_transcript_text("I need safety", "safety gloves")
        assert merged == "I need safety gloves"

        merged = utterance_manager._merge_transcript_text("Hello how", "how are you")
        assert merged == "Hello how are you"

        # Test prefix relationship
        merged = utterance_manager._merge_transcript_text("Hello", "Hello how are you")
        assert merged == "Hello how are you"

        # Test no overlap
        merged = utterance_manager._merge_transcript_text("Hello", "Goodbye")
        assert merged == "Hello Goodbye"

    async def test_publishes_utterance_complete_event(self, utterance_manager, event_bus):
        """Test that utterance.complete event has correct schema."""
        conversation_id = uuid4()
        utterance_complete_events = []

        def capture_event(event: Event):
            utterance_complete_events.append(event)

        event_bus.subscribe("utterance.complete", capture_event)

        await event_bus.publish(Event.create(
            event_type="transcript.word.final",
            source="test",
            conversation_id=str(conversation_id),
            data={
                "speaker": "Customer",
                "text": "Where is my order?",
                "confidence": 0.9,
                "is_final": True,
            }
        ))

        await asyncio.sleep(0.3)

        assert len(utterance_complete_events) == 1
        event = utterance_complete_events[0]

        # Verify event schema
        assert event.event_type == "utterance.complete"
        assert event.source == "utterance_manager"
        assert event.conversation_id == str(conversation_id)
        assert "speaker" in event.data
        assert "text" in event.data
        assert "word_count" in event.data
        assert "confidence" in event.data
        assert "reason" in event.data
        assert "finalization_reason" in event.data

        assert event.data["speaker"] == "Customer"
        assert event.data["text"] == "Where is my order?"
        assert event.data["word_count"] == 4
        assert event.data["confidence"] > 0

    async def test_cleanup_on_shutdown(self, event_bus, boundary_detector):
        """Test that shutdown cancels all pending tasks."""
        manager = UtteranceManager(
            event_bus=event_bus,
            boundary_detector=boundary_detector,
            short_timeout=1.0,  # Long timeout so it won't fire
            medium_timeout=2.0,
            long_timeout=3.0,
            hard_max_timeout=5.0,
            confidence_high=0.85,
            confidence_good=0.70,
        )

        conversation_id = uuid4()

        # Emit event to start finalization task
        await event_bus.publish(Event.create(
            event_type="transcript.word.final",
            source="test",
            conversation_id=str(conversation_id),
            data={
                "speaker": "Customer",
                "text": "Test",
                "confidence": 0.8,
                "is_final": True,
            }
        ))

        await asyncio.sleep(0.1)

        # Shutdown should cancel pending tasks
        await manager.shutdown()

        # Wait to ensure no events fire after shutdown
        utterance_complete_events = []

        def capture_event(event: Event):
            utterance_complete_events.append(event)

        event_bus.subscribe("utterance.complete", capture_event)

        await asyncio.sleep(0.5)
        assert len(utterance_complete_events) == 0  # No events after shutdown

    async def test_handles_empty_text(self, utterance_manager, event_bus):
        """Test that manager handles empty text gracefully."""
        conversation_id = uuid4()
        utterance_complete_events = []

        def capture_event(event: Event):
            utterance_complete_events.append(event)

        event_bus.subscribe("utterance.complete", capture_event)

        # Emit empty text
        await event_bus.publish(Event.create(
            event_type="transcript.word.final",
            source="test",
            conversation_id=str(conversation_id),
            data={
                "speaker": "Customer",
                "text": "",
                "confidence": 0.9,
                "is_final": True,
            }
        ))

        await asyncio.sleep(0.3)

        # Should not publish utterance for empty text
        assert len(utterance_complete_events) == 0

    async def test_handles_rapid_updates(self, utterance_manager, event_bus):
        """Test that manager handles rapid transcript updates without errors."""
        conversation_id = uuid4()

        # Emit many rapid updates
        for i in range(20):
            await event_bus.publish(Event.create(
                event_type="transcript.word.interim",
                source="test",
                conversation_id=str(conversation_id),
                data={
                    "speaker": "Customer",
                    "text": f"Word {i}",
                    "confidence": 0.8,
                    "is_final": False,
                }
            ))
            await asyncio.sleep(0.01)

        # Final update
        await event_bus.publish(Event.create(
            event_type="transcript.word.final",
            source="test",
            conversation_id=str(conversation_id),
            data={
                "speaker": "Customer",
                "text": "Complete sentence here",
                "confidence": 0.9,
                "is_final": True,
            }
        ))

        await asyncio.sleep(0.3)

        # Should handle without errors (just verify no exceptions)
        # The test passing means no exceptions were raised


# ---------------------------------------------------------------------------
# Semantic Layer Integration Tests (TDD — tests for Step 5)
# ---------------------------------------------------------------------------
from unittest.mock import MagicMock
from app.services.spacy_semantic_checker import CompletenessResult


def _make_semantic_mock(*, is_complete: bool, confidence: float, reason: str) -> MagicMock:
    """Create a mock SpacySemanticChecker that returns a fixed result."""
    mock = MagicMock()
    mock.is_complete.return_value = CompletenessResult(
        is_complete=is_complete,
        confidence=confidence,
        reason=reason,
        processing_time_ms=1.0,
    )
    return mock


@pytest_asyncio.fixture
async def semantic_manager_factory(event_bus, boundary_detector):
    """Factory fixture that creates UtteranceManagers with optional semantic checker."""
    managers = []

    def _create(semantic_checker=None, semantic_confidence_threshold=0.85):
        manager = UtteranceManager(
            event_bus=event_bus,
            boundary_detector=boundary_detector,
            short_timeout=0.1,
            medium_timeout=0.2,
            long_timeout=0.3,
            hard_max_timeout=0.5,
            confidence_high=0.85,
            confidence_good=0.70,
            semantic_checker=semantic_checker,
            semantic_confidence_threshold=semantic_confidence_threshold,
        )
        managers.append(manager)
        return manager

    yield _create

    for m in managers:
        await m.shutdown()


@pytest.mark.asyncio
class TestSemanticLayerIntegration:
    """Tests for optional spaCy semantic layer in UtteranceManager.

    Verifies the critical invariant: semantic can only DELAY finalization,
    never accelerate it.
    """

    async def test_semantic_delays_incomplete_utterance(
        self, semantic_manager_factory, event_bus
    ):
        """Semantic says incomplete with high confidence → timeout bumped up.

        Heuristic sees 'what is the weather' as complete (4+ words, question word).
        Semantic sees it as needing more context (no ?) → delay finalization.
        """
        semantic_mock = _make_semantic_mock(
            is_complete=False, confidence=0.9, reason="incomplete_question"
        )
        manager = semantic_manager_factory(semantic_checker=semantic_mock)

        # Call _determine_timeout directly with a complete heuristic decision
        decision = BoundaryDecision(
            is_complete=True, confidence=0.9, reason="complete_question", word_count=4
        )
        timeout = manager._determine_timeout(
            decision=decision, confidence=0.9, text="what is the weather"
        )

        # Should be bumped to max(medium, long) = long_timeout = 0.3
        assert timeout >= manager.long_timeout
        semantic_mock.is_complete.assert_called_once_with("what is the weather")

    async def test_semantic_does_not_accelerate(
        self, semantic_manager_factory, event_bus
    ):
        """Semantic says complete → timeout unchanged from heuristic.

        Critical invariant: semantic NEVER reduces the timeout.
        """
        semantic_mock = _make_semantic_mock(
            is_complete=True, confidence=0.95, reason="syntactically_complete"
        )
        manager = semantic_manager_factory(semantic_checker=semantic_mock)

        # Heuristic says incomplete → long timeout
        decision = BoundaryDecision(
            is_complete=False, confidence=0.8, reason="dangling_word", word_count=3
        )
        timeout = manager._determine_timeout(
            decision=decision, confidence=0.8, text="I need gloves for"
        )

        # Should stay at long_timeout (semantic cannot reduce it)
        assert timeout == manager.long_timeout
        # Semantic should NOT be consulted when heuristic already says incomplete
        semantic_mock.is_complete.assert_not_called()

    async def test_semantic_not_consulted_for_incomplete_heuristic(
        self, semantic_manager_factory, event_bus
    ):
        """When heuristic says incomplete, semantic is not consulted at all.

        No point asking semantic to confirm what heuristics already determined.
        """
        semantic_mock = _make_semantic_mock(
            is_complete=True, confidence=0.95, reason="syntactically_complete"
        )
        manager = semantic_manager_factory(semantic_checker=semantic_mock)

        decision = BoundaryDecision(
            is_complete=False, confidence=0.6, reason="too_short", word_count=2
        )
        manager._determine_timeout(
            decision=decision, confidence=0.6, text="hello there"
        )

        semantic_mock.is_complete.assert_not_called()

    async def test_semantic_disabled_none(
        self, semantic_manager_factory, event_bus
    ):
        """No semantic checker → behavior identical to heuristic-only."""
        manager = semantic_manager_factory(semantic_checker=None)

        decision = BoundaryDecision(
            is_complete=True, confidence=0.9, reason="complete_question", word_count=4
        )
        timeout = manager._determine_timeout(
            decision=decision, confidence=0.9, text="where is my order"
        )

        # Should be short timeout (heuristic-only path)
        assert timeout == manager.short_timeout

    async def test_semantic_below_threshold_ignored(
        self, semantic_manager_factory, event_bus
    ):
        """Semantic confidence below threshold → no override."""
        semantic_mock = _make_semantic_mock(
            is_complete=False, confidence=0.5, reason="incomplete_question"
        )
        manager = semantic_manager_factory(
            semantic_checker=semantic_mock,
            semantic_confidence_threshold=0.85,
        )

        decision = BoundaryDecision(
            is_complete=True, confidence=0.9, reason="complete_question", word_count=4
        )
        timeout = manager._determine_timeout(
            decision=decision, confidence=0.9, text="what is the weather"
        )

        # Semantic confidence (0.5) < threshold (0.85), so no override
        assert timeout == manager.short_timeout
        # Semantic WAS called, but result was ignored
        semantic_mock.is_complete.assert_called_once()

    async def test_semantic_exception_graceful_fallback(
        self, semantic_manager_factory, event_bus
    ):
        """If semantic checker throws, fall back to heuristic timeout."""
        semantic_mock = MagicMock()
        semantic_mock.is_complete.side_effect = RuntimeError("spaCy internal error")
        manager = semantic_manager_factory(semantic_checker=semantic_mock)

        decision = BoundaryDecision(
            is_complete=True, confidence=0.9, reason="complete_question", word_count=4
        )
        # Should NOT raise — graceful fallback
        timeout = manager._determine_timeout(
            decision=decision, confidence=0.9, text="where is my order"
        )

        assert timeout == manager.short_timeout

    async def test_semantic_integration_through_event_flow(
        self, semantic_manager_factory, event_bus
    ):
        """End-to-end: semantic delays finalization through event bus flow.

        Emits a heuristic-complete utterance, but semantic says incomplete.
        The timeout should be bumped, delaying finalization.
        """
        semantic_mock = _make_semantic_mock(
            is_complete=False, confidence=0.9, reason="incomplete_noun_phrase"
        )
        manager = semantic_manager_factory(semantic_checker=semantic_mock)

        conversation_id = uuid4()
        events_captured = []

        async def capture(event: Event):
            events_captured.append(event)

        event_bus.subscribe("utterance.complete", capture)

        # Emit a heuristic-complete utterance
        await event_bus.publish(Event.create(
            event_type="transcript.word.final",
            source="test",
            conversation_id=str(conversation_id),
            data={
                "speaker": "Customer",
                "text": "Where is my order?",
                "confidence": 0.95,
                "is_final": True,
            }
        ))

        # Without semantic, this would finalize in ~0.1s (short timeout).
        # With semantic delay, it should take longer (0.3s long timeout).
        await asyncio.sleep(0.15)
        # Should NOT have finalized yet (semantic bumped timeout)
        assert len(events_captured) == 0, (
            "Utterance finalized too quickly — semantic delay not applied"
        )

        # Wait for the bumped timeout to expire
        await asyncio.sleep(0.25)
        assert len(events_captured) == 1
        assert events_captured[0].data["text"] == "Where is my order?"
