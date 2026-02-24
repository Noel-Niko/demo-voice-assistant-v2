"""Unit tests for DashboardService.

Following TDD: Tests written FIRST, then implementation.

Tests file discovery, JSON parsing, metric extraction, aggregation,
deduplication, and edge cases.
"""
import json
import os
import pytest

from app.dashboard.service import DashboardService


def _write_conversation_file(tmp_path, filename, data):
    """Helper to write a test conversation JSON file."""
    f = tmp_path / filename
    f.write_text(json.dumps(data))
    return str(f)


def _make_conversation_data(conv_id="conv-001", **overrides):
    """Helper to create a minimal valid conversation export."""
    base = {
        "conversation": {
            "id": conv_id,
            "agent_id": "agent-1",
            "customer_id": "cust-1",
            "status": "completed",
            "started_at": "2026-02-22T10:00:00",
            "ended_at": "2026-02-22T10:05:00",
            "disposition_code": "RESOLVED",
            "acw_duration_secs": 30,
        },
        "transcript": {
            "line_count": 50,
            "word_count": 500,
            "duration_secs": 300,
        },
        "summaries": [{"version": 1}, {"version": 2}],
        "metrics": {
            "mcp_queries": {
                "manual_count": 3,
                "auto_count": 2,
                "rated_up": 1,
                "rated_down": 0,
                "unrated": 4,
            },
            "ai_costs": {
                "total_cost_usd": 0.05,
                "total_tokens": 1500,
                "call_count": 5,
            },
            "edits": {
                "total_edits": 1,
            },
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            base[key].update(value)
        else:
            base[key] = value
    return base


class TestFileDiscovery:
    """Test file discovery functionality."""

    def test_empty_directory(self, tmp_path):
        """Empty directory returns empty list."""
        service = DashboardService(data_dir=str(tmp_path))
        assert service.discover_files() == []

    def test_finds_matching_files(self, tmp_path):
        """Matching conversation_data_*.json files are discovered."""
        (tmp_path / "conversation_data_abc_20260222.json").write_text("{}")
        (tmp_path / "conversation_data_def_20260222.json").write_text("{}")
        (tmp_path / "other_file.json").write_text("{}")

        service = DashboardService(data_dir=str(tmp_path))
        files = service.discover_files()

        assert len(files) == 2
        assert all("conversation_data_" in f for f in files)

    def test_sorted_by_mtime_desc(self, tmp_path):
        """Files are sorted newest first."""
        f1 = tmp_path / "conversation_data_old.json"
        f1.write_text("{}")
        os.utime(f1, (1000000, 1000000))

        f2 = tmp_path / "conversation_data_new.json"
        f2.write_text("{}")

        service = DashboardService(data_dir=str(tmp_path))
        files = service.discover_files()

        assert "new" in os.path.basename(files[0])


class TestLoadConversation:
    """Test JSON loading."""

    def test_valid_json(self, tmp_path):
        """Valid JSON file loads correctly."""
        data = {"conversation": {"id": "test-123"}}
        f = tmp_path / "conversation_data_test.json"
        f.write_text(json.dumps(data))

        service = DashboardService(data_dir=str(tmp_path))
        result = service.load_conversation(str(f))

        assert result is not None
        assert result["conversation"]["id"] == "test-123"

    def test_invalid_json_returns_none(self, tmp_path):
        """Invalid JSON returns None gracefully."""
        f = tmp_path / "conversation_data_bad.json"
        f.write_text("not json {{{")

        service = DashboardService(data_dir=str(tmp_path))
        assert service.load_conversation(str(f)) is None

    def test_missing_file_returns_none(self):
        """Missing file returns None gracefully."""
        service = DashboardService(data_dir="/tmp")
        assert service.load_conversation("/tmp/nonexistent_dashboard_file.json") is None


class TestMetricsExtraction:
    """Test per-conversation metrics extraction."""

    def test_basic_metrics(self, tmp_path):
        """Extract basic conversation metrics."""
        data = _make_conversation_data()
        service = DashboardService(data_dir=str(tmp_path))
        result = service._extract_conversation_metrics(data, "/tmp/test.json")

        assert result.conversation_id == "conv-001"
        assert result.status == "completed"
        assert result.duration_secs == 300
        assert result.summary_count == 2
        assert result.total_ai_cost_usd == 0.05
        assert result.manual_query_count == 3
        assert result.auto_query_count == 2

    def test_fcr_true_for_resolved(self, tmp_path):
        """FCR is True for resolution-eligible dispositions."""
        data = _make_conversation_data(
            conversation={"id": "c1", "disposition_code": "RESOLVED"}
        )
        service = DashboardService(data_dir=str(tmp_path))
        result = service._extract_conversation_metrics(data, "/tmp/t.json")
        assert result.fcr is True

    def test_fcr_false_for_escalated(self, tmp_path):
        """FCR is False for non-resolution dispositions."""
        data = _make_conversation_data(
            conversation={"id": "c2", "disposition_code": "ESCALATED_SUPERVISOR"}
        )
        service = DashboardService(data_dir=str(tmp_path))
        result = service._extract_conversation_metrics(data, "/tmp/t.json")
        assert result.fcr is False

    def test_fcr_none_when_no_disposition(self, tmp_path):
        """FCR is None when disposition not set."""
        data = _make_conversation_data(
            conversation={"id": "c3", "disposition_code": None}
        )
        service = DashboardService(data_dir=str(tmp_path))
        result = service._extract_conversation_metrics(data, "/tmp/t.json")
        assert result.fcr is None


class TestAggregation:
    """Test aggregate KPI computation."""

    def test_single_conversation_kpis(self, tmp_path):
        """KPIs computed from a single conversation."""
        data = _make_conversation_data()
        _write_conversation_file(tmp_path, "conversation_data_001.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.kpis.total_conversations == 1
        assert result.kpis.fcr_rate == 100.0
        assert result.kpis.total_ai_cost_usd == 0.05
        assert result.kpis.avg_duration_secs == 300.0

    def test_multi_conversation_averages(self, tmp_path):
        """KPIs average across multiple conversations."""
        data1 = _make_conversation_data(
            conv_id="conv-a",
            transcript={"duration_secs": 200, "line_count": 30, "word_count": 300},
            metrics={"ai_costs": {"total_cost_usd": 0.04, "total_tokens": 1000, "call_count": 4},
                     "mcp_queries": {}, "edits": {}},
        )
        data2 = _make_conversation_data(
            conv_id="conv-b",
            transcript={"duration_secs": 400, "line_count": 70, "word_count": 700},
            metrics={"ai_costs": {"total_cost_usd": 0.06, "total_tokens": 2000, "call_count": 6},
                     "mcp_queries": {}, "edits": {}},
        )
        _write_conversation_file(tmp_path, "conversation_data_a.json", data1)
        _write_conversation_file(tmp_path, "conversation_data_b.json", data2)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.kpis.total_conversations == 2
        assert result.kpis.avg_duration_secs == 300.0
        assert result.kpis.total_ai_cost_usd == pytest.approx(0.10)

    def test_deduplication_keeps_latest(self, tmp_path):
        """Duplicate conversation IDs are deduplicated (latest file wins)."""
        data_old = _make_conversation_data(
            conv_id="conv-dup",
            conversation={"id": "conv-dup", "status": "active"},
        )
        data_new = _make_conversation_data(
            conv_id="conv-dup",
            conversation={"id": "conv-dup", "status": "completed"},
        )

        f1 = tmp_path / "conversation_data_dup_old.json"
        f1.write_text(json.dumps(data_old))
        os.utime(f1, (1000000, 1000000))

        f2 = tmp_path / "conversation_data_dup_new.json"
        f2.write_text(json.dumps(data_new))

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.kpis.total_conversations == 1
        assert result.conversations[0].status == "completed"

    def test_empty_directory_returns_zeros(self, tmp_path):
        """Empty directory produces zero KPIs."""
        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.kpis.total_conversations == 0
        assert result.kpis.avg_duration_secs == 0.0
        assert result.kpis.total_ai_cost_usd == 0.0
        assert result.kpis.fcr_rate == 0.0

    def test_skips_malformed_files(self, tmp_path):
        """Malformed JSON files are skipped without crashing."""
        (tmp_path / "conversation_data_bad.json").write_text("not json")
        data = _make_conversation_data(conv_id="conv-good")
        _write_conversation_file(tmp_path, "conversation_data_good.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.kpis.total_conversations == 1


class TestModelBreakdown:
    """Test model cost aggregation across conversations."""

    def test_multi_model_aggregation(self, tmp_path):
        """Model costs aggregated across conversations."""
        data = _make_conversation_data(
            metrics={
                "mcp_queries": {},
                "ai_costs": {"total_cost_usd": 0.11, "total_tokens": 7000, "call_count": 12},
                "edits": {},
                "ai_costs_by_model": {
                    "gpt-3.5-turbo": {
                        "call_count": 10,
                        "total_tokens": 5000,
                        "total_cost_usd": 0.01,
                        "avg_latency_ms": 200,
                    },
                    "gpt-4o": {
                        "call_count": 2,
                        "total_tokens": 2000,
                        "total_cost_usd": 0.10,
                        "avg_latency_ms": 1500,
                    },
                },
            }
        )
        _write_conversation_file(tmp_path, "conversation_data_m1.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert len(result.model_breakdown) == 2
        # Sorted by cost desc
        assert result.model_breakdown[0].model_name == "gpt-4o"
        assert result.model_breakdown[0].total_cost_usd == 0.10
        assert result.model_breakdown[1].model_name == "gpt-3.5-turbo"

    def test_no_model_data(self, tmp_path):
        """No model breakdown when data is absent."""
        data = _make_conversation_data()
        _write_conversation_file(tmp_path, "conversation_data_001.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()
        assert result.model_breakdown == []


class TestComplianceAggregation:
    """Test compliance detection metrics."""

    def test_compliance_accuracy(self, tmp_path):
        """Compliance accuracy and override rate computed correctly."""
        data = _make_conversation_data()
        data["compliance_detection_attempts"] = [
            {"ai_detected": True, "ai_confidence": 0.95, "agent_override": False, "final_status": True},
            {"ai_detected": True, "ai_confidence": 0.80, "agent_override": True, "final_status": False},
            {"ai_detected": False, "ai_confidence": 0.30, "agent_override": False, "final_status": False},
        ]
        _write_conversation_file(tmp_path, "conversation_data_c1.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.compliance.total_attempts == 3
        assert result.compliance.agent_overrides == 1
        assert result.compliance.ai_correct == 2
        assert result.compliance.override_rate == pytest.approx(1 / 3, rel=0.01)

    def test_no_compliance_data(self, tmp_path):
        """Zero compliance when no attempts exist."""
        data = _make_conversation_data()
        _write_conversation_file(tmp_path, "conversation_data_001.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()
        assert result.compliance.total_attempts == 0


class TestACWPercentageCalculation:
    """Test ACW % calculation fix (Item 1)."""

    def test_acw_pct_uses_call_duration_not_transcript_duration(self, tmp_path):
        """ACW % should use call duration (ended_at - started_at), not transcript duration.

        30s ACW on 300s call (10:00→10:05) with 0.07s transcript duration
        should be 10.0%, not 42857%.
        """
        data = _make_conversation_data(
            conversation={
                "id": "conv-001",
                "started_at": "2026-02-22T10:00:00",
                "ended_at": "2026-02-22T10:05:00",  # 5 minutes = 300s
                "acw_duration_secs": 30,
            },
            transcript={"duration_secs": 0.07, "line_count": 10, "word_count": 50},  # Tiny transcript duration
        )
        _write_conversation_file(tmp_path, "conversation_data_001.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        # 30s ACW / 300s call = 10.0%
        assert result.kpis.avg_acw_pct == pytest.approx(10.0, rel=0.01)

    def test_acw_pct_capped_at_100(self, tmp_path):
        """ACW % should be capped at 100% even if ACW exceeds call duration."""
        data = _make_conversation_data(
            conversation={
                "id": "conv-002",
                "started_at": "2026-02-22T10:00:00",
                "ended_at": "2026-02-22T10:01:00",  # 60s call
                "acw_duration_secs": 120,  # 120s ACW (exceeds call duration)
            },
        )
        _write_conversation_file(tmp_path, "conversation_data_002.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        # Should be capped at 100%
        assert result.kpis.avg_acw_pct <= 100.0

    def test_acw_pct_skips_when_no_timestamps(self, tmp_path):
        """ACW % should be 0.0% when started_at/ended_at are missing."""
        data = _make_conversation_data(
            conversation={
                "id": "conv-003",
                "started_at": None,
                "ended_at": None,
                "acw_duration_secs": 30,
            },
        )
        _write_conversation_file(tmp_path, "conversation_data_003.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.kpis.avg_acw_pct == 0.0

    def test_acw_pct_normal_case(self, tmp_path):
        """ACW % normal case with default data (300s call, 30s ACW)."""
        data = _make_conversation_data()  # Default: 10:00→10:05 (300s), 30s ACW
        _write_conversation_file(tmp_path, "conversation_data_004.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        # 30s / 300s = 10.0%
        assert result.kpis.avg_acw_pct == pytest.approx(10.0, rel=0.01)


class TestFeedbackMetrics:
    """Test feedback (thumbs up/down) aggregation (Item 2)."""

    def test_feedback_aggregation(self, tmp_path):
        """Feedback aggregated across conversations with correct approval rate."""
        data1 = _make_conversation_data(
            conv_id="conv-a",
            metrics={
                "mcp_queries": {"rated_up": 5, "rated_down": 3},
                "ai_costs": {},
                "edits": {},
            },
        )
        data2 = _make_conversation_data(
            conv_id="conv-b",
            metrics={
                "mcp_queries": {"rated_up": 0, "rated_down": 0},
                "ai_costs": {},
                "edits": {},
            },
        )
        _write_conversation_file(tmp_path, "conversation_data_a.json", data1)
        _write_conversation_file(tmp_path, "conversation_data_b.json", data2)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.feedback_metrics.total_rated_up == 5
        assert result.feedback_metrics.total_rated_down == 3
        assert result.feedback_metrics.total_rated == 8
        # 5 / 8 * 100 = 62.5%
        assert result.feedback_metrics.approval_rate == pytest.approx(62.5, rel=0.01)

    def test_feedback_no_ratings(self, tmp_path):
        """No ratings results in 0.0% approval rate."""
        data = _make_conversation_data(
            metrics={
                "mcp_queries": {"rated_up": 0, "rated_down": 0},
                "ai_costs": {},
                "edits": {},
            },
        )
        _write_conversation_file(tmp_path, "conversation_data_001.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.feedback_metrics.total_rated_up == 0
        assert result.feedback_metrics.total_rated_down == 0
        assert result.feedback_metrics.total_rated == 0
        assert result.feedback_metrics.approval_rate == 0.0

    def test_feedback_only_positive(self, tmp_path):
        """Only positive ratings results in 100% approval rate."""
        data = _make_conversation_data(
            metrics={
                "mcp_queries": {"rated_up": 10, "rated_down": 0},
                "ai_costs": {},
                "edits": {},
            },
        )
        _write_conversation_file(tmp_path, "conversation_data_001.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.feedback_metrics.total_rated_up == 10
        assert result.feedback_metrics.total_rated_down == 0
        assert result.feedback_metrics.total_rated == 10
        assert result.feedback_metrics.approval_rate == 100.0


class TestLatencyAggregation:
    """Test latency aggregation per model (Item 3)."""

    def test_latency_aggregation_across_conversations(self, tmp_path):
        """Latency weighted average across conversations for same model.

        Conversation 1: model A, 2 calls, 100ms avg
        Conversation 2: model A, 3 calls, 200ms avg
        Expected weighted avg: (100*2 + 200*3) / (2+3) = 800/5 = 160ms
        """
        data1 = _make_conversation_data(
            conv_id="conv-a",
            metrics={
                "mcp_queries": {},
                "ai_costs": {"total_cost_usd": 0.01, "total_tokens": 1000, "call_count": 2},
                "edits": {},
                "ai_costs_by_model": {
                    "gpt-3.5-turbo": {
                        "call_count": 2,
                        "total_tokens": 1000,
                        "total_cost_usd": 0.01,
                        "avg_latency_ms": 100,
                    },
                },
            },
        )
        data1["ai_calls"] = [
            {"model_name": "gpt-3.5-turbo", "latency_ms": 100},
            {"model_name": "gpt-3.5-turbo", "latency_ms": 100},
        ]
        data2 = _make_conversation_data(
            conv_id="conv-b",
            metrics={
                "mcp_queries": {},
                "ai_costs": {"total_cost_usd": 0.02, "total_tokens": 2000, "call_count": 3},
                "edits": {},
                "ai_costs_by_model": {
                    "gpt-3.5-turbo": {
                        "call_count": 3,
                        "total_tokens": 2000,
                        "total_cost_usd": 0.02,
                        "avg_latency_ms": 200,
                    },
                },
            },
        )
        data2["ai_calls"] = [
            {"model_name": "gpt-3.5-turbo", "latency_ms": 200},
            {"model_name": "gpt-3.5-turbo", "latency_ms": 200},
            {"model_name": "gpt-3.5-turbo", "latency_ms": 200},
        ]
        _write_conversation_file(tmp_path, "conversation_data_a.json", data1)
        _write_conversation_file(tmp_path, "conversation_data_b.json", data2)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert len(result.model_breakdown) == 1
        assert result.model_breakdown[0].model_name == "gpt-3.5-turbo"
        # Weighted avg: (100*2 + 200*3) / 5 = 160
        assert result.model_breakdown[0].avg_latency_ms == 160


class TestACWFormMetrics:
    """Test end-of-call form metrics (Item 4)."""

    def test_disposition_distribution(self, tmp_path):
        """Disposition codes aggregated correctly."""
        data1 = _make_conversation_data(
            conv_id="conv-a",
            conversation={"id": "conv-a", "disposition_code": "RESOLVED"},
        )
        data2 = _make_conversation_data(
            conv_id="conv-b",
            conversation={"id": "conv-b", "disposition_code": "RESOLVED"},
        )
        data3 = _make_conversation_data(
            conv_id="conv-c",
            conversation={"id": "conv-c", "disposition_code": "ESCALATED_SUPERVISOR"},
        )
        _write_conversation_file(tmp_path, "conversation_data_a.json", data1)
        _write_conversation_file(tmp_path, "conversation_data_b.json", data2)
        _write_conversation_file(tmp_path, "conversation_data_c.json", data3)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.acw_metrics.disposition_distribution == {
            "RESOLVED": 2,
            "ESCALATED_SUPERVISOR": 1,
        }
        assert result.acw_metrics.total_with_disposition == 3

    def test_wrap_up_notes_completion_rate(self, tmp_path):
        """Wrap-up notes completion rate computed correctly."""
        data1 = _make_conversation_data(
            conv_id="conv-a",
            conversation={"id": "conv-a", "wrap_up_notes": "Customer issue resolved"},
        )
        data2 = _make_conversation_data(
            conv_id="conv-b",
            conversation={"id": "conv-b", "wrap_up_notes": None},
        )
        data3 = _make_conversation_data(
            conv_id="conv-c",
            conversation={"id": "conv-c", "wrap_up_notes": ""},
        )
        _write_conversation_file(tmp_path, "conversation_data_a.json", data1)
        _write_conversation_file(tmp_path, "conversation_data_b.json", data2)
        _write_conversation_file(tmp_path, "conversation_data_c.json", data3)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        # Only 1 of 3 has non-empty notes
        assert result.acw_metrics.notes_completed == 1
        assert result.acw_metrics.notes_completion_rate == pytest.approx(33.3, rel=0.1)

    def test_agent_feedback_distribution(self, tmp_path):
        """Agent feedback (up/down/none) counted correctly."""
        data1 = _make_conversation_data(
            conv_id="conv-a",
            conversation={"id": "conv-a", "agent_feedback": "up"},
        )
        data2 = _make_conversation_data(
            conv_id="conv-b",
            conversation={"id": "conv-b", "agent_feedback": "down"},
        )
        data3 = _make_conversation_data(
            conv_id="conv-c",
            conversation={"id": "conv-c", "agent_feedback": None},
        )
        _write_conversation_file(tmp_path, "conversation_data_a.json", data1)
        _write_conversation_file(tmp_path, "conversation_data_b.json", data2)
        _write_conversation_file(tmp_path, "conversation_data_c.json", data3)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.acw_metrics.agent_feedback_up == 1
        assert result.acw_metrics.agent_feedback_down == 1
        assert result.acw_metrics.agent_feedback_none == 1

    def test_crm_auto_fill_rate(self, tmp_path):
        """CRM auto-fill rate based on extraction source."""
        data1 = _make_conversation_data(conv_id="conv-a")
        data1["crm_extractions"] = [
            {"field_name": "customer_name", "source": "AI"},
            {"field_name": "order_id", "source": "AI"},
        ]
        data2 = _make_conversation_data(conv_id="conv-b")
        data2["crm_extractions"] = [
            {"field_name": "issue", "source": "Transcript"},
        ]
        _write_conversation_file(tmp_path, "conversation_data_a.json", data1)
        _write_conversation_file(tmp_path, "conversation_data_b.json", data2)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.acw_metrics.crm_total_extractions == 3
        assert result.acw_metrics.crm_ai_extractions == 2
        assert result.acw_metrics.crm_transcript_extractions == 1
        # 2 AI / 3 total = 66.7%
        assert result.acw_metrics.crm_auto_fill_rate == pytest.approx(66.7, rel=0.1)

    def test_empty_acw_metrics(self, tmp_path):
        """Empty data results in zero ACW metrics."""
        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.acw_metrics.total_with_disposition == 0
        assert result.acw_metrics.notes_completed == 0
        assert result.acw_metrics.notes_completion_rate == 0.0
        assert result.acw_metrics.agent_feedback_up == 0
        assert result.acw_metrics.agent_feedback_down == 0
        assert result.acw_metrics.agent_feedback_none == 0
        assert result.acw_metrics.crm_total_extractions == 0
        assert result.acw_metrics.crm_auto_fill_rate == 0.0


class TestAISuggestionMetrics:
    """Test AI suggestion usage rate (Item 5)."""

    def test_suggestion_rate_basic(self, tmp_path):
        """AI suggestion interactions counted correctly by type.

        FIX: Ratings are now stored in user_rating field, not as separate interaction type.
        """
        data = _make_conversation_data()
        data["agent_interactions"] = [
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:00:00", "user_rating": "up"},
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:01:00", "user_rating": None},
            {"interaction_type": "mcp_query_auto", "timestamp": "2026-02-22T10:02:00", "user_rating": None},
            {"interaction_type": "mode_switch", "timestamp": "2026-02-22T10:04:00", "user_rating": None},
            {"interaction_type": "disposition_selected", "timestamp": "2026-02-22T10:05:00", "user_rating": None},
            {"interaction_type": "compliance_override", "timestamp": "2026-02-22T10:06:00", "user_rating": None},
        ]
        _write_conversation_file(tmp_path, "conversation_data_001.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.ai_suggestion_metrics.total_interactions == 6
        assert result.ai_suggestion_metrics.total_manual_queries == 2
        assert result.ai_suggestion_metrics.total_auto_queries == 1
        assert result.ai_suggestion_metrics.total_suggestions_rated == 1
        assert result.ai_suggestion_metrics.total_mode_switches == 1
        assert result.ai_suggestion_metrics.interaction_type_breakdown == {
            "manual_query": 2,
            "mcp_query_auto": 1,
            "mode_switch": 1,
            "disposition_selected": 1,
            "compliance_override": 1,
        }

    def test_suggestion_rate_per_conversation(self, tmp_path):
        """Average queries per conversation computed correctly."""
        data1 = _make_conversation_data(conv_id="conv-a")
        data1["agent_interactions"] = [
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:00:00"},
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:01:00"},
            {"interaction_type": "mcp_query_auto", "timestamp": "2026-02-22T10:02:00"},
        ]
        data2 = _make_conversation_data(conv_id="conv-b")
        data2["agent_interactions"] = [
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:00:00"},
            {"interaction_type": "mcp_query_auto", "timestamp": "2026-02-22T10:01:00"},
            {"interaction_type": "mcp_query_auto", "timestamp": "2026-02-22T10:02:00"},
        ]
        _write_conversation_file(tmp_path, "conversation_data_a.json", data1)
        _write_conversation_file(tmp_path, "conversation_data_b.json", data2)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        # Total queries: 3 + 3 = 6, conversations: 2 → avg 3.0
        assert result.ai_suggestion_metrics.avg_queries_per_conversation == pytest.approx(3.0)
        assert result.ai_suggestion_metrics.conversations_with_queries == 2
        assert result.ai_suggestion_metrics.query_usage_rate == 100.0  # 2/2

    def test_no_interactions(self, tmp_path):
        """No interactions results in zero metrics."""
        data = _make_conversation_data()
        _write_conversation_file(tmp_path, "conversation_data_001.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.ai_suggestion_metrics.total_interactions == 0
        assert result.ai_suggestion_metrics.total_manual_queries == 0
        assert result.ai_suggestion_metrics.total_auto_queries == 0
        assert result.ai_suggestion_metrics.avg_queries_per_conversation == 0.0
        assert result.ai_suggestion_metrics.query_usage_rate == 0.0


class TestManualSearchMetrics:
    """Test manual search frequency when listening mode off (Item 6)."""

    def test_manual_queries_outside_listening(self, tmp_path):
        """Manual queries classified correctly as inside/outside listening sessions."""
        data = _make_conversation_data()
        # Listening session: 10:01 - 10:03
        data["listening_mode_sessions"] = [
            {"started_at": "2026-02-22T10:01:00", "ended_at": "2026-02-22T10:03:00"},
        ]
        # 3 manual queries: 1 inside, 2 outside
        data["agent_interactions"] = [
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:00:00"},  # Before
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:02:00"},  # Inside
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:04:00"},  # After
        ]
        _write_conversation_file(tmp_path, "conversation_data_001.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.manual_search_metrics.total_manual_queries == 3
        assert result.manual_search_metrics.total_manual_inside_listening == 1
        assert result.manual_search_metrics.total_manual_outside_listening == 2
        # 2 / 3 * 100 = 66.7%
        assert result.manual_search_metrics.outside_query_rate == pytest.approx(66.7, rel=0.1)

    def test_no_listening_sessions_all_outside(self, tmp_path):
        """All manual queries are outside when no listening sessions exist."""
        data = _make_conversation_data()
        data["agent_interactions"] = [
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:00:00"},
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:01:00"},
        ]
        _write_conversation_file(tmp_path, "conversation_data_001.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.manual_search_metrics.total_manual_queries == 2
        assert result.manual_search_metrics.total_manual_outside_listening == 2
        assert result.manual_search_metrics.total_manual_inside_listening == 0
        assert result.manual_search_metrics.outside_query_rate == 100.0

    def test_all_inside_listening(self, tmp_path):
        """All manual queries inside listening session results in 0 outside."""
        data = _make_conversation_data()
        # Full coverage session
        data["listening_mode_sessions"] = [
            {"started_at": "2026-02-22T10:00:00", "ended_at": "2026-02-22T10:10:00"},
        ]
        data["agent_interactions"] = [
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:02:00"},
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:05:00"},
        ]
        _write_conversation_file(tmp_path, "conversation_data_001.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.manual_search_metrics.total_manual_queries == 2
        assert result.manual_search_metrics.total_manual_inside_listening == 2
        assert result.manual_search_metrics.total_manual_outside_listening == 0
        assert result.manual_search_metrics.outside_query_rate == 0.0

    def test_multiple_listening_sessions(self, tmp_path):
        """Correctly classifies queries with multiple listening sessions."""
        data = _make_conversation_data()
        # Two sessions with gaps
        data["listening_mode_sessions"] = [
            {"started_at": "2026-02-22T10:01:00", "ended_at": "2026-02-22T10:02:00"},
            {"started_at": "2026-02-22T10:04:00", "ended_at": "2026-02-22T10:05:00"},
        ]
        data["agent_interactions"] = [
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:00:00"},  # Before first
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:01:30"},  # In first
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:03:00"},  # Between sessions
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:04:30"},  # In second
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:06:00"},  # After second
        ]
        _write_conversation_file(tmp_path, "conversation_data_001.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.manual_search_metrics.total_manual_queries == 5
        assert result.manual_search_metrics.total_manual_inside_listening == 2
        assert result.manual_search_metrics.total_manual_outside_listening == 3
        assert result.manual_search_metrics.outside_query_rate == pytest.approx(60.0, rel=0.1)

    def test_empty_data(self, tmp_path):
        """Empty data results in zero metrics."""
        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.manual_search_metrics.total_manual_queries == 0
        assert result.manual_search_metrics.total_manual_outside_listening == 0
        assert result.manual_search_metrics.total_manual_inside_listening == 0
        assert result.manual_search_metrics.outside_query_rate == 0.0
        assert result.manual_search_metrics.avg_outside_per_conversation == 0.0
        assert result.manual_search_metrics.conversations_with_outside_queries == 0

    def test_avg_and_rate(self, tmp_path):
        """Average outside queries per conversation computed correctly."""
        data1 = _make_conversation_data(conv_id="conv-a")
        # No listening sessions → all queries are outside
        data1["agent_interactions"] = [
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:00:00"},
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:01:00"},
        ]
        data2 = _make_conversation_data(conv_id="conv-b")
        data2["agent_interactions"] = [
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:00:00"},
            {"interaction_type": "manual_query", "timestamp": "2026-02-22T10:01:00"},
        ]
        _write_conversation_file(tmp_path, "conversation_data_a.json", data1)
        _write_conversation_file(tmp_path, "conversation_data_b.json", data2)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        # Total: 4 outside, 2 conversations → avg 2.0
        assert result.manual_search_metrics.avg_outside_per_conversation == pytest.approx(2.0)
        assert result.manual_search_metrics.conversations_with_outside_queries == 2


class TestListeningModeAggregation:
    """Test listening mode metrics."""

    def test_listening_mode_metrics(self, tmp_path):
        """Listening mode sessions aggregated correctly."""
        data = _make_conversation_data()
        data["listening_mode_sessions"] = [
            {"started_at": "2026-02-22T10:00:00", "ended_at": "2026-02-22T10:03:00",
             "auto_queries_count": 5, "opportunities_detected": 3, "duration_secs": 180},
            {"started_at": "2026-02-22T10:04:00", "ended_at": "2026-02-22T10:05:00",
             "auto_queries_count": 2, "opportunities_detected": 1, "duration_secs": 60},
        ]
        _write_conversation_file(tmp_path, "conversation_data_l1.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert result.listening_mode.total_sessions == 2
        assert result.listening_mode.total_duration_secs == 240.0
        assert result.listening_mode.total_auto_queries == 7
        assert result.listening_mode.avg_queries_per_session == 3.5
        assert result.listening_mode.total_opportunities == 4


class TestLatencyPercentiles:
    """Test percentile-based latency calculations (p50, p99)."""

    def test_latency_p50_odd_count(self, tmp_path):
        """P50 with odd count returns middle value."""
        data = _make_conversation_data()
        data["ai_calls"] = [
            {"model_name": "gpt-3.5-turbo", "latency_ms": 100},
            {"model_name": "gpt-3.5-turbo", "latency_ms": 200},
            {"model_name": "gpt-3.5-turbo", "latency_ms": 300},
            {"model_name": "gpt-3.5-turbo", "latency_ms": 400},
            {"model_name": "gpt-3.5-turbo", "latency_ms": 500},
        ]
        data["metrics"]["ai_costs_by_model"] = {
            "gpt-3.5-turbo": {"call_count": 5, "total_tokens": 1000, "total_cost_usd": 0.01}
        }
        _write_conversation_file(tmp_path, "conversation_data_p50odd.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert len(result.model_breakdown) == 1
        assert result.model_breakdown[0].p50_latency_ms == 300  # Median

    def test_latency_p50_even_count(self, tmp_path):
        """P50 with even count interpolates between middle values."""
        data = _make_conversation_data()
        data["ai_calls"] = [
            {"model_name": "gpt-3.5-turbo", "latency_ms": 100},
            {"model_name": "gpt-3.5-turbo", "latency_ms": 200},
            {"model_name": "gpt-3.5-turbo", "latency_ms": 300},
            {"model_name": "gpt-3.5-turbo", "latency_ms": 400},
        ]
        data["metrics"]["ai_costs_by_model"] = {
            "gpt-3.5-turbo": {"call_count": 4, "total_tokens": 1000, "total_cost_usd": 0.01}
        }
        _write_conversation_file(tmp_path, "conversation_data_p50even.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert len(result.model_breakdown) == 1
        # (200 + 300) / 2 = 250
        assert result.model_breakdown[0].p50_latency_ms == 250

    def test_latency_p99_calculation(self, tmp_path):
        """P99 returns 99th percentile value."""
        data = _make_conversation_data()
        # Create 100 latency values: 0-99ms
        data["ai_calls"] = [
            {"model_name": "gpt-3.5-turbo", "latency_ms": i} for i in range(100)
        ]
        data["metrics"]["ai_costs_by_model"] = {
            "gpt-3.5-turbo": {"call_count": 100, "total_tokens": 10000, "total_cost_usd": 0.10}
        }
        _write_conversation_file(tmp_path, "conversation_data_p99.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert len(result.model_breakdown) == 1
        # p99 of [0..99] at position 99/100*(99) = 98.01 → interpolate: 98*0.99 + 99*0.01 = 98.01 → rounds to 98
        assert result.model_breakdown[0].p99_latency_ms == 98

    def test_latency_single_value(self, tmp_path):
        """Single latency value: p50 and p99 both equal that value."""
        data = _make_conversation_data()
        data["ai_calls"] = [
            {"model_name": "gpt-3.5-turbo", "latency_ms": 500},
        ]
        data["metrics"]["ai_costs_by_model"] = {
            "gpt-3.5-turbo": {"call_count": 1, "total_tokens": 100, "total_cost_usd": 0.001}
        }
        _write_conversation_file(tmp_path, "conversation_data_single.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert len(result.model_breakdown) == 1
        assert result.model_breakdown[0].p50_latency_ms == 500
        assert result.model_breakdown[0].p99_latency_ms == 500

    def test_latency_empty_list(self, tmp_path):
        """Empty latency list: p50 and p99 return 0."""
        data = _make_conversation_data()
        data["ai_calls"] = []  # No AI calls
        data["metrics"]["ai_costs_by_model"] = {
            "gpt-3.5-turbo": {"call_count": 0, "total_tokens": 0, "total_cost_usd": 0.0}
        }
        _write_conversation_file(tmp_path, "conversation_data_empty.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert len(result.model_breakdown) == 1
        assert result.model_breakdown[0].p50_latency_ms == 0
        assert result.model_breakdown[0].p99_latency_ms == 0

    def test_latency_two_values(self, tmp_path):
        """Two values: p50 interpolates, p99 is max."""
        data = _make_conversation_data()
        data["ai_calls"] = [
            {"model_name": "gpt-3.5-turbo", "latency_ms": 100},
            {"model_name": "gpt-3.5-turbo", "latency_ms": 200},
        ]
        data["metrics"]["ai_costs_by_model"] = {
            "gpt-3.5-turbo": {"call_count": 2, "total_tokens": 200, "total_cost_usd": 0.002}
        }
        _write_conversation_file(tmp_path, "conversation_data_two.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert len(result.model_breakdown) == 1
        # p50 at position 0.5: interpolate between 100 and 200 = 150
        assert result.model_breakdown[0].p50_latency_ms == 150
        # p99 at position 0.99: almost at 200
        assert result.model_breakdown[0].p99_latency_ms == 199  # 100 + 0.99*(200-100) = 199

    def test_percentiles_from_ai_calls(self, tmp_path):
        """Integration: Extract latencies from multiple conversations."""
        # Conversation 1: latencies [1000, 1100, 1200]
        data1 = _make_conversation_data(conv_id="conv1")
        data1["ai_calls"] = [
            {"model_name": "gpt-3.5-turbo", "latency_ms": 1000},
            {"model_name": "gpt-3.5-turbo", "latency_ms": 1100},
            {"model_name": "gpt-3.5-turbo", "latency_ms": 1200},
        ]
        data1["metrics"]["ai_costs_by_model"] = {
            "gpt-3.5-turbo": {"call_count": 3, "total_tokens": 300, "total_cost_usd": 0.003}
        }

        # Conversation 2: latencies [1300, 1400]
        data2 = _make_conversation_data(conv_id="conv2")
        data2["ai_calls"] = [
            {"model_name": "gpt-3.5-turbo", "latency_ms": 1300},
            {"model_name": "gpt-3.5-turbo", "latency_ms": 1400},
        ]
        data2["metrics"]["ai_costs_by_model"] = {
            "gpt-3.5-turbo": {"call_count": 2, "total_tokens": 200, "total_cost_usd": 0.002}
        }

        _write_conversation_file(tmp_path, "conversation_data_c1.json", data1)
        _write_conversation_file(tmp_path, "conversation_data_c2.json", data2)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert len(result.model_breakdown) == 1
        # Combined: [1000, 1100, 1200, 1300, 1400] → p50 = 1200 (middle)
        assert result.model_breakdown[0].p50_latency_ms == 1200
        # p99 at position 99/100 * 4 = 3.96 → interpolate between 1300 and 1400
        # 1300 + 0.96 * (1400-1300) = 1396
        assert result.model_breakdown[0].p99_latency_ms == 1396

    def test_percentiles_per_model(self, tmp_path):
        """Each model gets separate percentile calculations."""
        data = _make_conversation_data()
        data["ai_calls"] = [
            {"model_name": "gpt-3.5-turbo", "latency_ms": 100},
            {"model_name": "gpt-3.5-turbo", "latency_ms": 200},
            {"model_name": "gpt-3.5-turbo", "latency_ms": 300},
            {"model_name": "gpt-4", "latency_ms": 1000},
            {"model_name": "gpt-4", "latency_ms": 2000},
            {"model_name": "gpt-4", "latency_ms": 3000},
        ]
        data["metrics"]["ai_costs_by_model"] = {
            "gpt-3.5-turbo": {"call_count": 3, "total_tokens": 300, "total_cost_usd": 0.003},
            "gpt-4": {"call_count": 3, "total_tokens": 300, "total_cost_usd": 0.03}
        }
        _write_conversation_file(tmp_path, "conversation_data_multi.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert len(result.model_breakdown) == 2

        # Find each model in results (sorted by cost, so gpt-4 first)
        gpt4 = next(m for m in result.model_breakdown if m.model_name == "gpt-4")
        gpt35 = next(m for m in result.model_breakdown if m.model_name == "gpt-3.5-turbo")

        assert gpt35.p50_latency_ms == 200
        assert gpt4.p50_latency_ms == 2000

    def test_percentiles_ignores_nulls(self, tmp_path):
        """Handle missing latency_ms gracefully."""
        data = _make_conversation_data()
        data["ai_calls"] = [
            {"model_name": "gpt-3.5-turbo", "latency_ms": 100},
            {"model_name": "gpt-3.5-turbo", "latency_ms": None},  # Null value
            {"model_name": "gpt-3.5-turbo", "latency_ms": 300},
            {"model_name": "gpt-3.5-turbo"},  # Missing key
        ]
        data["metrics"]["ai_costs_by_model"] = {
            "gpt-3.5-turbo": {"call_count": 4, "total_tokens": 400, "total_cost_usd": 0.004}
        }
        _write_conversation_file(tmp_path, "conversation_data_nulls.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        assert len(result.model_breakdown) == 1
        # Only [100, 300] are valid → p50 = 200
        assert result.model_breakdown[0].p50_latency_ms == 200
