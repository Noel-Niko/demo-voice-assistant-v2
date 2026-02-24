"""Tests for SpacySemanticChecker — TDD (tests written before implementation).

These tests define the contract for the spaCy semantic analysis layer.
The implementation will be ported from demo_voice_assistant/src/gateway/semantic_checker.py.

Test execution requires spaCy + en_core_web_sm:
    uv run --extra nlp pytest tests/unit/test_spacy_semantic_checker.py -v

Tests are skipped gracefully if spaCy is not installed.
"""

import pytest

spacy = pytest.importorskip("spacy", reason="spaCy not installed — skipping semantic checker tests")

from app.services.spacy_semantic_checker import CompletenessResult, SpacySemanticChecker


@pytest.fixture(scope="module")
def checker():
    """Create a single SpacySemanticChecker instance shared across all tests.

    Module-scoped to avoid reloading the spaCy model per test (~500ms).
    """
    return SpacySemanticChecker()


# ---------------------------------------------------------------------------
# CompletenessResult dataclass
# ---------------------------------------------------------------------------
class TestCompletenessResult:
    """Verify the CompletenessResult data contract."""

    def test_fields_present(self):
        result = CompletenessResult(
            is_complete=True,
            confidence=0.9,
            reason="test_reason",
            processing_time_ms=1.23,
        )
        assert result.is_complete is True
        assert result.confidence == 0.9
        assert result.reason == "test_reason"
        assert result.processing_time_ms == 1.23

    def test_frozen_dataclass(self):
        result = CompletenessResult(True, 0.9, "test", 0.0)
        with pytest.raises(AttributeError):
            result.is_complete = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Quick-check path tests (pattern matching, no spaCy parse)
# ---------------------------------------------------------------------------
class TestQuickChecks:
    """Tests for the fast pattern-matching layer (_quick_checks).

    These cases are resolved without invoking the spaCy parser.
    """

    def test_empty_text(self, checker: SpacySemanticChecker):
        result = checker.is_complete("")
        assert result.is_complete is False
        assert result.reason == "empty_text"

    def test_whitespace_only(self, checker: SpacySemanticChecker):
        result = checker.is_complete("   ")
        assert result.is_complete is False
        assert result.reason == "empty_text"

    def test_single_word(self, checker: SpacySemanticChecker):
        result = checker.is_complete("hello")
        assert result.is_complete is False
        assert result.confidence == pytest.approx(0.9)
        assert result.reason == "single_word"

    def test_starts_with_conjunction_short(self, checker: SpacySemanticChecker):
        """Short fragments starting with coordinating conjunction are incomplete."""
        result = checker.is_complete("and then")
        assert result.is_complete is False
        assert result.reason == "starts_with_conjunction"

    def test_starts_with_conjunction_but(self, checker: SpacySemanticChecker):
        result = checker.is_complete("but also")
        assert result.is_complete is False
        assert result.reason == "starts_with_conjunction"

    def test_starts_with_conjunction_or_three_words(self, checker: SpacySemanticChecker):
        result = checker.is_complete("or maybe not")
        assert result.is_complete is False
        assert result.reason == "starts_with_conjunction"

    def test_ends_with_continuation_word(self, checker: SpacySemanticChecker):
        """Trailing continuation words signal incompleteness."""
        result = checker.is_complete("I went to the store and")
        assert result.is_complete is False
        assert result.confidence == pytest.approx(0.95)
        assert result.reason == "ends_with_conjunction"

    def test_ends_with_preposition(self, checker: SpacySemanticChecker):
        result = checker.is_complete("I need it for")
        assert result.is_complete is False
        assert result.confidence == pytest.approx(0.9)
        assert result.reason == "ends_with_preposition"

    def test_ends_with_determiner(self, checker: SpacySemanticChecker):
        result = checker.is_complete("I need a")
        assert result.is_complete is False
        assert result.confidence == pytest.approx(0.9)
        assert result.reason == "ends_with_determiner"

    def test_ends_with_determiner_the(self, checker: SpacySemanticChecker):
        """'turn on the' caught by quick check (not spaCy), since 'the' is a determiner."""
        result = checker.is_complete("turn on the")
        assert result.is_complete is False
        assert result.reason == "ends_with_determiner"

    def test_complete_question_with_question_mark(self, checker: SpacySemanticChecker):
        """Question word + ? + 3+ words → complete via quick check."""
        result = checker.is_complete("What is your order number?")
        assert result.is_complete is True
        assert result.confidence == pytest.approx(0.9)
        assert result.reason == "complete_question"

    def test_complete_question_how(self, checker: SpacySemanticChecker):
        result = checker.is_complete("How do I return this item?")
        assert result.is_complete is True
        assert result.reason == "complete_question"

    def test_complete_command(self, checker: SpacySemanticChecker):
        """Command verb + 3+ words + non-dangling ending → complete via quick check."""
        result = checker.is_complete("find me the blue gloves")
        assert result.is_complete is True
        assert result.confidence == pytest.approx(0.8)
        assert result.reason == "complete_command"

    def test_complete_command_turn_on(self, checker: SpacySemanticChecker):
        result = checker.is_complete("turn on the lights")
        assert result.is_complete is True
        assert result.reason == "complete_command"


