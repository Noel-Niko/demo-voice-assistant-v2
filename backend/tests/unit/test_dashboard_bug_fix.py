"""Unit tests to diagnose and verify dashboard metrics bug.

BUG: Dashboard shows NO entries for:
- AI feedback (rated_up/rated_down)
- Suggestions rated
- Manual queries
- Manual search activity
- Use of model gpt-5

These tests reproduce the bug with real data structures.
"""
import json
import pytest

from app.dashboard.service import DashboardService


def _write_conversation_file(tmp_path, filename, data):
    """Helper to write a test conversation JSON file."""
    f = tmp_path / filename
    f.write_text(json.dumps(data))
    return str(f)


def _make_realistic_conversation_data(conv_id="conv-001"):
    """Create conversation data matching actual export structure."""
    return {
        "export_metadata": {
            "exported_at": "2026-02-22T15:32:33.836614",
            "conversation_id": conv_id,
            "format_version": "2.0"
        },
        "conversation": {
            "id": conv_id,
            "agent_id": "agent-1",
            "customer_id": "cust-1",
            "status": "active",
            "started_at": "2026-02-22T20:06:41.172412",
            "ended_at": "2026-02-22T20:11:41.172412",  # 5 minutes later
            "disposition_code": "RESOLVED",
            "wrap_up_notes": "Resolved customer issue",
            "agent_feedback": "up",
            "acw_duration_secs": 30
        },
        "transcript": {
            "line_count": 50,
            "word_count": 500,
            "duration_secs": 300
        },
        "summaries": [{"version": 1}],
        "agent_interactions": [],
        "ai_calls": [],
        "compliance_detection_attempts": [],
        "content_edits": [],
        "disposition_suggestions": [],
        "listening_mode_sessions": [],
        "crm_extractions": [],
        "metrics": {
            "mcp_queries": {
                "manual_count": 0,
                "auto_count": 0,
                "total_count": 0,
                "rated_up": 0,
                "rated_down": 0,
                "unrated": 0
            },
            "listening_mode": {
                "sessions_count": 0,
                "total_duration_secs": 0,
                "avg_auto_queries_per_session": 0
            },
            "ai_costs": {
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "avg_tokens_per_call": 0,
                "call_count": 0
            },
            "edits": {
                "summaries_edited": 0,
                "suggestions_edited": 0,
                "total_edits": 0
            }
        }
    }


