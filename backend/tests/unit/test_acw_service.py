"""Unit tests for ACWService (AI-powered ACW features).

Following TDD: Tests written FIRST, then implementation.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from app.services.acw_service import ACWService


@pytest.mark.asyncio
class TestACWService:
    """Test suite for ACWService AI-powered features."""

    @pytest.fixture
    def mock_repository(self):
        """Mock conversation repository."""
        repo = MagicMock()
        repo.get_latest_summary = AsyncMock()
        repo.get_all_transcript_lines = AsyncMock()
        repo.save_ai_interaction = AsyncMock()
        repo.save_disposition_suggestions = AsyncMock()
        repo.save_compliance_attempts = AsyncMock()
        repo.save_crm_fields = AsyncMock()
        return repo

    @pytest.fixture
    def acw_service(self, mock_repository):
        """Create ACWService instance with mocked dependencies."""
        return ACWService(repository=mock_repository, openai_api_key="test-key")

    async def test_generate_disposition_suggestions_success(
        self, acw_service, mock_repository
    ):
        """Test disposition suggestions generation from summary."""
        conversation_id = UUID("12345678-1234-5678-1234-567812345678")

        # Mock summary exists
        mock_summary = MagicMock()
        mock_summary.summary_text = (
            "Customer called about order tracking. Agent provided tracking number. "
            "Customer satisfied with resolution."
        )
        mock_repository.get_latest_summary.return_value = mock_summary

        # Mock OpenAI client at instance level
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"suggestions": [{"code": "RESOLVED", "label": "Issue Resolved", "confidence": 0.95, "reasoning": "Customer satisfied"}]}'
                )
            )
        ]
        mock_response.usage = MagicMock(total_tokens=150)
        acw_service.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await acw_service.generate_disposition_suggestions(conversation_id)

        # Verify result structure
        assert "suggestions" in result
        assert len(result["suggestions"]) > 0

        # Verify AI interaction was logged
        mock_repository.save_ai_interaction.assert_called_once()
        call_args = mock_repository.save_ai_interaction.call_args[1]
        assert call_args["conversation_id"] == conversation_id
        assert call_args["interaction_type"] == "disposition"

    async def test_suggestions_saved_to_database(
        self, acw_service, mock_repository
    ):
        """Test that suggestions are persisted to disposition_suggestions table."""
        conversation_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_summary = MagicMock()
        mock_summary.summary_text = "Test"
        mock_repository.get_latest_summary.return_value = mock_summary

        # Mock OpenAI client
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"suggestions": [{"code": "RESOLVED", "label": "Resolved", "confidence": 0.9, "reasoning": "Done"}]}'
                )
            )
        ]
        mock_response.usage = MagicMock(total_tokens=100)
        acw_service.client.chat.completions.create = AsyncMock(return_value=mock_response)

        await acw_service.generate_disposition_suggestions(conversation_id)

        # Verify suggestions were saved
        mock_repository.save_disposition_suggestions.assert_called_once()

    async def test_detect_compliance_items(
        self, acw_service, mock_repository
    ):
        """Test AI compliance detection from transcript."""
        conversation_id = UUID("12345678-1234-5678-1234-567812345678")

        # Mock transcript lines
        mock_lines = [
            MagicMock(speaker="agent", text="Can you verify your account number?"),
            MagicMock(speaker="customer", text="Sure, it's 12345"),
            MagicMock(speaker="agent", text="Thank you. I've confirmed your identity."),
            MagicMock(speaker="agent", text="I've updated your order and sent confirmation."),
        ]
        mock_repository.get_all_transcript_lines.return_value = mock_lines

        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"items": [{"label": "Verified customer identity", "detected": true, "confidence": 0.95}, {"label": "Confirmed order details", "detected": true, "confidence": 0.85}]}'
                )
            )
        ]
        mock_response.usage = MagicMock(total_tokens=200)
        acw_service.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await acw_service.detect_compliance_items(conversation_id)

        # Verify result structure
        assert "items" in result
        assert len(result["items"]) > 0
        assert result["items"][0]["detected"] is True
        assert result["items"][0]["confidence"] > 0

        # Verify AI interaction logged
        mock_repository.save_ai_interaction.assert_called()

    async def test_compliance_detection_saved_to_database(
        self, acw_service, mock_repository
    ):
        """Test that compliance attempts are persisted."""
        conversation_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_repository.get_all_transcript_lines.return_value = [
            MagicMock(speaker="agent", text="Test")
        ]

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"items": [{"label": "Identity verified", "detected": true, "confidence": 0.9}]}'
                )
            )
        ]
        mock_response.usage = MagicMock(total_tokens=100)
        acw_service.client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_repository.save_compliance_attempts = AsyncMock()

        await acw_service.detect_compliance_items(conversation_id)

        # Verify attempts saved
        mock_repository.save_compliance_attempts.assert_called_once()

    async def test_extract_crm_fields(
        self, acw_service, mock_repository
    ):
        """Test CRM field extraction from transcript."""
        conversation_id = UUID("12345678-1234-5678-1234-567812345678")

        # Mock transcript lines
        mock_lines = [
            MagicMock(speaker="customer", text="I need to track my order 771903"),
            MagicMock(speaker="agent", text="Let me look that up for you"),
            MagicMock(speaker="agent", text="The shipment was delayed due to weather"),
            MagicMock(speaker="agent", text="I've expedited shipping at no charge"),
        ]
        mock_repository.get_all_transcript_lines.return_value = mock_lines

        # Mock OpenAI response with structured CRM fields
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"fields": [{"field_name": "Case Subject", "value": "Order tracking inquiry for order 771903", "confidence": 0.95}, {"field_name": "Case Type", "value": "Order Tracking", "confidence": 0.98}, {"field_name": "Priority", "value": "High", "confidence": 0.85}, {"field_name": "Root Cause", "value": "Weather-related shipping delay", "confidence": 0.90}, {"field_name": "Resolution Action", "value": "Expedited shipping at no charge", "confidence": 0.92}]}'
                )
            )
        ]
        mock_response.usage = MagicMock(total_tokens=250)
        acw_service.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await acw_service.extract_crm_fields(conversation_id)

        # Verify result structure
        assert "fields" in result
        assert len(result["fields"]) == 5

        # Verify field names and types
        field_names = [f["field_name"] for f in result["fields"]]
        assert "Case Subject" in field_names
        assert "Case Type" in field_names
        assert "Priority" in field_names
        assert "Root Cause" in field_names
        assert "Resolution Action" in field_names

        # Verify Case Type is from taxonomy
        case_type_field = next(f for f in result["fields"] if f["field_name"] == "Case Type")
        assert case_type_field["value"] == "Order Tracking"

        # Verify Priority is from taxonomy
        priority_field = next(f for f in result["fields"] if f["field_name"] == "Priority")
        assert priority_field["value"] in ["Critical", "High", "Medium", "Low"]

        # Verify AI interaction logged
        mock_repository.save_ai_interaction.assert_called()

    async def test_crm_fields_saved_to_database(
        self, acw_service, mock_repository
    ):
        """Test that CRM field extractions are persisted."""
        conversation_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_repository.get_all_transcript_lines.return_value = [
            MagicMock(speaker="customer", text="Test transcript")
        ]

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"fields": [{"field_name": "Case Subject", "value": "Test case", "confidence": 0.9}, {"field_name": "Case Type", "value": "Other", "confidence": 0.8}, {"field_name": "Priority", "value": "Medium", "confidence": 0.85}]}'
                )
            )
        ]
        mock_response.usage = MagicMock(total_tokens=150)
        acw_service.client.chat.completions.create = AsyncMock(return_value=mock_response)

        await acw_service.extract_crm_fields(conversation_id)

        # Verify extractions saved
        mock_repository.save_crm_fields.assert_called_once()

    # ===== Model Selector Tests =====

    async def test_set_model_updates_model(self, acw_service):
        """Test that set_model changes the model used for LLM calls."""
        assert acw_service.model == "gpt-3.5-turbo"  # default
        acw_service.set_model("gpt-4o")
        assert acw_service.model == "gpt-4o"

    async def test_set_model_with_reasoning_effort(self, acw_service):
        """Test that set_model stores reasoning_effort."""
        acw_service.set_model("gpt-5", reasoning_effort="low")
        assert acw_service.model == "gpt-5"
        assert acw_service._reasoning_effort == "low"

    async def test_model_switch_during_disposition_uses_captured_config(self, mock_repository):
        """Test that model changes mid-operation don't affect in-flight API calls.

        Bug: When user switches models during ACW operations (e.g., GPT-3.5 → GPT-5),
        the API call reads self.model mid-execution, causing parameter mismatches.

        This test verifies that after the fix:
        1. Disposition generation starts with GPT-3.5
        2. Model switches to GPT-5 mid-operation
        3. API call uses the originally captured GPT-3.5 config
        """
        from uuid import UUID

        # Initialize with GPT-3.5
        acw_service = ACWService(
            repository=mock_repository,
            openai_api_key="test-key",
            model="gpt-3.5-turbo"
        )
        acw_service._reasoning_effort = None

        # Mock summary for disposition context
        mock_repository.get_latest_summary = AsyncMock(
            return_value=MagicMock(summary_text="Customer needs help with order")
        )
        mock_repository.save_ai_interaction = AsyncMock()
        mock_repository.save_disposition_suggestions = AsyncMock()

        # Track API kwargs
        captured_api_kwargs = {}

        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps({
                "suggestions": [{"code": "RESOLVED", "label": "Issue Resolved", "confidence": 0.9, "reasoning": "test"}]
            })))
        ]
        mock_response.usage = MagicMock(total_tokens=100)

        async def mock_create(*args, **kwargs):
            # Capture kwargs
            captured_api_kwargs.update(kwargs)
            return mock_response

        acw_service.client.chat.completions.create = mock_create

        # Monkey-patch to switch model mid-operation
        original_get_summary = mock_repository.get_latest_summary

        async def get_summary_with_switch(*args, **kwargs):
            # Switch model during operation
            acw_service.model = "gpt-5"
            acw_service._reasoning_effort = "low"
            return await original_get_summary(*args, **kwargs)

        mock_repository.get_latest_summary = get_summary_with_switch

        # Generate disposition suggestions
        conversation_id = UUID("12345678-1234-1234-1234-123456789012")
        await acw_service.generate_disposition_suggestions(conversation_id)

        # Verify the API call used GPT-3.5 config (captured at start), not GPT-5
        assert captured_api_kwargs["model"] == "gpt-3.5-turbo", \
            "API call should use originally captured model (GPT-3.5), not switched model (GPT-5)"
        assert "temperature" in captured_api_kwargs, \
            "GPT-3.5 should use temperature parameter"
        assert "reasoning_effort" not in captured_api_kwargs, \
            "GPT-3.5 should NOT have reasoning_effort parameter"

        # Verify logged model also uses captured config
        save_ai_call = mock_repository.save_ai_interaction.call_args
        assert save_ai_call[1]["model_name"] == "gpt-3.5-turbo", \
            "Logged model should match captured config"