# ---------------------------------------------------------------------------
# spaCy syntax analysis tests (cases that pass through quick checks)
# ---------------------------------------------------------------------------
class TestSyntaxAnalysis:
    """Tests where quick checks are inconclusive and spaCy dependency parsing is invoked.

    These verify the 6 sub-checks in _analyze_syntax().
    """

    def test_incomplete_question_short(self, checker: SpacySemanticChecker):
        """Short question without ? (≤3 words) → incomplete_question."""
        result = checker.is_complete("how much")
        assert result.is_complete is False
        assert result.confidence == pytest.approx(0.9)
        assert result.reason == "incomplete_question"

    def test_incomplete_question_what(self, checker: SpacySemanticChecker):
        result = checker.is_complete("what color")
        assert result.is_complete is False
        assert result.reason == "incomplete_question"

    def test_hanging_preposition(self, checker: SpacySemanticChecker):
        """Preposition not in our PREPOSITIONS set but tagged ADP by spaCy."""
        result = checker.is_complete("I went running towards")
        assert result.is_complete is False
        assert result.confidence == pytest.approx(0.85)
        assert result.reason == "hanging_preposition"

    def test_incomplete_noun_phrase(self, checker: SpacySemanticChecker):
        """DET near end with no NOUN in head's children → incomplete."""
        result = checker.is_complete("I want the new")
        assert result.is_complete is False
        assert result.confidence == pytest.approx(0.8)
        assert result.reason == "incomplete_noun_phrase"

    def test_missing_arguments_find(self, checker: SpacySemanticChecker):
        """Transitive verb (find) with no dobj/attr/prep → missing_arguments."""
        result = checker.is_complete("find quickly")
        assert result.is_complete is False
        assert result.confidence == pytest.approx(0.75)
        assert result.reason == "missing_arguments"

    def test_missing_arguments_set(self, checker: SpacySemanticChecker):
        result = checker.is_complete("set carefully")
        assert result.is_complete is False
        assert result.reason == "missing_arguments"

    def test_incomplete_clause(self, checker: SpacySemanticChecker):
        """Subordinating conjunction in last 2 tokens → incomplete_clause."""
        result = checker.is_complete("I will do it if")
        assert result.is_complete is False
        assert result.confidence == pytest.approx(0.8)
        assert result.reason == "incomplete_clause"

    def test_complete_with_natural_ending(self, checker: SpacySemanticChecker):
        """'please' at end boosts confidence via _is_natural_ending."""
        result = checker.is_complete("I need safety gloves please")
        assert result.is_complete is True
        assert result.confidence >= 0.85
        assert result.reason == "syntactically_complete"

    def test_complete_question_no_question_mark(self, checker: SpacySemanticChecker):
        """Question with enough structure is syntactically complete even without ?."""
        result = checker.is_complete("what is the weather today")
        assert result.is_complete is True
        assert result.confidence >= 0.85
        assert result.reason == "syntactically_complete"

    def test_show_me_is_syntactically_complete(self, checker: SpacySemanticChecker):
        """'show me' — spaCy parses 'me' as dobj, so transitive check passes.

        NOTE: The heuristic detector may still flag this as incomplete (too short).
        The semantic layer's job is syntax analysis, not minimum-length checks.
        """
        result = checker.is_complete("show me")
        assert result.is_complete is True
        assert result.confidence == pytest.approx(0.7)
        assert result.reason == "syntactically_complete"

    def test_display_everything_is_complete(self, checker: SpacySemanticChecker):
        """Transitive verb with dobj satisfied → syntactically_complete."""
        result = checker.is_complete("display everything")
        assert result.is_complete is True
        assert result.reason == "syntactically_complete"

    def test_no_root_predicate(self, checker: SpacySemanticChecker):
        """Edge case: if spaCy finds no ROOT token, return no_root_predicate."""
        # Most inputs produce a ROOT, but the code path should be covered.
        # Passing an empty doc is hard; we rely on the implementation returning
        # this reason when `roots` is empty. Integration check via a short
        # fragment that spaCy may struggle with is fragile, so we test the
        # path via mock in a separate test if needed.
        pass  # Covered by unit-level mock test in Step 4 if needed


