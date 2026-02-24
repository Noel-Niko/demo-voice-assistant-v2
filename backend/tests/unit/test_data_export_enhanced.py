"""Tests for enhanced DataExportService with additional metrics.

Validates the new export sections (compliance, content edits, disposition
suggestions, listening mode sessions, CRM extractions) and enhanced
metrics calculations (model breakdown, type breakdown).
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock
from datetime import datetime, timezone

from app.services.data_export_service import DataExportService


def _make_ai_interaction(
    model_name="gpt-3.5-turbo",
    interaction_type="summary",
    tokens_used=100,
    cost_usd=0.01,
    latency_ms=200,
):
    """Helper to create a mock AIInteraction."""
    ai = MagicMock()
    ai.model_name = model_name
    ai.interaction_type = interaction_type
    ai.tokens_used = tokens_used
    ai.cost_usd = cost_usd
    ai.latency_ms = latency_ms
    ai.prompt_text = "test prompt"
    ai.response_text = "test response"
    ai.agent_edited = False
    ai.created_at = datetime(2026, 2, 22, 10, 0, 0, tzinfo=timezone.utc)
    return ai


def _make_mock_repository():
    """Create a mock repository with all required methods."""
    repo = AsyncMock()

    conv = MagicMock()
    conv.agent_id = "agent-1"
    conv.customer_id = "cust-1"
    conv.recording_id = None
    conv.queue_name = None
    conv.interaction_id = None
    conv.status = "completed"
    conv.started_at = datetime(2026, 2, 22, 10, 0, 0, tzinfo=timezone.utc)
    conv.ended_at = datetime(2026, 2, 22, 10, 5, 0, tzinfo=timezone.utc)
    conv.disposition_code = "RESOLVED"
    conv.wrap_up_notes = "Done"
    conv.agent_feedback = "up"
    conv.acw_duration_secs = 30
    conv.transcript_lines = []

    repo.get_conversation.return_value = conv
    repo.get_all_summaries.return_value = []
    repo.get_agent_interactions.return_value = []
    repo.get_ai_interactions.return_value = []
    repo.get_compliance_attempts.return_value = []
    repo.get_content_edits.return_value = []
    repo.get_disposition_suggestions.return_value = []
    repo.get_listening_mode_sessions.return_value = []
    repo.get_crm_field_extractions.return_value = []
    return repo


class TestEnhancedExportFormatVersion:
    """Test format version bump."""

    @pytest.mark.asyncio
    async def test_export_format_version_2(self, tmp_path):
        """Export should use format version 2.0."""
        repo = _make_mock_repository()
        service = DataExportService(repo)

        path = await service.export_conversation_data("test-conv-id")

        with open(path) as f:
            data = json.load(f)
        assert data["export_metadata"]["format_version"] == "2.0"


class TestEnhancedExportNewSections:
    """Test new data sections in export JSON."""

    @pytest.mark.asyncio
    async def test_export_includes_compliance_attempts(self):
        """Export should include compliance detection attempts."""
        repo = _make_mock_repository()
        attempt = MagicMock()
        attempt.item_label = "Greeting"
        attempt.ai_detected = True
        attempt.ai_confidence = 0.95
        attempt.agent_override = False
        attempt.final_status = True
        attempt.detected_at = datetime(2026, 2, 22, 10, 1, 0, tzinfo=timezone.utc)
        repo.get_compliance_attempts.return_value = [attempt]

        service = DataExportService(repo)
        path = await service.export_conversation_data("test-conv-id")

        with open(path) as f:
            data = json.load(f)
        attempts = data["compliance_detection_attempts"]
        assert len(attempts) == 1
        assert attempts[0]["item_label"] == "Greeting"
        assert attempts[0]["ai_detected"] is True
        assert attempts[0]["ai_confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_export_includes_content_edits(self):
        """Export should include content edits."""
        repo = _make_mock_repository()
        edit = MagicMock()
        edit.field_name = "wrap_up_notes"
        edit.original_value = "AI text"
        edit.edited_value = "Agent text"
        edit.edit_type = "modification"
        edit.edited_at = datetime(2026, 2, 22, 10, 2, 0, tzinfo=timezone.utc)
        edit.agent_id = "agent-1"
        repo.get_content_edits.return_value = [edit]

        service = DataExportService(repo)
        path = await service.export_conversation_data("test-conv-id")

        with open(path) as f:
            data = json.load(f)
        edits = data["content_edits"]
        assert len(edits) == 1
        assert edits[0]["field_name"] == "wrap_up_notes"
        assert edits[0]["edit_type"] == "modification"

    @pytest.mark.asyncio
    async def test_export_includes_listening_sessions(self):
        """Export should include listening mode sessions with duration."""
        repo = _make_mock_repository()
        session = MagicMock()
        session.started_at = datetime(2026, 2, 22, 10, 0, 0, tzinfo=timezone.utc)
        session.ended_at = datetime(2026, 2, 22, 10, 3, 0, tzinfo=timezone.utc)
        session.auto_queries_count = 5
        session.opportunities_detected = 3
        session.products_suggested = '["gloves", "safety goggles"]'
        session.orders_tracked = None
        repo.get_listening_mode_sessions.return_value = [session]

        service = DataExportService(repo)
        path = await service.export_conversation_data("test-conv-id")

        with open(path) as f:
            data = json.load(f)
        sessions = data["listening_mode_sessions"]
        assert len(sessions) == 1
        assert sessions[0]["auto_queries_count"] == 5
        assert sessions[0]["duration_secs"] == 180.0
        assert sessions[0]["products_suggested"] == ["gloves", "safety goggles"]

    @pytest.mark.asyncio
    async def test_export_includes_crm_extractions(self):
        """Export should include CRM field extractions with source."""
        repo = _make_mock_repository()
        crm = MagicMock()
        crm.field_name = "case_subject"
        crm.extracted_value = "Order inquiry"
        crm.source = "AI"
        crm.confidence = 0.88
        crm.extracted_at = datetime(2026, 2, 22, 10, 1, 0, tzinfo=timezone.utc)
        repo.get_crm_field_extractions.return_value = [crm]

        service = DataExportService(repo)
        path = await service.export_conversation_data("test-conv-id")

        with open(path) as f:
            data = json.load(f)
        extractions = data["crm_extractions"]
        assert len(extractions) == 1
        assert extractions[0]["source"] == "AI"
        assert extractions[0]["confidence"] == 0.88

    @pytest.mark.asyncio
    async def test_empty_sections_export_as_empty_lists(self):
        """All new sections should be empty lists when no data exists."""
        repo = _make_mock_repository()
        service = DataExportService(repo)
        path = await service.export_conversation_data("test-conv-id")

        with open(path) as f:
            data = json.load(f)
        assert data["compliance_detection_attempts"] == []
        assert data["content_edits"] == []
        assert data["disposition_suggestions"] == []
        assert data["listening_mode_sessions"] == []
        assert data["crm_extractions"] == []


class TestModelBreakdownMetrics:
    """Test AI cost breakdown by model."""

    @pytest.mark.asyncio
    async def test_model_breakdown_aggregation(self):
        """Metrics should include per-model cost breakdown."""
        repo = _make_mock_repository()
        repo.get_ai_interactions.return_value = [
            _make_ai_interaction(model_name="gpt-3.5-turbo", tokens_used=100, cost_usd=0.01, latency_ms=200),
            _make_ai_interaction(model_name="gpt-3.5-turbo", tokens_used=150, cost_usd=0.015, latency_ms=300),
            _make_ai_interaction(model_name="gpt-4o", tokens_used=200, cost_usd=0.10, latency_ms=1500),
        ]

        service = DataExportService(repo)
        path = await service.export_conversation_data("test-conv-id")

        with open(path) as f:
            data = json.load(f)
        by_model = data["metrics"]["ai_costs_by_model"]

        assert "gpt-3.5-turbo" in by_model
        assert by_model["gpt-3.5-turbo"]["call_count"] == 2
        assert by_model["gpt-3.5-turbo"]["total_tokens"] == 250
        assert by_model["gpt-3.5-turbo"]["avg_latency_ms"] == 250

        assert "gpt-4o" in by_model
        assert by_model["gpt-4o"]["call_count"] == 1
        assert by_model["gpt-4o"]["total_cost_usd"] == 0.10

    @pytest.mark.asyncio
    async def test_type_breakdown_aggregation(self):
        """Metrics should include per-type cost breakdown."""
        repo = _make_mock_repository()
        repo.get_ai_interactions.return_value = [
            _make_ai_interaction(interaction_type="summary", cost_usd=0.01),
            _make_ai_interaction(interaction_type="summary", cost_usd=0.02),
            _make_ai_interaction(interaction_type="opportunity_detection", cost_usd=0.005),
        ]

        service = DataExportService(repo)
        path = await service.export_conversation_data("test-conv-id")

        with open(path) as f:
            data = json.load(f)
        by_type = data["metrics"]["ai_costs_by_type"]

        assert by_type["summary"]["call_count"] == 2
        assert by_type["summary"]["total_cost_usd"] == pytest.approx(0.03)
        assert by_type["opportunity_detection"]["call_count"] == 1

    @pytest.mark.asyncio
    async def test_no_model_breakdown_when_no_ai_interactions(self):
        """Model breakdown should not exist when there are no AI interactions."""
        repo = _make_mock_repository()
        service = DataExportService(repo)
        path = await service.export_conversation_data("test-conv-id")

        with open(path) as f:
            data = json.load(f)
        assert "ai_costs_by_model" not in data["metrics"]
        assert "ai_costs_by_type" not in data["metrics"]
