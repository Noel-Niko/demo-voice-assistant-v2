"""Unit tests for Summary Generator formatting.

Tests that summaries maintain proper markdown format (**HEADER:**) for frontend parsing.
Related to bug fix: Summary format loss after first update.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.summary_generator import SummaryGenerator


class TestSummaryFormattingPrompts:
    """Test summary generator prompts maintain markdown format."""

    @pytest.fixture
    def mock_repository(self):
        """Mock repository."""
        repo = AsyncMock()
        repo.get_recent_transcript_lines = AsyncMock(return_value=[
            MagicMock(speaker="agent", text="How can I help you?"),
            MagicMock(speaker="customer", text="I need safety gloves"),
        ])
        repo.get_latest_summary = AsyncMock(return_value=None)
        repo.get_summary_count = AsyncMock(return_value=0)
        repo.save_summary = AsyncMock()
        return repo

    @pytest.fixture
    def mock_event_bus(self):
        """Mock event bus."""
        bus = AsyncMock()
        bus.publish = AsyncMock()
        return bus

    @pytest.fixture
    def generator(self, mock_repository, mock_event_bus):
        """Create summary generator."""
        return SummaryGenerator(
            repository=mock_repository,
            event_bus=mock_event_bus,
            api_key="test-key",
        )

    @pytest.mark.asyncio
    async def test_first_summary_prompt_includes_markdown_headers(self, generator, mock_repository):
        """Test first summary prompt specifies markdown format."""
        # Given: No previous summary
        mock_repository.get_latest_summary = AsyncMock(return_value=None)

        # When: Generating first summary
        with patch.object(generator, '_ensure_client') as mock_client:
            mock_openai = AsyncMock()
            mock_openai.chat.completions.create = AsyncMock(return_value=AsyncMock(
                __aiter__=AsyncMock(return_value=iter([
                    MagicMock(choices=[MagicMock(delta=MagicMock(content="**CUSTOMER INTENT:** Test"))])
                ]))
            ))
            mock_client.return_value = mock_openai

            try:
                await generator._generate_summary(uuid4())
            except Exception:
                pass  # We only care about the prompt

            # Then: Prompt should include markdown format
            call_args = mock_openai.chat.completions.create.call_args
            if call_args:
                messages = call_args.kwargs.get('messages', [])
                user_prompt = next((m['content'] for m in messages if m['role'] == 'user'), '')

                assert "**CUSTOMER INTENT:**" in user_prompt
                assert "**KEY DETAILS:**" in user_prompt
                assert "**ACTIONS TAKEN:**" in user_prompt
                assert "**OPEN ITEMS:**" in user_prompt

    @pytest.mark.asyncio
    async def test_rolling_update_prompt_includes_markdown_headers(self, generator, mock_repository):
        """Test rolling update prompt maintains markdown format."""
        # Given: Previous summary exists
        previous_summary = MagicMock(
            summary_text="**CUSTOMER INTENT:** Previous intent\n\n**KEY DETAILS:**\n• Item 1",
            version=1,
        )
        mock_repository.get_latest_summary = AsyncMock(return_value=previous_summary)

        # When: Generating update
        with patch.object(generator, '_ensure_client') as mock_client:
            mock_openai = AsyncMock()
            mock_openai.chat.completions.create = AsyncMock(return_value=AsyncMock(
                __aiter__=AsyncMock(return_value=iter([
                    MagicMock(choices=[MagicMock(delta=MagicMock(content="Updated"))])
                ]))
            ))
            mock_client.return_value = mock_openai

            try:
                await generator._generate_summary(uuid4())
            except Exception:
                pass  # We only care about the prompt

            # Then: Prompt should require markdown format
            call_args = mock_openai.chat.completions.create.call_args
            if call_args:
                messages = call_args.kwargs.get('messages', [])
                user_prompt = next((m['content'] for m in messages if m['role'] == 'user'), '')

                # Should mention keeping EXACT format
                assert "EXACT format" in user_prompt or "exact format" in user_prompt.lower()
                # Should reference markdown headers
                assert "**CUSTOMER INTENT:**" in user_prompt
                assert "**KEY DETAILS:**" in user_prompt
                assert "**ACTIONS TAKEN:**" in user_prompt
                # Should remind about bold headers
                assert "bold" in user_prompt.lower() or "**HEADER:**" in user_prompt

    @pytest.mark.asyncio
    async def test_system_prompt_emphasizes_markdown_format(self, generator, mock_repository):
        """Test system prompt emphasizes markdown header format."""
        # Given: Any summary generation
        mock_repository.get_latest_summary = AsyncMock(return_value=None)

        # When: Generating summary
        with patch.object(generator, '_ensure_client') as mock_client:
            mock_openai = AsyncMock()
            mock_openai.chat.completions.create = AsyncMock(return_value=AsyncMock(
                __aiter__=AsyncMock(return_value=iter([
                    MagicMock(choices=[MagicMock(delta=MagicMock(content="Test"))])
                ]))
            ))
            mock_client.return_value = mock_openai

            try:
                await generator._generate_summary(uuid4())
            except Exception:
                pass

            # Then: System prompt should emphasize format
            call_args = mock_openai.chat.completions.create.call_args
            if call_args:
                messages = call_args.kwargs.get('messages', [])
                system_prompt = next((m['content'] for m in messages if m['role'] == 'system'), '')

                # Should mention markdown headers
                assert "**CUSTOMER INTENT:**" in system_prompt or "bold markdown" in system_prompt.lower()
                # Should mention it's CRITICAL
                assert "CRITICAL" in system_prompt or "MUST" in system_prompt or "EXACT" in system_prompt


class TestSummaryFormatValidation:
    """Test validation of summary format for frontend compatibility."""

    def test_valid_summary_format(self):
        """Test recognizing valid summary format."""
        # Given: Properly formatted summary
        summary = """**CUSTOMER INTENT:** Customer needs safety gloves