class TestDashboardBugFix:
    """Tests that reproduce and verify the dashboard metrics bug."""

    def test_ai_feedback_from_user_rating_field(self, tmp_path):
        """BUG: AI feedback should be counted from user_rating field on interactions.

        The data export puts ratings in the user_rating field of query interactions,
        not as separate 'suggestion_rated' interaction types.
        """
        data = _make_realistic_conversation_data()

        # Real data structure: ratings are in user_rating field
        data["agent_interactions"] = [
            {
                "interaction_type": "manual_query",
                "timestamp": "2026-02-22T10:00:00",
                "query_text": "search for product",
                "user_rating": "up",  # Rating is HERE
                "manually_edited": False,
            },
            {
                "interaction_type": "manual_query",
                "timestamp": "2026-02-22T10:01:00",
                "query_text": "check order status",
                "user_rating": "down",  # Rating is HERE
                "manually_edited": False,
            },
            {
                "interaction_type": "mcp_query_auto",
                "timestamp": "2026-02-22T10:02:00",
                "query_text": "auto search",
                "user_rating": "up",  # Auto queries can be rated too
                "manually_edited": False,
            },
        ]

        # Update metrics to match (this is what data export calculates)
        data["metrics"]["mcp_queries"] = {
            "manual_count": 2,
            "auto_count": 1,
            "total_count": 3,
            "rated_up": 2,
            "rated_down": 1,
            "unrated": 0
        }

        _write_conversation_file(tmp_path, "conversation_data_001.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        # BUG: These should show rated feedback but currently show 0
        print(f"Feedback metrics: {result.feedback_metrics}")
        assert result.feedback_metrics.total_rated_up == 2, "Should count 2 thumbs up"
        assert result.feedback_metrics.total_rated_down == 1, "Should count 1 thumbs down"
        assert result.feedback_metrics.total_rated == 3, "Should count 3 total ratings"
        assert result.feedback_metrics.approval_rate == pytest.approx(66.67, rel=0.1)

    def test_suggestions_rated_count(self, tmp_path):
        """BUG: Suggestions rated should count interactions with non-null user_rating.

        The dashboard looks for interaction_type=='suggestion_rated' which doesn't exist.
        Should instead count interactions where user_rating is not null.
        """
        data = _make_realistic_conversation_data()

        data["agent_interactions"] = [
            {
                "interaction_type": "manual_query",
                "timestamp": "2026-02-22T10:00:00",
                "query_text": "search",
                "user_rating": "up",  # This is a rated suggestion
                "manually_edited": False,
            },
            {
                "interaction_type": "manual_query",
                "timestamp": "2026-02-22T10:01:00",
                "query_text": "search 2",
                "user_rating": "down",  # This is a rated suggestion
                "manually_edited": False,
            },
            {
                "interaction_type": "manual_query",
                "timestamp": "2026-02-22T10:02:00",
                "query_text": "search 3",
                "user_rating": None,  # This is NOT rated
                "manually_edited": False,
            },
        ]

        data["metrics"]["mcp_queries"]["manual_count"] = 3
        data["metrics"]["mcp_queries"]["rated_up"] = 1
        data["metrics"]["mcp_queries"]["rated_down"] = 1
        data["metrics"]["mcp_queries"]["unrated"] = 1

        _write_conversation_file(tmp_path, "conversation_data_001.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        # BUG: Currently shows 0 because it looks for non-existent 'suggestion_rated' type
        print(f"AI suggestion metrics: {result.ai_suggestion_metrics}")
        assert result.ai_suggestion_metrics.total_suggestions_rated == 2, \
            "Should count 2 suggestions with ratings (up + down)"

    def test_manual_queries_count(self, tmp_path):
        """BUG: Manual queries should be counted from mcp_query_manual interactions."""
        data = _make_realistic_conversation_data()

        data["agent_interactions"] = [
            {
                "interaction_type": "manual_query",
                "timestamp": "2026-02-22T10:00:00",
                "query_text": "manual search 1",
                "user_rating": None,
                "manually_edited": False,
            },
            {
                "interaction_type": "manual_query",
                "timestamp": "2026-02-22T10:01:00",
                "query_text": "manual search 2",
                "user_rating": None,
                "manually_edited": False,
            },
            {
                "interaction_type": "mcp_query_auto",
                "timestamp": "2026-02-22T10:02:00",
                "query_text": "auto search",
                "user_rating": None,
                "manually_edited": False,
            },
        ]

        data["metrics"]["mcp_queries"]["manual_count"] = 2
        data["metrics"]["mcp_queries"]["auto_count"] = 1

        _write_conversation_file(tmp_path, "conversation_data_001.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        print(f"AI suggestion metrics: {result.ai_suggestion_metrics}")
        assert result.ai_suggestion_metrics.total_manual_queries == 2, \
            "Should count 2 manual queries"
        assert result.ai_suggestion_metrics.total_auto_queries == 1, \
            "Should count 1 auto query"

    def test_manual_search_activity_outside_listening(self, tmp_path):
        """BUG: Manual search activity should work with real data structure."""
        data = _make_realistic_conversation_data()

        # Listening session from 10:01 to 10:03
        data["listening_mode_sessions"] = [
            {
                "started_at": "2026-02-22T10:01:00",
                "ended_at": "2026-02-22T10:03:00",
                "auto_queries_count": 0,
                "opportunities_detected": 0,
                "duration_secs": 120
            }
        ]

        # Manual queries: 1 before, 1 during, 1 after listening session
        data["agent_interactions"] = [
            {
                "interaction_type": "manual_query",
                "timestamp": "2026-02-22T10:00:00",  # Before session
                "query_text": "manual search before",
                "user_rating": None,
                "manually_edited": False,
            },
            {
                "interaction_type": "manual_query",
                "timestamp": "2026-02-22T10:02:00",  # During session
                "query_text": "manual search during",
                "user_rating": None,
                "manually_edited": False,
            },
            {
                "interaction_type": "manual_query",
                "timestamp": "2026-02-22T10:04:00",  # After session
                "query_text": "manual search after",
                "user_rating": None,
                "manually_edited": False,
            },
        ]

        data["metrics"]["mcp_queries"]["manual_count"] = 3

        _write_conversation_file(tmp_path, "conversation_data_001.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        print(f"Manual search metrics: {result.manual_search_metrics}")
        assert result.manual_search_metrics.total_manual_queries == 3
        assert result.manual_search_metrics.total_manual_inside_listening == 1
        assert result.manual_search_metrics.total_manual_outside_listening == 2

    def test_model_usage_counts(self, tmp_path):
        """Verify model usage is counted correctly."""
        data = _make_realistic_conversation_data()

        # Add AI calls with different models
        data["ai_calls"] = [
            {
                "interaction_type": "compliance",
                "model_name": "gpt-3.5-turbo",
                "tokens_used": 1000,
                "cost_usd": 0.002,
                "latency_ms": 150,
            },
            {
                "interaction_type": "summary",
                "model_name": "gpt-4o",
                "tokens_used": 2000,
                "cost_usd": 0.020,
                "latency_ms": 500,
            },
            {
                "interaction_type": "disposition",
                "model_name": "gpt-5",  # New model
                "tokens_used": 3000,
                "cost_usd": 0.030,
                "latency_ms": 300,
            },
        ]

        data["metrics"]["ai_costs_by_model"] = {
            "gpt-3.5-turbo": {
                "call_count": 1,
                "total_tokens": 1000,
                "total_cost_usd": 0.002,
                "avg_latency_ms": 150
            },
            "gpt-4o": {
                "call_count": 1,
                "total_tokens": 2000,
                "total_cost_usd": 0.020,
                "avg_latency_ms": 500
            },
            "gpt-5": {
                "call_count": 1,
                "total_tokens": 3000,
                "total_cost_usd": 0.030,
                "avg_latency_ms": 300
            }
        }

        _write_conversation_file(tmp_path, "conversation_data_001.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        print(f"Model breakdown: {result.model_breakdown}")

        # Should see all 3 models
        assert len(result.model_breakdown) == 3

        # Find gpt-5 model
        gpt5_model = next((m for m in result.model_breakdown if m.model_name == "gpt-5"), None)
        assert gpt5_model is not None, "Should find gpt-5 model in breakdown"
        assert gpt5_model.call_count == 1
        assert gpt5_model.total_tokens == 3000
        assert gpt5_model.total_cost_usd == 0.030

    def test_realistic_data_structure_from_export(self, tmp_path):
        """Integration test with data structure matching actual export format."""
        data = _make_realistic_conversation_data()

        # Populate with realistic data matching export service structure
        data["agent_interactions"] = [
            # Manual query with rating
            {
                "interaction_type": "manual_query",
                "timestamp": "2026-02-22T10:00:00",
                "query_text": "search for surge protector",
                "user_rating": "up",  # User rated this up
                "manually_edited": False,
                "llm_request": None,
                "llm_response": None,
                "mcp_request": None,
                "mcp_response": None,
                "edit_details": None,
                "context_data": {"tool_used": "search"}
            },
            # Auto query with rating
            {
                "interaction_type": "mcp_query_auto",
                "timestamp": "2026-02-22T10:02:00",
                "query_text": "check order 12345",
                "user_rating": "down",  # User rated this down
                "manually_edited": False,
                "llm_request": None,
                "llm_response": None,
                "mcp_request": None,
                "mcp_response": None,
                "edit_details": None,
                "context_data": {"opportunity_type": "order_tracking"}
            },
            # Manual query without rating
            {
                "interaction_type": "manual_query",
                "timestamp": "2026-02-22T10:03:00",
                "query_text": "find product specs",
                "user_rating": None,  # Not rated
                "manually_edited": False,
                "llm_request": None,
                "llm_response": None,
                "mcp_request": None,
                "mcp_response": None,
                "edit_details": None,
                "context_data": None
            },
        ]

        # Update metrics to match what data export calculates
        data["metrics"]["mcp_queries"] = {
            "manual_count": 2,
            "auto_count": 1,
            "total_count": 3,
            "rated_up": 1,
            "rated_down": 1,
            "unrated": 1
        }

        # Add AI calls
        data["ai_calls"] = [
            {
                "interaction_type": "compliance",
                "model_name": "gpt-3.5-turbo",
                "tokens_used": 1000,
                "cost_usd": 0.002,
                "latency_ms": 150,
                "agent_edited": False,
                "created_at": "2026-02-22T10:00:05"
            },
        ]

        data["metrics"]["ai_costs_by_model"] = {
            "gpt-3.5-turbo": {
                "call_count": 1,
                "total_tokens": 1000,
                "total_cost_usd": 0.002,
                "avg_latency_ms": 150
            }
        }

        _write_conversation_file(tmp_path, "conversation_data_001.json", data)

        service = DashboardService(data_dir=str(tmp_path))
        result = service.get_dashboard_data()

        # Verify feedback metrics (from aggregated metrics.mcp_queries)
        assert result.feedback_metrics.total_rated_up == 1
        assert result.feedback_metrics.total_rated_down == 1
        assert result.feedback_metrics.total_rated == 2

        # Verify AI suggestion metrics (from agent_interactions)
        assert result.ai_suggestion_metrics.total_manual_queries == 2
        assert result.ai_suggestion_metrics.total_auto_queries == 1
        assert result.ai_suggestion_metrics.total_suggestions_rated == 2  # BUG: Currently 0

        # Verify model breakdown
        assert len(result.model_breakdown) == 1
        assert result.model_breakdown[0].model_name == "gpt-3.5-turbo"