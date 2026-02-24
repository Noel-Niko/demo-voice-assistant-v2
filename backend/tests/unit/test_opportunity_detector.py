"""Unit tests for OpportunityDetector service.

Tests the event-driven opportunity detection system that analyzes
transcript windows and publishes opportunity events.
"""
import asyncio
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from app.services.opportunity_detector import OpportunityDetector
from app.services.event_bus import Event


@pytest.fixture
def mock_repository():
    """Mock conversation repository."""
    repo = AsyncMock()
    repo.get_recent_transcript_window = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_event_bus():
    """Mock event bus."""
    bus = AsyncMock()
    bus.subscribe = Mock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_cache():
    """Mock cache for deduplication."""
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


@pytest.fixture
def detector(mock_repository, mock_event_bus, mock_cache):
    """Create OpportunityDetector instance (polling mode for backwards compatibility)."""
    return OpportunityDetector(
        repository=mock_repository,
        event_bus=mock_event_bus,
        cache=mock_cache,
        api_key="test-key",
        model="gpt-3.5-turbo",
        use_utterances=False,  # Use polling mode for existing tests
        analysis_interval=1,  # 1 second for faster tests
        window_seconds=45,
        confidence_threshold=0.7,
        dedup_ttl=30,
    )


@pytest.mark.asyncio
class TestOpportunityDetector:
    """Test suite for OpportunityDetector service."""

    async def test_subscribes_to_transcript_events(self, detector, mock_event_bus):
        """Test that detector subscribes to transcript.word.final events."""
        # Verify subscription was registered
        mock_event_bus.subscribe.assert_called_once_with(
            "transcript.word.final",
            detector._on_transcript_word_final
        )

    async def test_starts_periodic_analysis_on_first_event(self, detector, mock_repository):
        """Test that periodic analysis starts when first transcript event arrives."""
        conversation_id = uuid4()
        event = Event.create(
            event_type="transcript.word.final",
            source="test",
            conversation_id=str(conversation_id),
            data={"word": "hello", "speaker": "CUSTOMER"}
        )

        # First event should start analysis task
        await detector._on_transcript_word_final(event)
        await asyncio.sleep(0.1)  # Let task start

        # Verify analysis task is running
        assert conversation_id in detector._analysis_tasks
        assert not detector._analysis_tasks[conversation_id].done()

        # Cleanup
        await detector.stop_analysis(conversation_id)

    async def test_analyzes_sliding_window(self, detector, mock_repository):
        """Test that analyzer fetches transcript window with correct time range."""
        conversation_id = uuid4()

        # Mock transcript lines
        mock_repository.get_recent_transcript_window.return_value = [
            {"speaker": "CUSTOMER", "text": "I need a ladder", "timestamp": datetime.now(timezone.utc)}
        ]

        # Mock LLM response (no opportunity)
        with patch.object(detector, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "opportunity_detected": False,
                "confidence": 0.3,
            }

            # Trigger analysis
            event = Event.create(
                event_type="transcript.word.final",
                source="test",
                conversation_id=str(conversation_id),
                data={"word": "ladder", "speaker": "CUSTOMER"}
            )
            await detector._on_transcript_word_final(event)
            await asyncio.sleep(1.5)  # Wait for one analysis cycle

            # Verify repository was called with correct conversation_id and window
            mock_repository.get_recent_transcript_window.assert_called()
            call_kwargs = mock_repository.get_recent_transcript_window.call_args.kwargs
            assert call_kwargs["conversation_id"] == conversation_id
            assert call_kwargs["seconds"] == 45

        # Cleanup
        await detector.stop_analysis(conversation_id)

    async def test_detects_product_opportunity(self, detector, mock_repository, mock_event_bus, mock_cache):
        """Test detection of product search opportunity."""
        conversation_id = uuid4()

        # Mock transcript with product request
        mock_repository.get_recent_transcript_window.return_value = [
            {"speaker": "CUSTOMER", "text": "I need a ladder for warehouse use", "timestamp": datetime.now(timezone.utc)}
        ]

        # Mock LLM response with high-confidence opportunity
        with patch.object(detector, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "opportunity_detected": True,
                "opportunity_type": "product_search",
                "confidence": 0.9,
                "query_text": "warehouse ladder",
                "reasoning": "Customer explicitly requested a ladder for warehouse use",
                "semantic_fingerprint": "product_search_ladder_warehouse"
            }

            # Trigger analysis
            event = Event.create(
                event_type="transcript.word.final",
                source="test",
                conversation_id=str(conversation_id),
                data={"word": "use", "speaker": "CUSTOMER"}
            )
            await detector._on_transcript_word_final(event)
            await asyncio.sleep(1.5)  # Wait for analysis cycle

            # Verify opportunity event was published
            published_events = [call[0][0] for call in mock_event_bus.publish.call_args_list]
            opportunity_events = [e for e in published_events if e.event_type == "listening_mode.opportunity.detected"]

            assert len(opportunity_events) >= 1
            opportunity_event = opportunity_events[0]
            assert opportunity_event.data["opportunity_type"] == "product_search"
            assert opportunity_event.data["confidence"] == 0.9
            assert opportunity_event.data["query_text"] == "warehouse ladder"

        # Cleanup
        await detector.stop_analysis(conversation_id)

    async def test_ignores_low_confidence_opportunities(self, detector, mock_repository, mock_event_bus):
        """Test that low-confidence opportunities are not published."""
        conversation_id = uuid4()

        # Mock transcript
        mock_repository.get_recent_transcript_window.return_value = [
            {"speaker": "CUSTOMER", "text": "Maybe I need something", "timestamp": datetime.now(timezone.utc)}
        ]

        # Mock LLM response with low confidence
        with patch.object(detector, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "opportunity_detected": True,
                "opportunity_type": "product_search",
                "confidence": 0.4,  # Below threshold (0.7)
                "query_text": "something",
                "reasoning": "Vague request",
                "semantic_fingerprint": "product_search_something"
            }

            # Trigger analysis
            event = Event.create(
                event_type="transcript.word.final",
                source="test",
                conversation_id=str(conversation_id),
                data={"word": "something", "speaker": "CUSTOMER"}
            )
            await detector._on_transcript_word_final(event)
            await asyncio.sleep(1.5)

            # Verify NO opportunity event was published
            published_events = [call[0][0] for call in mock_event_bus.publish.call_args_list]
            opportunity_events = [e for e in published_events if e.event_type == "listening_mode.opportunity.detected"]
            assert len(opportunity_events) == 0

        # Cleanup
        await detector.stop_analysis(conversation_id)

    async def test_deduplicates_similar_opportunities(self, detector, mock_repository, mock_event_bus, mock_cache):
        """Test that duplicate opportunities are not re-published within TTL window."""
        conversation_id = uuid4()
        fingerprint = "product_search_ladder_warehouse"

        # Mock transcript
        mock_repository.get_recent_transcript_window.return_value = [
            {"speaker": "CUSTOMER", "text": "I need a ladder for warehouse", "timestamp": datetime.now(timezone.utc)}
        ]

        # First detection: cache miss (no duplicate)
        mock_cache.get.return_value = None

        with patch.object(detector, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "opportunity_detected": True,
                "opportunity_type": "product_search",
                "confidence": 0.9,
                "query_text": "warehouse ladder",
                "reasoning": "Customer requested ladder",
                "semantic_fingerprint": fingerprint
            }

            # First event - should publish
            event = Event.create(
                event_type="transcript.word.final",
                source="test",
                conversation_id=str(conversation_id),
                data={"word": "warehouse", "speaker": "CUSTOMER"}
            )
            await detector._on_transcript_word_final(event)
            await asyncio.sleep(1.5)

            # Verify first opportunity was published and cached
            mock_cache.set.assert_called()
            published_count_1 = len([
                call for call in mock_event_bus.publish.call_args_list
                if call[0][0].event_type == "listening_mode.opportunity.detected"
            ])
            assert published_count_1 >= 1

            # Second detection: cache hit (duplicate)
            mock_cache.get.return_value = "cached"
            mock_event_bus.publish.reset_mock()

            # Trigger another analysis cycle
            await asyncio.sleep(1.5)

            # Verify NO new opportunity event was published (deduplicated)
            published_count_2 = len([
                call for call in mock_event_bus.publish.call_args_list
                if call[0][0].event_type == "listening_mode.opportunity.detected"
            ])
            assert published_count_2 == 0

        # Cleanup
        await detector.stop_analysis(conversation_id)

    async def test_handles_llm_errors_gracefully(self, detector, mock_repository, mock_event_bus):
        """Test that LLM errors don't crash the analysis loop."""
        conversation_id = uuid4()

        # Mock transcript
        mock_repository.get_recent_transcript_window.return_value = [
            {"speaker": "CUSTOMER", "text": "I need help", "timestamp": datetime.now(timezone.utc)}
        ]

        # Mock LLM to raise error first, then succeed
        call_count = 0
        async def llm_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("OpenAI timeout")
            return {
                "opportunity_detected": False,
                "confidence": 0.3,
            }

        with patch.object(detector, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = llm_side_effect

            # Trigger analysis
            event = Event.create(
                event_type="transcript.word.final",
                source="test",
                conversation_id=str(conversation_id),
                data={"word": "help", "speaker": "CUSTOMER"}
            )
            await detector._on_transcript_word_final(event)
            await asyncio.sleep(2.5)  # Wait for 2 analysis cycles

            # Verify task is still running (didn't crash)
            assert conversation_id in detector._analysis_tasks
            assert not detector._analysis_tasks[conversation_id].done()

            # Verify LLM was called multiple times (recovered from error)
            assert mock_llm.call_count >= 2

        # Cleanup
        await detector.stop_analysis(conversation_id)

    async def test_stops_analysis_on_conversation_end(self, detector):
        """Test that analysis task is properly cancelled when conversation ends."""
        conversation_id = uuid4()

        # Start analysis
        event = Event.create(
            event_type="transcript.word.final",
            source="test",
            conversation_id=str(conversation_id),
            data={"word": "hello", "speaker": "CUSTOMER"}
        )
        await detector._on_transcript_word_final(event)
        await asyncio.sleep(0.1)

        # Verify task is running
        assert conversation_id in detector._analysis_tasks
        task = detector._analysis_tasks[conversation_id]
        assert not task.done()

        # Stop analysis
        await detector.stop_analysis(conversation_id)
        await asyncio.sleep(0.1)

        # Verify task is cancelled and removed
        assert task.done()
        assert task.cancelled()
        assert conversation_id not in detector._analysis_tasks

    # ===== NEW TESTS FOR UTTERANCE MODE =====

    async def test_utterance_mode_subscribes_to_utterance_complete(self, mock_repository, mock_event_bus, mock_cache):
        """Test that utterance mode subscribes to utterance.complete events."""
        # Create detector with utterance mode enabled
        detector = OpportunityDetector(
            repository=mock_repository,
            event_bus=mock_event_bus,
            cache=mock_cache,
            api_key="test-key",
            model="gpt-3.5-turbo",
            confidence_threshold=0.7,
            dedup_ttl=30,
            use_utterances=True,  # NEW: utterance mode
        )

        # Verify subscription to utterance.complete (not transcript.word.final)
        mock_event_bus.subscribe.assert_called_once_with(
            "utterance.complete",
            detector._on_utterance_complete
        )

    async def test_utterance_mode_gets_full_conversation_context(self, mock_repository, mock_event_bus, mock_cache):
        """Test that utterance mode fetches full conversation history (not 45s window)."""
        detector = OpportunityDetector(
            repository=mock_repository,
            event_bus=mock_event_bus,
            cache=mock_cache,
            api_key="test-key",
            use_utterances=True,
        )

        conversation_id = uuid4()

        # Mock full conversation history
        mock_repository.get_all_final_transcript_lines.return_value = [
            {"speaker": "Customer", "text": "Hello", "timestamp": "2026-02-21T10:00:00", "sequence_number": 1},
            {"speaker": "Agent", "text": "Hi how can I help", "timestamp": "2026-02-21T10:00:05", "sequence_number": 2},
            {"speaker": "Customer", "text": "I need a ladder", "timestamp": "2026-02-21T10:00:10", "sequence_number": 3},
        ]

        # Mock LLM response (no opportunity)
        with patch.object(detector, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "opportunity_detected": False,
                "confidence": 0.3,
            }

            # Emit utterance.complete event
            event = Event.create(
                event_type="utterance.complete",
                source="utterance_manager",
                conversation_id=str(conversation_id),
                data={
                    "speaker": "Customer",
                    "text": "I need a ladder",
                    "word_count": 4,
                    "confidence": 0.9,
                    "reason": "complete_statement",
                    "finalization_reason": "timeout_short",
                }
            )

            await detector._on_utterance_complete(event)
            await asyncio.sleep(0.1)

            # Verify get_all_final_transcript_lines was called (not get_recent_transcript_window)
            mock_repository.get_all_final_transcript_lines.assert_called_once_with(conversation_id=conversation_id)
            mock_repository.get_recent_transcript_window.assert_not_called()

            # Verify LLM received full conversation
            mock_llm.assert_called_once()
            transcript_lines = mock_llm.call_args[0][0]
            assert len(transcript_lines) == 3  # Full conversation
            assert transcript_lines[0]["text"] == "Hello"
            assert transcript_lines[2]["text"] == "I need a ladder"

    async def test_utterance_mode_analyzes_agent_utterances(self, mock_repository, mock_event_bus, mock_cache):
        """Test that utterance mode analyzes BOTH customer and agent utterances.

        Agent may mention product details that trigger opportunities.
        Example: Agent: "So you need safety gloves for chemical handling?"
                 Customer: "Yes"
        """
        detector = OpportunityDetector(
            repository=mock_repository,
            event_bus=mock_event_bus,
            cache=mock_cache,
            api_key="test-key",
            use_utterances=True,
        )

        conversation_id = uuid4()

        # Mock conversation with agent mentioning product
        mock_repository.get_all_final_transcript_lines.return_value = [
            {"speaker": "Agent", "text": "So you need safety gloves for chemical handling?", "timestamp": "2026-02-21T10:00:00", "sequence_number": 1},
            {"speaker": "Customer", "text": "Yes", "timestamp": "2026-02-21T10:00:05", "sequence_number": 2},
        ]

        # Mock LLM response (detects opportunity from agent's question)
        with patch.object(detector, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "opportunity_detected": True,
                "opportunity_type": "product_search",
                "confidence": 0.9,
                "query_text": "safety gloves for chemical handling",
                "reasoning": "Agent mentioned specific product need",
                "semantic_fingerprint": "test-fingerprint",
            }

            # Emit AGENT utterance
            event = Event.create(
                event_type="utterance.complete",
                source="utterance_manager",
                conversation_id=str(conversation_id),
                data={
                    "speaker": "Agent",  # Agent utterance
                    "text": "So you need safety gloves for chemical handling?",
                    "word_count": 8,
                    "confidence": 0.9,
                }
            )

            await detector._on_utterance_complete(event)
            await asyncio.sleep(0.1)

            # Verify LLM WAS called for agent utterance (agent may mention products!)
            mock_llm.assert_called_once()
            mock_repository.get_all_final_transcript_lines.assert_called_once_with(conversation_id=conversation_id)

            # Verify full conversation context includes agent's product mention
            transcript_lines = mock_llm.call_args[0][0]
            assert len(transcript_lines) == 2
            assert transcript_lines[0]["speaker"] == "Agent"
            assert "safety gloves" in transcript_lines[0]["text"]

    async def test_utterance_mode_no_periodic_polling(self, mock_repository, mock_event_bus, mock_cache):
        """Test that utterance mode does NOT use periodic polling."""
        detector = OpportunityDetector(
            repository=mock_repository,
            event_bus=mock_event_bus,
            cache=mock_cache,
            api_key="test-key",
            use_utterances=True,  # Utterance mode
        )

        conversation_id = uuid4()

        # Mock customer utterance
        mock_repository.get_all_final_transcript_lines.return_value = [
            {"speaker": "Customer", "text": "I need help", "timestamp": "2026-02-21T10:00:00", "sequence_number": 1},
        ]

        # Mock LLM (no opportunity)
        with patch.object(detector, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"opportunity_detected": False, "confidence": 0.3}

            # Emit utterance.complete event
            event = Event.create(
                event_type="utterance.complete",
                source="utterance_manager",
                conversation_id=str(conversation_id),
                data={
                    "speaker": "Customer",
                    "text": "I need help",
                    "word_count": 3,
                    "confidence": 0.9,
                }
            )

            await detector._on_utterance_complete(event)
            await asyncio.sleep(0.1)

            # Verify LLM called once (event-driven)
            assert mock_llm.call_count == 1

            # Wait longer (no periodic polling should happen)
            await asyncio.sleep(1.5)

            # Verify LLM still only called once (no polling)
            assert mock_llm.call_count == 1

            # Verify no analysis task was created (no periodic loop)
            assert conversation_id not in detector._analysis_tasks

    # ===== Model Selector Tests =====

    async def test_set_model_updates_model(self, mock_repository, mock_event_bus, mock_cache):
        """Test that set_model changes the model used for LLM calls."""
        detector = OpportunityDetector(
            repository=mock_repository,
            event_bus=mock_event_bus,
            cache=mock_cache,
            api_key="test-key",
            model="gpt-3.5-turbo",
            use_utterances=False,
        )
        assert detector.model == "gpt-3.5-turbo"
        detector.set_model("gpt-4o")
        assert detector.model == "gpt-4o"

    async def test_set_model_with_reasoning_effort(self, mock_repository, mock_event_bus, mock_cache):
        """Test that set_model stores reasoning_effort."""
        detector = OpportunityDetector(
            repository=mock_repository,
            event_bus=mock_event_bus,
            cache=mock_cache,
            api_key="test-key",
            use_utterances=False,
        )
        detector.set_model("gpt-5", reasoning_effort="low")
        assert detector.model == "gpt-5"
        assert detector._reasoning_effort == "low"

    async def test_polling_mode_still_works(self, mock_repository, mock_event_bus, mock_cache):
        """Test that polling mode (use_utterances=False) still works for backwards compatibility."""
        # Create detector with polling mode (old behavior)
        detector = OpportunityDetector(
            repository=mock_repository,
            event_bus=mock_event_bus,
            cache=mock_cache,
            api_key="test-key",
            use_utterances=False,  # Polling mode
            analysis_interval=1,
            window_seconds=45,
        )

        # Verify subscription to transcript.word.final (old behavior)
        mock_event_bus.subscribe.assert_called_once_with(
            "transcript.word.final",
            detector._on_transcript_word_final
        )

        conversation_id = uuid4()

        # Mock transcript window
        mock_repository.get_recent_transcript_window.return_value = [
            {"speaker": "CUSTOMER", "text": "I need help", "timestamp": datetime.now(timezone.utc)}
        ]

        # Emit transcript.word.final event (old event type)
        event = Event.create(
            event_type="transcript.word.final",
            source="test",
            conversation_id=str(conversation_id),
            data={"word": "help", "speaker": "CUSTOMER"}
        )

        await detector._on_transcript_word_final(event)
        await asyncio.sleep(0.1)

        # Verify periodic analysis task was created (old behavior)
        assert conversation_id in detector._analysis_tasks
        assert not detector._analysis_tasks[conversation_id].done()

        # Cleanup
        await detector.stop_analysis(conversation_id)

    @pytest.mark.asyncio
    async def test_model_switch_during_analysis_uses_captured_config(self):
        """Test that model changes mid-operation don't affect in-flight API calls.

        Bug: When user switches models during opportunity detection (e.g., GPT-3.5 → GPT-5),
        the API call reads self.model mid-execution, causing parameter mismatches.

        This test verifies that after the fix:
        1. Detector initializes with GPT-3.5
        2. Config is captured
        3. Model switches to GPT-5
        4. API kwargs use the originally captured GPT-3.5 config
        """
        from uuid import UUID

        repository = AsyncMock()
        event_bus = Mock()
        cache = Mock()

        # Initialize with GPT-3.5
        detector = OpportunityDetector(
            repository=repository,
            event_bus=event_bus,
            cache=cache,
            api_key="test-key",
            model="gpt-3.5-turbo",
            use_utterances=True
        )
        detector._reasoning_effort = None

        # Test _build_api_kwargs with captured config
        # 1. Capture config when model is GPT-3.5
        captured_model, captured_reasoning_effort = detector._get_current_model_config()

        # 2. Switch model to GPT-5
        detector.model = "gpt-5"
        detector._reasoning_effort = "low"

        # 3. Build API kwargs using the CAPTURED config (not current self.model)
        api_kwargs = detector._build_api_kwargs(
            base_temp=0.3,
            model=captured_model,  # Should be gpt-3.5-turbo
            reasoning_effort=captured_reasoning_effort,  # Should be None
            response_format={"type": "json_object"}
        )

        # 4. Verify kwargs use GPT-3.5 config, not GPT-5
        assert api_kwargs["model"] == "gpt-3.5-turbo", \
            "API kwargs should use captured model (GPT-3.5), not current model (GPT-5)"
        assert "temperature" in api_kwargs, \
            "GPT-3.5 should use temperature parameter"
        assert "reasoning_effort" not in api_kwargs, \
            "GPT-3.5 should NOT have reasoning_effort parameter"
        assert api_kwargs["response_format"] == {"type": "json_object"}

    # ===== Event Bus Blocking Fix Tests =====

    async def test_utterance_handler_does_not_block_event_bus(self, mock_repository, mock_event_bus, mock_cache):
        """Test that _on_utterance_complete returns immediately without awaiting the LLM call.

        Bug: _on_utterance_complete directly awaits _analyze_for_opportunities, which makes
        a slow OpenAI API call (10-60s for GPT-5 reasoning models). Since the InMemoryEventBus
        processes events through a single worker loop, this blocks ALL subsequent events in
        the queue — including transcript.word.final events that the WebSocket handler needs
        to forward to the frontend. The user sees transcription freeze.

        Fix: Wrap the analysis in asyncio.create_task so the handler returns immediately.
        """
        detector = OpportunityDetector(
            repository=mock_repository,
            event_bus=mock_event_bus,
            cache=mock_cache,
            api_key="test-key",
            model="gpt-3.5-turbo",
            use_utterances=True,
        )

        conversation_id = uuid4()

        # Mock repository to return transcript lines
        mock_repository.get_all_final_transcript_lines.return_value = [
            {"speaker": "Customer", "text": "I need a ladder", "timestamp": "2026-02-21T10:00:00", "sequence_number": 1},
        ]

        # Mock LLM to take a long time (simulates slow GPT-5 reasoning)
        slow_llm_started = asyncio.Event()
        slow_llm_release = asyncio.Event()

        async def slow_llm(*args, **kwargs):
            slow_llm_started.set()
            await slow_llm_release.wait()
            return {"opportunity_detected": False, "confidence": 0.3}

        with patch.object(detector, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = slow_llm

            event = Event.create(
                event_type="utterance.complete",
                source="utterance_manager",
                conversation_id=str(conversation_id),
                data={"speaker": "Customer", "text": "I need a ladder", "word_count": 4},
            )

            # _on_utterance_complete should return IMMEDIATELY (non-blocking)
            # If it blocks, this will hang until slow_llm_release is set
            handler_task = asyncio.create_task(detector._on_utterance_complete(event))

            # Give the handler a moment to start
            await asyncio.sleep(0.05)

            # Handler should be DONE (returned immediately after spawning task)
            assert handler_task.done(), (
                "_on_utterance_complete should return immediately without awaiting "
                "the LLM call. It currently blocks the event bus worker."
            )

            # But the LLM call should be in progress (running in background task)
            assert slow_llm_started.is_set(), (
                "The LLM analysis should have started in a background task"
            )

            # Clean up: release the slow LLM and let background task finish
            slow_llm_release.set()
            await asyncio.sleep(0.1)

    async def test_utterance_tasks_tracked_for_cleanup(self, mock_repository, mock_event_bus, mock_cache):
        """Test that background utterance analysis tasks are tracked in _utterance_tasks.

        Without tracking, tasks spawned by _on_utterance_complete would be fire-and-forget,
        meaning shutdown() couldn't cancel them — leading to race conditions where tasks
        try to publish events after the event bus has stopped.
        """
        detector = OpportunityDetector(
            repository=mock_repository,
            event_bus=mock_event_bus,
            cache=mock_cache,
            api_key="test-key",
            model="gpt-3.5-turbo",
            use_utterances=True,
        )

        conversation_id = uuid4()

        mock_repository.get_all_final_transcript_lines.return_value = [
            {"speaker": "Customer", "text": "I need a ladder", "timestamp": "2026-02-21T10:00:00", "sequence_number": 1},
        ]

        hold = asyncio.Event()

        async def held_llm(*args, **kwargs):
            await hold.wait()
            return {"opportunity_detected": False, "confidence": 0.3}

        with patch.object(detector, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = held_llm

            event = Event.create(
                event_type="utterance.complete",
                source="utterance_manager",
                conversation_id=str(conversation_id),
                data={"speaker": "Customer", "text": "I need a ladder", "word_count": 4},
            )

            await detector._on_utterance_complete(event)
            await asyncio.sleep(0.05)

            # Detector should track utterance tasks for shutdown cleanup
            assert hasattr(detector, '_utterance_tasks'), (
                "Detector should have _utterance_tasks dict to track background analysis tasks"
            )
            assert len(detector._utterance_tasks) > 0, (
                "Background utterance task should be tracked in _utterance_tasks"
            )

            # Clean up
            hold.set()
            await asyncio.sleep(0.1)

    async def test_shutdown_cancels_utterance_tasks(self, mock_repository, mock_event_bus, mock_cache):
        """Test that shutdown() cancels in-flight utterance analysis tasks."""
        detector = OpportunityDetector(
            repository=mock_repository,
            event_bus=mock_event_bus,
            cache=mock_cache,
            api_key="test-key",
            model="gpt-3.5-turbo",
            use_utterances=True,
        )

        conversation_id = uuid4()

        mock_repository.get_all_final_transcript_lines.return_value = [
            {"speaker": "Customer", "text": "I need help", "timestamp": "2026-02-21T10:00:00", "sequence_number": 1},
        ]

        hold = asyncio.Event()

        async def held_llm(*args, **kwargs):
            await hold.wait()
            return {"opportunity_detected": False, "confidence": 0.3}

        with patch.object(detector, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = held_llm

            event = Event.create(
                event_type="utterance.complete",
                source="utterance_manager",
                conversation_id=str(conversation_id),
                data={"speaker": "Customer", "text": "I need help", "word_count": 3},
            )

            await detector._on_utterance_complete(event)
            await asyncio.sleep(0.05)

            # Shutdown should cancel the background task
            await detector.shutdown()

            # After shutdown, utterance tasks should be cleared
            assert len(detector._utterance_tasks) == 0, (
                "shutdown() should cancel and clear all utterance tasks"
            )
