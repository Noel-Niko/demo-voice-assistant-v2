"""
Unit tests for UtteranceBoundaryDetector.

Tests the heuristic-based utterance boundary detection logic used by
the Listening Mode opportunity detector.
"""

import pytest

from app.services.utterance_boundary_detector import (
    BoundaryDecision,
    UtteranceBoundaryDetector,
    UtterancePatterns,
)


class TestUtteranceBoundaryDetector:
    """Test UtteranceBoundaryDetector service."""

    @pytest.fixture
    def detector(self) -> UtteranceBoundaryDetector:
        """Create detector instance with default settings."""
        return UtteranceBoundaryDetector()

    # ===== Complete Question Tests =====

    def test_complete_question_with_question_mark(self, detector: UtteranceBoundaryDetector):
        """Complete questions ending with ? are detected."""
        decision = detector.is_complete("Where is my order?")
        assert decision.is_complete is True
        assert decision.confidence >= 0.8
        assert decision.reason == "complete_question"

    def test_complete_question_without_question_mark(self, detector: UtteranceBoundaryDetector):
        """Complete questions starting with question words are detected even without ?"""
        decision = detector.is_complete("How do I return this item")
        assert decision.is_complete is True
        assert decision.confidence >= 0.8
        assert decision.reason == "complete_question"

    def test_incomplete_question_dangling_word(self, detector: UtteranceBoundaryDetector):
        """Questions ending with dangling words are incomplete."""
        decision = detector.is_complete("What is the")
        assert decision.is_complete is False
        assert decision.confidence >= 0.7
        assert decision.reason == "dangling_word"

    # ===== Complete Command Tests =====

    def test_complete_command_imperative(self, detector: UtteranceBoundaryDetector):
        """Complete commands with imperative verbs are detected."""
        decision = detector.is_complete("Show me the safety gloves")
        assert decision.is_complete is True
        assert decision.confidence >= 0.8
        assert decision.reason == "complete_command"

    def test_complete_command_find_pattern(self, detector: UtteranceBoundaryDetector):
        """Find me X pattern is detected as complete command."""
        decision = detector.is_complete("Find me industrial ladders")
        assert decision.is_complete is True
        assert decision.confidence >= 0.8
        assert decision.reason == "complete_command"

    def test_incomplete_command_dangling_preposition(self, detector: UtteranceBoundaryDetector):
        """Commands ending with prepositions are incomplete."""
        decision = detector.is_complete("Show me products for")
        assert decision.is_complete is False
        assert decision.confidence >= 0.7
        assert decision.reason == "dangling_word"

    # ===== Complete Statement Tests =====

    def test_complete_statement_with_period(self, detector: UtteranceBoundaryDetector):
        """Complete statements ending with period are detected."""
        decision = detector.is_complete("I need gloves for chemical handling.")
        assert decision.is_complete is True
        assert decision.confidence >= 0.8
        assert decision.reason == "complete_statement"

    def test_complete_statement_without_punctuation(self, detector: UtteranceBoundaryDetector):
        """Complete statements without punctuation are detected if long enough."""
        decision = detector.is_complete("I need industrial safety equipment")
        assert decision.is_complete is True
        assert decision.confidence >= 0.6
        # Could be complete_statement or default_complete

    def test_incomplete_statement_dangling_determiner(self, detector: UtteranceBoundaryDetector):
        """Statements ending with determiners are incomplete."""
        decision = detector.is_complete("I need a")
        assert decision.is_complete is False
        assert decision.confidence >= 0.7
        assert decision.reason == "dangling_word"

    # ===== Incomplete Patterns Tests =====

    def test_single_word_incomplete(self, detector: UtteranceBoundaryDetector):
        """Single words are always incomplete."""
        decision = detector.is_complete("Hello")
        assert decision.is_complete is False
        assert decision.confidence >= 0.9
        assert decision.reason == "single_word"
        assert decision.word_count == 1

    def test_empty_text_incomplete(self, detector: UtteranceBoundaryDetector):
        """Empty text is incomplete."""
        decision = detector.is_complete("")
        assert decision.is_complete is False
        assert decision.reason == "empty_text"
        assert decision.word_count == 0

    def test_whitespace_only_incomplete(self, detector: UtteranceBoundaryDetector):
        """Whitespace-only text is incomplete."""
        decision = detector.is_complete("   ")
        assert decision.is_complete is False
        assert decision.reason == "empty_text"

    def test_filler_word_ending_incomplete(self, detector: UtteranceBoundaryDetector):
        """Utterances ending with filler words are incomplete."""
        decision = detector.is_complete("I need um")
        assert decision.is_complete is False
        assert decision.confidence >= 0.8
        assert decision.reason == "filler_word_ending"

    def test_too_short_incomplete(self, detector: UtteranceBoundaryDetector):
        """Very short phrases are incomplete."""
        decision = detector.is_complete("I need")
        assert decision.is_complete is False
        assert decision.reason in {"dangling_word", "too_short"}

    # ===== Dangling Word Pattern Tests =====

    def test_dangling_preposition(self, detector: UtteranceBoundaryDetector):
        """Phrases ending with prepositions are incomplete."""
        for phrase in ["looking for", "waiting for", "searching for"]:
            decision = detector.is_complete(phrase)
            assert decision.is_complete is False
            assert decision.reason == "dangling_word"

    def test_dangling_conjunction(self, detector: UtteranceBoundaryDetector):
        """Phrases ending with conjunctions are incomplete."""
        for phrase in ["I need gloves and", "Show me products or"]:
            decision = detector.is_complete(phrase)
            assert decision.is_complete is False
            assert decision.reason == "dangling_word"

    def test_need_determiner_pattern(self, detector: UtteranceBoundaryDetector):
        """'need/want + determiner' patterns are incomplete."""
        for phrase in ["I need a", "I want the", "I require some"]:
            decision = detector.is_complete(phrase)
            assert decision.is_complete is False
            assert decision.reason == "dangling_word"

    # ===== Product/Order Mention Tests (Real-World Examples) =====

    def test_complete_product_request(self, detector: UtteranceBoundaryDetector):
        """Complete product requests are detected."""
        examples = [
            "Do you have SKU 1FYX7 in stock?",
            "I need chemical resistant gloves.",
            "Show me industrial ladders for roofing.",
            "What safety equipment do you recommend?"
        ]
        for phrase in examples:
            decision = detector.is_complete(phrase)
            assert decision.is_complete is True, f"Failed for: {phrase}"
            assert decision.confidence >= 0.7

    def test_incomplete_product_request(self, detector: UtteranceBoundaryDetector):
        """Incomplete product requests are detected."""
        examples = [
            "I need gloves for",
            "Show me the",
            "Do you have",
            "I'm looking for a"
        ]
        for phrase in examples:
            decision = detector.is_complete(phrase)
            assert decision.is_complete is False, f"Failed for: {phrase}"

    def test_complete_order_inquiry(self, detector: UtteranceBoundaryDetector):
        """Complete order inquiries are detected."""
        examples = [
            "Where is order 12345?",
            "What is the status of my order?",
            "When will order 12345 be delivered?",
            "Can you check on order 12345?"
        ]
        for phrase in examples:
            decision = detector.is_complete(phrase)
            assert decision.is_complete is True, f"Failed for: {phrase}"
            assert decision.confidence >= 0.7

    def test_incomplete_order_inquiry(self, detector: UtteranceBoundaryDetector):
        """Incomplete order inquiries are detected."""
        examples = [
            "Where is my",
            "Order number",
            "The status of",
            "I'm calling about order"
        ]
        for phrase in examples:
            decision = detector.is_complete(phrase)
            assert decision.is_complete is False, f"Failed for: {phrase}"

    # ===== Configuration Tests =====

    def test_custom_min_words_complete(self):
        """Custom minimum word counts are respected."""
        detector = UtteranceBoundaryDetector(min_words_complete=6)

        # 4 words - too short
        decision = detector.is_complete("I need safety gloves")
        assert decision.is_complete is False

        # 6+ words - long enough
        decision = detector.is_complete("I need safety gloves for chemical work")
        assert decision.is_complete is True

    def test_custom_confidence_threshold(self):
        """Custom confidence thresholds can be configured."""
        detector = UtteranceBoundaryDetector(confidence_threshold=0.9)
        # Detector still works with higher threshold
        decision = detector.is_complete("Where is my order?")
        assert decision.is_complete is True

    # ===== Word Count Tests =====

    def test_word_count_tracking(self, detector: UtteranceBoundaryDetector):
        """Word count is correctly tracked in decisions."""
        decision = detector.is_complete("Show me industrial safety gloves please")
        assert decision.word_count == 6

    # ===== Edge Cases =====

    def test_punctuation_stripping(self, detector: UtteranceBoundaryDetector):
        """Trailing punctuation is handled correctly."""
        # Multiple punctuation marks
        decision = detector.is_complete("Where is my order??")
        assert decision.is_complete is True

    def test_mixed_case_handling(self, detector: UtteranceBoundaryDetector):
        """Mixed case text is handled correctly."""
        decision = detector.is_complete("WHERE IS MY ORDER?")
        assert decision.is_complete is True

    def test_extra_whitespace_handling(self, detector: UtteranceBoundaryDetector):
        """Extra whitespace is trimmed correctly."""
        decision = detector.is_complete("  Where is my order?  ")
        assert decision.is_complete is True
        assert decision.reason == "complete_question"


