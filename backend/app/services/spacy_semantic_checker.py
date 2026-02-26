"""spaCy-based semantic analysis for utterance boundary detection.

Provides dependency-tree analysis to catch incomplete utterances that
heuristic pattern matching misses (e.g., hanging prepositions, missing
verb arguments, incomplete noun phrases).

Ported from demo_voice_assistant/src/gateway/semantic_checker.py
with adaptations:
- Imports constants from UtterancePatterns (not demo's UtteranceNLP)
- Uses structlog instead of stdlib logging
- Hardcodes disable=["ner", "textcat"] (not configurable)
- Model name passed as constructor arg

This module is optional. The application works identically without spaCy
installed — see ADR-025 in ARCHITECTURAL_DECISIONS.md.
"""

from __future__ import annotations

import importlib
import time
from dataclasses import dataclass
from typing import Any, Optional, Tuple

import structlog

from app.services.utterance_boundary_detector import UtterancePatterns

try:
    import spacy
except ImportError:
    spacy = None  # type: ignore[assignment]

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CompletenessResult:
    """Result of semantic completeness analysis."""

    is_complete: bool
    confidence: float
    reason: str
    processing_time_ms: float


class SpacySemanticChecker:
    """Semantic completeness checker using spaCy dependency parsing.

    Execution flow:
    1. _quick_checks() — fast pattern matching for obvious cases (< 0.1ms)
    2. self.nlp(text) — spaCy dependency parse (1-5ms with en_core_web_sm)
    3. _analyze_syntax() — dependency tree analysis with 6 sub-checks

    Usage:
        checker = SpacySemanticChecker()
        result = checker.is_complete("I need gloves for")
        # result.is_complete=False, result.reason="ends_with_preposition"
    """

    def __init__(self, model_name: str = "en_core_web_sm") -> None:
        spacy_mod = spacy
        if spacy_mod is None:
            try:
                spacy_mod = importlib.import_module("spacy")
            except ImportError as e:
                raise ImportError("spaCy is not installed") from e

        self.nlp = spacy_mod.load(model_name, disable=["ner", "textcat"])
        logger.info(
            "spacy_semantic_checker_loaded",
            model=model_name,
            disabled=["ner", "textcat"],
        )

    def is_complete(self, text: str, context: Optional[dict] = None) -> CompletenessResult:
        """Analyze text for syntactic completeness.

        Args:
            text: Utterance text to analyze.
            context: Optional context dict (reserved for future use).

        Returns:
            CompletenessResult with is_complete, confidence, reason, processing_time_ms.
        """
        start_time = time.perf_counter()

        text = text.strip()
        if not text:
            return CompletenessResult(False, 0.0, "empty_text", 0.0)

        quick_result = self._quick_checks(text)
        if quick_result:
            processing_time = (time.perf_counter() - start_time) * 1000
            return CompletenessResult(
                quick_result[0], quick_result[1], quick_result[2], processing_time
            )

        doc = self.nlp(text)
        result = self._analyze_syntax(doc, text)

        processing_time = (time.perf_counter() - start_time) * 1000
        return CompletenessResult(result[0], result[1], result[2], processing_time)

    def _quick_checks(self, text: str) -> Optional[Tuple[bool, float, str]]:
        """Fast pattern matching for obvious complete/incomplete cases."""
        words = text.split()
        if len(words) == 1:
            return False, 0.9, "single_word"

        last_word = words[-1].lower().rstrip(".,!?")

        # Short fragments starting with coordinating conjunction
        first_word = words[0].lower()
        if first_word in {"and", "or", "but"} and len(words) <= 3:
            return False, 0.9, "starts_with_conjunction"

        if last_word in UtterancePatterns.CONTINUATION_WORDS:
            return False, 0.95, "ends_with_conjunction"

        if last_word in UtterancePatterns.PREPOSITIONS:
            return False, 0.9, "ends_with_preposition"

        if last_word in UtterancePatterns.DETERMINERS:
            return False, 0.9, "ends_with_determiner"

        # Complete question: question word + "?" + 3+ words
        if (
            text.lower().startswith(UtterancePatterns.QUESTION_START_WORDS_TUPLE)
            and text.endswith("?")
            and len(words) >= 3
        ):
            return True, 0.9, "complete_question"

        # Complete command: command verb + 3+ words + non-dangling ending
        # Union of COMMAND_VERBS and TRANSITIVE_COMMAND_VERBS to cover all
        # imperative verbs (e.g., "turn" is in TRANSITIVE but not COMMAND)
        command_verbs = UtterancePatterns.COMMAND_VERBS | UtterancePatterns.TRANSITIVE_COMMAND_VERBS
        if (
            first_word in command_verbs
            and len(words) >= 3
            and last_word not in UtterancePatterns.CONTINUATION_WORDS
            and last_word not in UtterancePatterns.PREPOSITIONS
            and last_word not in UtterancePatterns.DETERMINERS
        ):
            return True, 0.8, "complete_command"

        return None

    def _analyze_syntax(self, doc: Any, text: str) -> Tuple[bool, float, str]:
        """Analyze spaCy dependency tree for completeness."""
        if not doc:
            return False, 0.5, "parse_failed"

        roots = [token for token in doc if token.dep_ == "ROOT"]
        if not roots:
            return False, 0.8, "no_root_predicate"

        root = roots[0]
        confidence = 0.7

        if self._is_incomplete_question(doc, root):
            return False, 0.9, "incomplete_question"

        if self._has_hanging_preposition(doc):
            return False, 0.85, "hanging_preposition"

        if self._has_incomplete_noun_phrase(doc):
            return False, 0.8, "incomplete_noun_phrase"

        if self._missing_required_arguments(doc, root):
            return False, 0.75, "missing_arguments"

        if self._has_incomplete_clause(doc, root):
            return False, 0.8, "incomplete_clause"

        # Boost confidence for punctuated endings
        if text.endswith((".", "!", "?")):
            confidence += 0.15

        if self._has_complete_predicate_structure(doc, root):
            confidence += 0.1

        if self._is_natural_ending(doc):
            confidence += 0.1

        return True, min(confidence, 0.95), "syntactically_complete"

    def _is_incomplete_question(self, doc: Any, root: Any) -> bool:
        """Detect incomplete questions (question word + short/dangling ending)."""
        tokens = [t.text.lower() for t in doc]
        if not tokens:
            return False

        question_start_set = frozenset(UtterancePatterns.QUESTION_START_WORDS_TUPLE)

        if tokens[0] in question_start_set and not doc[-1].text.endswith("?"):
            if len(tokens) <= 3:
                return True

            last = tokens[-1].rstrip(".,!?")
            if last in UtterancePatterns.DETERMINERS:
                return True
            if last in UtterancePatterns.PREPOSITIONS:
                return True
            if last in UtterancePatterns.CONTINUATION_WORDS:
                return True

        # Special case: "how" questions ≤ 3 words are almost always incomplete
        if tokens[0] == "how" and len(tokens) <= 3:
            return True

        return False

    def _has_hanging_preposition(self, doc: Any) -> bool:
        """Detect preposition at end without a prepositional object."""
        if len(doc) < 2:
            return False

        last_token = doc[-1]
        if last_token.pos_ == "ADP":
            return True

        second_last = doc[-2]
        if second_last.pos_ == "ADP" and not any(
            child.dep_ == "pobj" for child in second_last.children
        ):
            return True

        return False

    def _has_incomplete_noun_phrase(self, doc: Any) -> bool:
        """Detect determiner near end with no noun to attach to."""
        for token in doc:
            if token.pos_ == "DET":
                if token.i == len(doc) - 1 or token.i == len(doc) - 2:
                    head_children = list(token.head.children)
                    if not any(
                        child.pos_ in ("NOUN", "PROPN") for child in head_children
                    ):
                        return True
        return False

    def _missing_required_arguments(self, doc: Any, root: Any) -> bool:
        """Detect transitive verb without required direct object."""
        if root.lemma_.lower() in UtterancePatterns.TRANSITIVE_COMMAND_VERBS:
            has_object = any(
                child.dep_ in ("dobj", "attr", "prep") for child in root.children
            )
            if not has_object:
                return True

        return False

    def _has_incomplete_clause(self, doc: Any, root: Any) -> bool:
        """Detect subordinating conjunction at end (clause started but not finished)."""
        last_words = [t.text.lower() for t in doc[-2:]]
        if any(
            word in UtterancePatterns.SUBORDINATING_CONJUNCTIONS for word in last_words
        ):
            return True

        return False

    def _has_complete_predicate_structure(self, doc: Any, root: Any) -> bool:
        """Check for subject + verb + object structure (boosts confidence)."""
        has_subject = any(
            child.dep_ in ("nsubj", "nsubjpass") for child in root.children
        )

        if root.lemma_.lower() in UtterancePatterns.PREDICATE_VERBS_REQUIRE_OBJECT:
            has_object = any(
                child.dep_ in ("dobj", "attr", "prep") for child in root.children
            )
            return has_subject and has_object

        return has_subject

    def _is_natural_ending(self, doc: Any) -> bool:
        """Check for natural ending words like 'please', 'thanks'."""
        # Check single last token (e.g., "please", "thanks", "today")
        if doc[-1].text.lower() in UtterancePatterns.NATURAL_ENDINGS:
            return True
        # Check 2-token window (e.g., "thank you", "right now")
        if len(doc) >= 2:
            last_few = " ".join(t.text.lower() for t in doc[-2:]).strip()
            if last_few in UtterancePatterns.NATURAL_ENDINGS:
                return True
        return False
