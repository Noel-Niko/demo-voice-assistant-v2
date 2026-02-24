"""
Utterance Boundary Detection for Listening Mode.

This module implements lightweight heuristic-based utterance boundary detection
to determine when a speaker has completed a thought/phrase. This prevents
premature LLM queries on incomplete utterances like "I need a..." or "Where is my...".

Pattern based on demo_voice_assistant/src/gateway/utterance_boundary_decider.py
but simplified for conversation transcript analysis (no real-time voice events).

Key Concepts:
- **Complete utterance**: A finished thought that can be acted upon
  Examples: "I need gloves for chemical handling.", "Where is order 12345?"

- **Incomplete utterance**: Dangling phrase waiting for more context
  Examples: "I need...", "Where is my...", "Can you show me the..."

- **Utterance boundary**: The point where we're confident the speaker finished their thought
  Detected via:  - Heuristic rules (questions, statements, commands)
  - Dangling phrase detection (prepositions, conjunctions, determiners)
  - Confidence thresholds

Algorithm:
1. Check for high-confidence complete patterns (questions, statements, commands)
2. Check for incomplete indicators (dangling words, low word count)
3. Return confidence score + reason

No LLM calls, no ML models - pure heuristics for speed (< 1ms per check).
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# Linguistic constants for boundary detection
class UtterancePatterns:
    """Linguistic patterns for utterance boundary detection."""

    # Question starters
    QUESTION_WORDS = frozenset({
        "what", "where", "when", "why", "how", "who", "which",
        "can", "could", "would", "will", "should", "is", "are", "do", "does", "did"
    })

    # Command verbs (imperative mood)
    COMMAND_VERBS = frozenset({
        "show", "find", "get", "tell", "give", "help", "check", "look",
        "search", "list", "display", "open", "create", "update", "cancel"
    })

    # Words that signal incomplete thought
    DANGLING_WORDS = frozenset({
        # Prepositions
        "for", "with", "about", "from", "to", "in", "on", "at", "by",
        "of", "into", "onto", "upon", "after", "before", "during",
        # Determiners
        "the", "a", "an", "this", "that", "these", "those", "my", "your",
        # Conjunctions
        "and", "or", "but", "so", "because", "if", "when", "while",
        # Auxiliary verbs
        "is", "are", "was", "were", "have", "has", "had", "do", "does", "did",
        "can", "could", "will", "would", "should", "may", "might", "must"
    })

    # Natural sentence endings
    SENTENCE_ENDINGS = frozenset({".", "?", "!"})

    # Filler words suggesting more to come
    FILLER_WORDS = frozenset({"um", "uh", "er", "ah", "hmm"})

    # --- Semantic layer constants (used by SpacySemanticChecker) ---

    # Transitive verbs requiring direct objects
    TRANSITIVE_COMMAND_VERBS = frozenset({
        "find", "get", "show", "open", "close", "set", "turn", "display"
    })

    # Predicate verbs requiring object for completeness
    PREDICATE_VERBS_REQUIRE_OBJECT = frozenset({
        "find", "get", "show", "give", "tell", "ask"
    })

    # Subordinating conjunctions (incomplete if at end)
    SUBORDINATING_CONJUNCTIONS = frozenset({
        "because", "since", "although", "while", "if", "when", "where"
    })

    # Natural sentence endings (boost confidence)
    NATURAL_ENDINGS = frozenset({
        "please", "thanks", "thank you", "now", "today",
        "right now", "immediately", "asap"
    })

    # Continuation words (stronger signal than dangling words)
    CONTINUATION_WORDS = frozenset({
        "and", "or", "but", "because", "since", "while",
        "although", "however", "therefore", "furthermore",
        "moreover", "nevertheless", "so", "yet", "nor",
        "either", "neither", "both"
    })

    # Prepositions (subset of DANGLING_WORDS, used for specific checks)
    PREPOSITIONS = frozenset({
        "for", "with", "about", "from", "to", "of",
        "in", "on", "at", "by", "into", "onto", "upon",
        "after", "before", "during"
    })

    # Determiners (subset of DANGLING_WORDS, used for specific checks)
    DETERMINERS = frozenset({
        "the", "a", "an", "this", "that", "these", "those",
        "my", "your", "his", "her", "its", "our", "their"
    })

    # Question start words as tuple (for str.startswith) and frozenset (for O(1) lookup)
    QUESTION_START_WORDS_TUPLE = (
        "what", "how", "when", "where", "why", "who", "which", "whose", "whom"
    )


@dataclass(frozen=True)
class BoundaryDecision:
    """Result of utterance boundary detection."""

    is_complete: bool  # Is this a complete utterance?
    confidence: float  # How confident are we? (0.0 - 1.0)
    reason: str  # Why did we make this decision?
    word_count: int  # Number of words in utterance


class UtteranceBoundaryDetector:
    """
    Lightweight heuristic-based utterance boundary detector.

    Determines if a transcript line or sequence of lines represents a
    complete thought that's ready for analysis.

    Usage:
        detector = UtteranceBoundaryDetector()
        decision = detector.is_complete("I need gloves for chemical handling.")
        if decision.is_complete and decision.confidence > 0.8:
            # Utterance is complete, safe to analyze
            trigger_opportunity_detection(text)
    """

    def __init__(
        self,
        *,
        min_words_complete: int = 4,
        min_words_question: int = 3,
        min_words_command: int = 3,
        confidence_threshold: float = 0.7,
    ):
        """
        Initialize utterance boundary detector.

        Args:
            min_words_complete: Minimum words for complete statement
            min_words_question: Minimum words for complete question
            min_words_command: Minimum words for complete command
            confidence_threshold: Minimum confidence to consider complete
        """
        self.min_words_complete = min_words_complete
        self.min_words_question = min_words_question
        self.min_words_command = min_words_command
        self.confidence_threshold = confidence_threshold

    def is_complete(self, text: str, speaker: Optional[str] = None) -> BoundaryDecision:
        """
        Determine if text represents a complete utterance.

        Args:
            text: Transcript text to analyze
            speaker: Optional speaker label (Agent/Customer)

        Returns:
            BoundaryDecision with is_complete, confidence, reason
        """
        if not text or not text.strip():
            return BoundaryDecision(
                is_complete=False,
                confidence=1.0,
                reason="empty_text",
                word_count=0
            )

        cleaned = text.strip()
        words = cleaned.split()
        word_count = len(words)

        # Single word utterances are incomplete
        if word_count == 1:
            return BoundaryDecision(
                is_complete=False,
                confidence=0.95,
                reason="single_word",
                word_count=word_count
            )

        # Check for filler words at end
        if self._ends_with_filler(cleaned):
            return BoundaryDecision(
                is_complete=False,
                confidence=0.9,
                reason="filler_word_ending",
                word_count=word_count
            )

        # PRIORITY 1: Check for complete questions
        if self._is_complete_question(cleaned, words):
            return BoundaryDecision(
                is_complete=True,
                confidence=0.9,
                reason="complete_question",
                word_count=word_count
            )

        # PRIORITY 2: Check for complete commands
        if self._is_complete_command(cleaned, words):
            return BoundaryDecision(
                is_complete=True,
                confidence=0.85,
                reason="complete_command",
                word_count=word_count
            )

        # PRIORITY 3: Check for complete statements
        if self._is_complete_statement(cleaned, words):
            return BoundaryDecision(
                is_complete=True,
                confidence=0.8,
                reason="complete_statement",
                word_count=word_count
            )

        # PRIORITY 4: Check for incomplete indicators (dangling words)
        if self._has_dangling_ending(words):
            return BoundaryDecision(
                is_complete=False,
                confidence=0.9,
                reason="dangling_word",
                word_count=word_count
            )

        # PRIORITY 5: Short phrases are likely incomplete
        if word_count < self.min_words_complete:
            return BoundaryDecision(
                is_complete=False,
                confidence=0.75,
                reason="too_short",
                word_count=word_count
            )

        # DEFAULT: Assume complete if no strong signals
        return BoundaryDecision(
            is_complete=True,
            confidence=0.6,
            reason="default_complete",
            word_count=word_count
        )

    def _is_complete_question(self, text: str, words: list[str]) -> bool:
        """Check if text is a complete question."""
        if len(words) < self.min_words_question:
            return False

        lowered = text.lower()
        first_word = words[0].lower()

        # Questions ending with ? are complete
        if text.endswith("?"):
            # But check for dangling words before ?
            # Example: "What is the?" is incomplete despite ?
            # However, possessive determiner + noun is complete: "my order?" is OK
            if len(words) >= 2:
                second_last = words[-2].lower().rstrip(".,!?")
                last_word = words[-1].lower().rstrip(".,!?")

                # If second_last is a dangling word, check if it forms a complete phrase
                if second_last in UtterancePatterns.DANGLING_WORDS:
                    # Possessive determiner + noun is complete
                    # e.g., "my order", "your package", "the item"
                    if second_last in UtterancePatterns.DETERMINERS and len(words) >= 3:
                        # Has a noun after determiner - complete
                        return True
                    # Bare dangling word before ? is incomplete
                    # e.g., "What is the?"
                    return False
            return True

        # Questions starting with question words (even without ?)
        # Example: "How do I return this item"
        if first_word in UtterancePatterns.QUESTION_WORDS:
            # Must have enough words
            if len(words) >= self.min_words_question:
                # Check for dangling ending
                last_word = words[-1].lower().rstrip(".,!?")
                if last_word in UtterancePatterns.DANGLING_WORDS:
                    return False
                return True

        return False

    def _is_complete_command(self, text: str, words: list[str]) -> bool:
        """Check if text is a complete command (imperative)."""
        if len(words) < self.min_words_command:
            return False

        first_word = words[0].lower()

        # Check for command verb
        if first_word not in UtterancePatterns.COMMAND_VERBS:
            # Also check for "show me", "find me" patterns
            if len(words) >= 2 and words[1].lower() == "me":
                if first_word in {"show", "find", "get", "tell", "give"}:
                    pass  # Valid command pattern
                else:
                    return False
            else:
                return False

        # Check for dangling ending (includes complex patterns)
        if self._has_dangling_ending(words):
            return False

        return True

    def _is_complete_statement(self, text: str, words: list[str]) -> bool:
        """Check if text is a complete statement."""
        if len(words) < self.min_words_complete:
            return False

        # Statements ending with period are likely complete
        if text.endswith("."):
            # But check for dangling words before period
            if len(words) >= 2:
                second_last = words[-2].lower().rstrip(".,!?")
                if second_last in UtterancePatterns.DANGLING_WORDS:
                    return False
            return True

        # Check for natural statement patterns without punctuation
        # Example: "I need gloves for chemical handling"
        if len(words) >= self.min_words_complete:
            # Check for dangling ending (includes complex patterns)
            if self._has_dangling_ending(words):
                return False

            # Has subject + verb + object structure (heuristic)
            # This is a simple check - not grammatically rigorous
            return True

        return False

    def _has_dangling_ending(self, words: list[str]) -> bool:
        """Check if last word suggests incomplete utterance."""
        if not words:
            return False

        last_word = words[-1].lower().rstrip(".,!?")

        # Check if last word is a dangling word
        if last_word in UtterancePatterns.DANGLING_WORDS:
            return True

        # Check for two-word dangling patterns
        # Example: "looking for", "waiting for", "need a"
        if len(words) >= 2:
            second_last = words[-2].lower().rstrip(".,!?")

            # "verb + preposition" patterns
            if last_word in {"for", "to", "at", "in", "on", "with", "about"}:
                if second_last in {"looking", "waiting", "searching", "asking"}:
                    return True

            # "need/want + determiner" patterns
            if last_word in {"a", "an", "the", "some"}:
                if second_last in {"need", "want", "require", "get"}:
                    return True

            # "preposition + bare singular noun" patterns (needs qualification)
            # Example: "about order" (incomplete) vs "about orders" or "about the order" (complete)
            # Common nouns that typically need qualification (number, ID, determiner)
            if second_last in {"about", "for", "regarding", "concerning"}:
                # Check if last word is a common singular noun that needs qualification
                if last_word in {"order", "product", "item", "account", "shipment", "delivery", "invoice", "payment"}:
                    return True

        return False

    def _ends_with_filler(self, text: str) -> bool:
        """Check if text ends with filler words."""
        lowered = text.lower().strip()

        # Check for trailing filler words
        for filler in UtterancePatterns.FILLER_WORDS:
            if re.search(rf"\b{filler}\s*$", lowered):
                return True

        return False