class TestUtterancePatterns:
    """Test UtterancePatterns constants."""

    def test_question_words_coverage(self):
        """Question words cover common interrogatives."""
        assert "what" in UtterancePatterns.QUESTION_WORDS
        assert "where" in UtterancePatterns.QUESTION_WORDS
        assert "how" in UtterancePatterns.QUESTION_WORDS
        assert "can" in UtterancePatterns.QUESTION_WORDS

    def test_command_verbs_coverage(self):
        """Command verbs cover common imperatives."""
        assert "show" in UtterancePatterns.COMMAND_VERBS
        assert "find" in UtterancePatterns.COMMAND_VERBS
        assert "get" in UtterancePatterns.COMMAND_VERBS

    def test_dangling_words_coverage(self):
        """Dangling words cover prepositions, determiners, conjunctions."""
        # Prepositions
        assert "for" in UtterancePatterns.DANGLING_WORDS
        assert "with" in UtterancePatterns.DANGLING_WORDS
        # Determiners
        assert "the" in UtterancePatterns.DANGLING_WORDS
        assert "a" in UtterancePatterns.DANGLING_WORDS
        # Conjunctions
        assert "and" in UtterancePatterns.DANGLING_WORDS
        assert "or" in UtterancePatterns.DANGLING_WORDS