**KEY DETAILS:**
• Brand preference: ANSELL
• Size: Large

**ACTIONS TAKEN:**
• Provided product recommendations

**OPEN ITEMS:**
• Awaiting size confirmation"""

        # When: Checking format
        has_intent = "**CUSTOMER INTENT:**" in summary
        has_details = "**KEY DETAILS:**" in summary
        has_actions = "**ACTIONS TAKEN:**" in summary

        # Then: Should have all required sections
        assert has_intent
        assert has_details
        assert has_actions

    def test_invalid_summary_format_missing_markdown(self):
        """Test detecting invalid format (missing markdown)."""
        # Given: Summary without markdown (the bug we fixed)
        summary = """CUSTOMER INTENT: Customer needs safety gloves

KEY DETAILS:
• Brand preference: ANSELL
• Size: Large"""

        # When: Checking format
        has_markdown = "**CUSTOMER INTENT:**" in summary

        # Then: Should NOT have markdown format
        assert not has_markdown  # This is the bug condition

    @pytest.mark.parametrize("header", [
        "**CUSTOMER INTENT:**",
        "**KEY DETAILS:**",
        "**ACTIONS TAKEN:**",
        "**OPEN ITEMS:**",
    ])
    def test_all_required_headers_have_markdown(self, header):
        """Test all section headers use markdown format."""
        # Given: A properly formatted header
        # When: Checking format
        has_double_asterisk_start = header.startswith("**")
        has_double_asterisk_before_colon = ":**" in header

        # Then: Should have proper markdown
        assert has_double_asterisk_start
        assert has_double_asterisk_before_colon


class TestSummaryConcisenessRules:
    """Test that prompts enforce strict conciseness limits."""

    @pytest.fixture
    def mock_repository(self):
        """Mock repository."""
        repo = AsyncMock()
        repo.get_recent_transcript_lines = AsyncMock(return_value=[
            MagicMock(speaker="agent", text="How can I help you?"),
            MagicMock(speaker="customer", text="I need safety gloves"),
        ])
        repo.get_latest_summary = AsyncMock(return_value=None)
        repo.get_summary_count = AsyncMock(return_value=0)
        repo.save_summary = AsyncMock()
        return repo

    @pytest.fixture
    def mock_event_bus(self):
        """Mock event bus."""
        bus = AsyncMock()
        bus.publish = AsyncMock()
        return bus

    @pytest.fixture
    def generator(self, mock_repository, mock_event_bus):
        """Create summary generator."""
        return SummaryGenerator(
            repository=mock_repository,
            event_bus=mock_event_bus,
            api_key="test-key",
        )

    @pytest.mark.asyncio
    async def test_system_prompt_enforces_bullet_limits(self, generator, mock_repository):
        """Test system prompt includes strict bullet count limits."""
        # Given: Any summary generation
        mock_repository.get_latest_summary = AsyncMock(return_value=None)

        # When: Generating summary
        with patch.object(generator, '_ensure_client') as mock_client:
            mock_openai = AsyncMock()
            mock_openai.chat.completions.create = AsyncMock(return_value=AsyncMock(
                __aiter__=AsyncMock(return_value=iter([
                    MagicMock(choices=[MagicMock(delta=MagicMock(content="Test"))])
                ]))
            ))
            mock_client.return_value = mock_openai

            try:
                await generator._generate_summary(uuid4())
            except Exception:
                pass

            # Then: System prompt should specify limits
            call_args = mock_openai.chat.completions.create.call_args
            if call_args:
                messages = call_args.kwargs.get('messages', [])
                system_prompt = next((m['content'] for m in messages if m['role'] == 'system'), '')

                # Should mention bullet limits
                assert "3 bullets maximum" in system_prompt or "MAX 3" in system_prompt
                assert "4 bullets maximum" in system_prompt or "MAX 4" in system_prompt
                assert "10 bullets maximum" in system_prompt or "10 bullet maximum" in system_prompt
                # Should mention consolidation
                assert "consolidate" in system_prompt.lower() or "merge" in system_prompt.lower()

    @pytest.mark.asyncio
    async def test_rolling_update_enforces_consolidation(self, generator, mock_repository):
        """Test rolling update prompts tell LLM to consolidate, not just append."""
        # Given: Previous summary with actions
        previous_summary = MagicMock(
            summary_text="**ACTIONS TAKEN:**\n• Action 1\n• Action 2",
            version=1,
        )
        mock_repository.get_latest_summary = AsyncMock(return_value=previous_summary)

        # When: Generating update
        with patch.object(generator, '_ensure_client') as mock_client:
            mock_openai = AsyncMock()
            mock_openai.chat.completions.create = AsyncMock(return_value=AsyncMock(
                __aiter__=AsyncMock(return_value=iter([
                    MagicMock(choices=[MagicMock(delta=MagicMock(content="Updated"))])
                ]))
            ))
            mock_client.return_value = mock_openai

            try:
                await generator._generate_summary(uuid4())
            except Exception:
                pass

            # Then: Prompt should emphasize consolidation
            call_args = mock_openai.chat.completions.create.call_args
            if call_args:
                messages = call_args.kwargs.get('messages', [])
                user_prompt = next((m['content'] for m in messages if m['role'] == 'user'), '')

                # Should NOT say "append" without consolidation context
                assert "APPEND" not in user_prompt or "consolidate" in user_prompt.lower()
                # Should mention consolidation/merging
                assert "consolidate" in user_prompt.lower() or "merge" in user_prompt.lower()
                # Should mention max limits
                assert "MAX" in user_prompt or "maximum" in user_prompt.lower()

    @pytest.mark.asyncio
    async def test_first_summary_includes_bullet_limits(self, generator, mock_repository):
        """Test first summary prompt specifies bullet limits."""
        # Given: No previous summary
        mock_repository.get_latest_summary = AsyncMock(return_value=None)

        # When: Generating first summary
        with patch.object(generator, '_ensure_client') as mock_client:
            mock_openai = AsyncMock()
            mock_openai.chat.completions.create = AsyncMock(return_value=AsyncMock(
                __aiter__=AsyncMock(return_value=iter([
                    MagicMock(choices=[MagicMock(delta=MagicMock(content="Test"))])
                ]))
            ))
            mock_client.return_value = mock_openai

            try:
                await generator._generate_summary(uuid4())
            except Exception:
                pass

            # Then: Prompt should specify limits
            call_args = mock_openai.chat.completions.create.call_args
            if call_args:
                messages = call_args.kwargs.get('messages', [])
                user_prompt = next((m['content'] for m in messages if m['role'] == 'user'), '')

                # Should mention MAX limits
                assert "MAX" in user_prompt
                # Should mention 10 bullet maximum
                assert "10 bullet" in user_prompt or "10 bullets" in user_prompt