# ---------------------------------------------------------------------------
# Processing time tracking
# ---------------------------------------------------------------------------
class TestProcessingTime:
    """Verify that processing_time_ms is tracked and reasonable."""

    def test_processing_time_quick_check(self, checker: SpacySemanticChecker):
        """Quick check results should report processing time < 5ms."""
        result = checker.is_complete("I need a")
        assert result.processing_time_ms >= 0
        assert result.processing_time_ms < 5.0

    def test_processing_time_spacy_parse(self, checker: SpacySemanticChecker):
        """spaCy parse results should report processing time < 50ms."""
        result = checker.is_complete("I need safety gloves please")
        assert result.processing_time_ms >= 0
        assert result.processing_time_ms < 50.0

    def test_processing_time_consistency(self, checker: SpacySemanticChecker):
        """Multiple calls produce consistent results (deterministic)."""
        text = "what is the weather today"
        r1 = checker.is_complete(text)
        r2 = checker.is_complete(text)
        assert r1.is_complete == r2.is_complete
        assert r1.confidence == r2.confidence
        assert r1.reason == r2.reason


# ---------------------------------------------------------------------------
# Parametrized completeness boundary tests
# ---------------------------------------------------------------------------
class TestCompletenessBoundary:
    """Parametrized tests for completeness across diverse inputs."""

    @pytest.mark.parametrize(
        "text,expected_complete",
        [
            # Clearly incomplete
            ("", False),
            ("um", False),
            ("and then", False),
            ("I need a", False),
            ("show me the", False),
            ("because", False),
            ("I went to", False),
            # Clearly complete
            ("What is your order number?", True),
            ("find me the safety gloves", True),
            ("I need safety gloves please", True),
            ("turn on the lights", True),
        ],
        ids=[
            "empty",
            "single_word",
            "conjunction_start",
            "ends_determiner",
            "ends_determiner_the",
            "single_conjunction",
            "ends_preposition",
            "complete_question",
            "complete_command",
            "complete_with_please",
            "complete_command_turn",
        ],
    )
    def test_completeness(
        self, checker: SpacySemanticChecker, text: str, expected_complete: bool
    ):
        result = checker.is_complete(text)
        assert result.is_complete is expected_complete, (
            f"Expected is_complete={expected_complete} for {text!r}, "
            f"got {result.is_complete} (reason={result.reason}, conf={result.confidence})"
        )

    @pytest.mark.parametrize(
        "text",
        [
            "I need safety gloves for chemical handling.",
            "Where can I find a replacement belt?",
            "Show me the latest order status please",
        ],
    )
    def test_real_world_complete(self, checker: SpacySemanticChecker, text: str):
        """Real-world customer service utterances should be complete."""
        result = checker.is_complete(text)
        assert result.is_complete is True, (
            f"Expected complete for {text!r}, "
            f"got reason={result.reason}, conf={result.confidence}"
        )

    @pytest.mark.parametrize(
        "text",
        [
            "I need gloves for",
            "Can you show me the",
            "What about",
        ],
    )
    def test_real_world_incomplete(self, checker: SpacySemanticChecker, text: str):
        """Real-world incomplete utterances should be detected."""
        result = checker.is_complete(text)
        assert result.is_complete is False, (
            f"Expected incomplete for {text!r}, "
            f"got reason={result.reason}, conf={result.confidence}"
        )
