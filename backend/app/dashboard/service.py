"""Dashboard service - reads exported JSON files and computes metrics."""
from __future__ import annotations

import glob
import json
import os
from datetime import datetime
from typing import Any

import structlog

from app.constants import RESOLUTION_DISPOSITION_CODES
from app.dashboard.schemas import (
    ACWFormMetrics,
    AggregateKPIs,
    AISuggestionMetrics,
    ComplianceMetrics,
    ConversationMetricsSummary,
    DashboardData,
    FeedbackMetrics,
    ListeningModeMetrics,
    ManualSearchMetrics,
    ModelCostBreakdown,
    SummaryMetrics,
)

logger = structlog.get_logger(__name__)


class DashboardService:
    """Reads /tmp/conversation_data_*.json files and aggregates metrics.

    Stateless service — re-reads filesystem on each call to get_dashboard_data().
    """

    def __init__(
        self,
        data_dir: str = "/tmp",
        file_pattern: str = "conversation_data_*.json",
    ) -> None:
        self.data_dir = data_dir
        self.file_pattern = file_pattern

    def discover_files(self) -> list[str]:
        """Find all conversation data JSON files, sorted newest first."""
        pattern = os.path.join(self.data_dir, self.file_pattern)
        files = glob.glob(pattern)
        return sorted(files, key=os.path.getmtime, reverse=True)

    def load_conversation(self, file_path: str) -> dict[str, Any] | None:
        """Load and parse a single conversation JSON file.

        Returns None on any error (missing file, invalid JSON).
        """
        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("dashboard_file_load_error", file=file_path, error=str(e))
            return None

    def get_dashboard_data(self) -> DashboardData:
        """Load all files and compute complete dashboard data."""
        files = self.discover_files()
        all_data: list[dict[str, Any]] = []
        conversations: list[ConversationMetricsSummary] = []
        seen_ids: set[str] = set()

        for file_path in files:
            data = self.load_conversation(file_path)
            if data is None:
                continue
            conv_id = data.get("conversation", {}).get("id")
            if conv_id in seen_ids:
                continue
            seen_ids.add(conv_id)

            all_data.append(data)
            conversations.append(
                self._extract_conversation_metrics(data, file_path)
            )

        kpis = self._compute_kpis(conversations)

        total = len(conversations)
        total_summaries = sum(c.summary_count for c in conversations)
        total_edits = sum(c.total_edits for c in conversations)

        return DashboardData(
            generated_at=datetime.now().isoformat(),
            kpis=kpis,
            conversations=conversations,
            model_breakdown=self._aggregate_model_breakdown(all_data),
            compliance=self._aggregate_compliance(all_data),
            listening_mode=self._aggregate_listening_mode(all_data),
            summary_metrics=SummaryMetrics(
                total_summaries=total_summaries,
                total_edits=total_edits,
                avg_summaries_per_conversation=(
                    total_summaries / total if total > 0 else 0.0
                ),
            ),
            feedback_metrics=self._aggregate_feedback(conversations),
            acw_metrics=self._aggregate_acw_form_metrics(all_data),
            ai_suggestion_metrics=self._aggregate_ai_suggestion_metrics(all_data),
            manual_search_metrics=self._aggregate_manual_search_metrics(all_data),
        )

    def _extract_conversation_metrics(
        self, data: dict[str, Any], file_path: str
    ) -> ConversationMetricsSummary:
        """Extract metrics from a single conversation export."""
        conv = data.get("conversation", {})
        transcript = data.get("transcript", {})
        metrics = data.get("metrics", {})
        ai_costs = metrics.get("ai_costs", {})
        mcp_queries = metrics.get("mcp_queries", {})
        edits = metrics.get("edits", {})

        disposition_code = conv.get("disposition_code")
        fcr = None
        if disposition_code:
            fcr = disposition_code in RESOLUTION_DISPOSITION_CODES

        return ConversationMetricsSummary(
            conversation_id=conv.get("id", "unknown"),
            agent_id=conv.get("agent_id"),
            customer_id=conv.get("customer_id"),
            status=conv.get("status", "unknown"),
            started_at=conv.get("started_at"),
            ended_at=conv.get("ended_at"),
            duration_secs=transcript.get("duration_secs"),
            disposition_code=disposition_code,
            fcr=fcr,
            acw_duration_secs=conv.get("acw_duration_secs"),
            transcript_line_count=transcript.get("line_count", 0),
            transcript_word_count=transcript.get("word_count", 0),
            summary_count=len(data.get("summaries", [])),
            total_ai_cost_usd=ai_costs.get("total_cost_usd", 0.0),
            total_ai_tokens=ai_costs.get("total_tokens", 0),
            ai_call_count=ai_costs.get("call_count", 0),
            manual_query_count=mcp_queries.get("manual_count", 0),
            auto_query_count=mcp_queries.get("auto_count", 0),
            rated_up=mcp_queries.get("rated_up", 0),
            rated_down=mcp_queries.get("rated_down", 0),
            total_edits=edits.get("total_edits", 0),
            export_file=os.path.basename(file_path),
        )

    def _compute_kpis(
        self, conversations: list[ConversationMetricsSummary]
    ) -> AggregateKPIs:
        """Compute aggregate KPIs from all conversations."""
        total = len(conversations)
        if total == 0:
            return AggregateKPIs()

        durations = [
            c.duration_secs for c in conversations if c.duration_secs is not None
        ]
        avg_duration = sum(durations) / len(durations) if durations else 0.0

        acw_pcts: list[float] = []
        for c in conversations:
            if c.acw_duration_secs is not None and c.started_at and c.ended_at:
                try:
                    # Use call duration (started_at to ended_at), not transcript duration
                    start = datetime.fromisoformat(c.started_at)
                    end = datetime.fromisoformat(c.ended_at)
                    call_duration_secs = (end - start).total_seconds()

                    if call_duration_secs > 0:
                        acw_pct = (c.acw_duration_secs / call_duration_secs) * 100
                        # Cap at 100%
                        acw_pcts.append(min(acw_pct, 100.0))
                except (ValueError, AttributeError):
                    # Skip malformed timestamps
                    pass
        avg_acw_pct = sum(acw_pcts) / len(acw_pcts) if acw_pcts else 0.0

        total_cost = sum(c.total_ai_cost_usd for c in conversations)

        fcr_eligible = [c for c in conversations if c.fcr is not None]
        fcr_resolved = [c for c in fcr_eligible if c.fcr is True]

        return AggregateKPIs(
            total_conversations=total,
            avg_duration_secs=avg_duration,
            avg_acw_pct=avg_acw_pct,
            total_ai_cost_usd=total_cost,
            fcr_rate=(
                len(fcr_resolved) / len(fcr_eligible) * 100
                if fcr_eligible
                else 0.0
            ),
            fcr_eligible_count=len(fcr_eligible),
            fcr_resolved_count=len(fcr_resolved),
        )

    def _calculate_percentile(self, values: list[float], percentile: int) -> int:
        """Calculate percentile using linear interpolation.

        Args:
            values: List of numeric values
            percentile: Percentile to calculate (0-100)

        Returns:
            Percentile value as integer (rounds to nearest int)

        Algorithm:
            Uses linear interpolation method (similar to numpy's default).
            For percentile p and n values:
            - Position = p/100 * (n-1)
            - If position is integer, return values[position]
            - Otherwise, interpolate between floor and ceil positions
        """
        if not values:
            return 0
        if len(values) == 1:
            return int(round(values[0]))

        sorted_values = sorted(values)
        position = (percentile / 100.0) * (len(sorted_values) - 1)

        if position.is_integer():
            return int(round(sorted_values[int(position)]))

        lower_idx = int(position)
        upper_idx = lower_idx + 1
        weight = position - lower_idx

        interpolated = sorted_values[lower_idx] * (1 - weight) + sorted_values[upper_idx] * weight
        return int(round(interpolated))

    def _aggregate_model_breakdown(
        self, all_data: list[dict[str, Any]]
    ) -> list[ModelCostBreakdown]:
        """Aggregate AI cost breakdown by model across all conversations."""
        combined: dict[str, dict[str, Any]] = {}

        for data in all_data:
            # Still use ai_costs_by_model for tokens/cost aggregation
            by_model = data.get("metrics", {}).get("ai_costs_by_model", {})
            for model, stats in by_model.items():
                if model not in combined:
                    combined[model] = {
                        "call_count": 0,
                        "total_tokens": 0,
                        "total_cost_usd": 0.0,
                        "latencies": []  # NEW: Collect individual latencies
                    }
                combined[model]["call_count"] += stats.get("call_count", 0)
                combined[model]["total_tokens"] += stats.get("total_tokens", 0)
                combined[model]["total_cost_usd"] += stats.get("total_cost_usd", 0.0)

            # NEW: Extract individual latencies from ai_calls
            for call in data.get("ai_calls", []):
                model_name = call.get("model_name")
                latency = call.get("latency_ms")
                if model_name and latency is not None:
                    if model_name not in combined:
                        combined[model_name] = {
                            "call_count": 0,
                            "total_tokens": 0,
                            "total_cost_usd": 0.0,
                            "latencies": []
                        }
                    combined[model_name]["latencies"].append(latency)

        result: list[ModelCostBreakdown] = []
        for model, stats in combined.items():
            latencies = stats["latencies"]
            result.append(
                ModelCostBreakdown(
                    model_name=model,
                    call_count=stats["call_count"],
                    total_tokens=stats["total_tokens"],
                    total_cost_usd=stats["total_cost_usd"],
                    avg_latency_ms=int(sum(latencies) / len(latencies)) if latencies else 0,
                    p50_latency_ms=self._calculate_percentile(latencies, 50),
                    p99_latency_ms=self._calculate_percentile(latencies, 99),
                )
            )
        return sorted(result, key=lambda x: x.total_cost_usd, reverse=True)

    def _aggregate_compliance(
        self, all_data: list[dict[str, Any]]
    ) -> ComplianceMetrics:
        """Aggregate compliance detection metrics across all conversations."""
        total = 0
        correct = 0
        overrides = 0
        total_confidence = 0.0

        for data in all_data:
            for a in data.get("compliance_detection_attempts", []):
                total += 1
                total_confidence += a.get("ai_confidence", 0.0)
                if a.get("agent_override"):
                    overrides += 1
                elif a.get("ai_detected") == a.get("final_status"):
                    correct += 1

        return ComplianceMetrics(
            total_attempts=total,
            ai_correct=correct,
            agent_overrides=overrides,
            override_rate=(overrides / total) if total > 0 else 0.0,
            avg_confidence=(total_confidence / total) if total > 0 else 0.0,
        )

    def _aggregate_listening_mode(
        self, all_data: list[dict[str, Any]]
    ) -> ListeningModeMetrics:
        """Aggregate listening mode metrics across all conversations."""
        total_sessions = 0
        total_duration = 0.0
        total_auto = 0
        total_opportunities = 0

        for data in all_data:
            sessions = data.get("listening_mode_sessions", [])
            total_sessions += len(sessions)
            for s in sessions:
                dur = s.get("duration_secs")
                if dur is not None:
                    total_duration += dur
                total_auto += s.get("auto_queries_count", 0)
                total_opportunities += s.get("opportunities_detected", 0)

        return ListeningModeMetrics(
            total_sessions=total_sessions,
            total_duration_secs=total_duration,
            total_auto_queries=total_auto,
            avg_queries_per_session=(
                total_auto / total_sessions if total_sessions > 0 else 0.0
            ),
            total_opportunities=total_opportunities,
        )

    def _aggregate_feedback(
        self, conversations: list[ConversationMetricsSummary]
    ) -> FeedbackMetrics:
        """Aggregate feedback metrics (thumbs up/down) across all conversations."""
        total_up = sum(c.rated_up for c in conversations)
        total_down = sum(c.rated_down for c in conversations)
        total_rated = total_up + total_down

        approval_rate = (total_up / total_rated * 100) if total_rated > 0 else 0.0

        return FeedbackMetrics(
            total_rated_up=total_up,
            total_rated_down=total_down,
            total_rated=total_rated,
            approval_rate=approval_rate,
        )

    def _aggregate_acw_form_metrics(
        self, all_data: list[dict[str, Any]]
    ) -> ACWFormMetrics:
        """Aggregate end-of-call form (ACW) metrics across all conversations."""
        disposition_dist: dict[str, int] = {}
        total_with_disposition = 0
        notes_completed = 0
        agent_feedback_up = 0
        agent_feedback_down = 0
        agent_feedback_none = 0
        crm_total = 0
        crm_ai = 0
        crm_transcript = 0

        for data in all_data:
            # Disposition codes
            conv = data.get("conversation", {})
            disp_code = conv.get("disposition_code")
            if disp_code:
                disposition_dist[disp_code] = disposition_dist.get(disp_code, 0) + 1
                total_with_disposition += 1

            # Wrap-up notes
            wrap_up = conv.get("wrap_up_notes")
            if wrap_up and wrap_up.strip():
                notes_completed += 1

            # Agent feedback
            feedback = conv.get("agent_feedback")
            if feedback == "up":
                agent_feedback_up += 1
            elif feedback == "down":
                agent_feedback_down += 1
            else:
                agent_feedback_none += 1

            # CRM extractions
            crm_extractions = data.get("crm_extractions", [])
            for extraction in crm_extractions:
                crm_total += 1
                source = extraction.get("source", "")
                if source == "AI":
                    crm_ai += 1
                elif source == "Transcript":
                    crm_transcript += 1

        total_conversations = len(all_data) if all_data else 1  # Avoid division by zero
        notes_completion_rate = (
            (notes_completed / total_conversations * 100) if total_conversations > 0 else 0.0
        )
        crm_auto_fill_rate = (crm_ai / crm_total * 100) if crm_total > 0 else 0.0

        return ACWFormMetrics(
            disposition_distribution=disposition_dist,
            total_with_disposition=total_with_disposition,
            notes_completed=notes_completed,
            notes_completion_rate=notes_completion_rate,
            agent_feedback_up=agent_feedback_up,
            agent_feedback_down=agent_feedback_down,
            agent_feedback_none=agent_feedback_none,
            crm_total_extractions=crm_total,
            crm_ai_extractions=crm_ai,
            crm_transcript_extractions=crm_transcript,
            crm_auto_fill_rate=crm_auto_fill_rate,
        )

    def _aggregate_ai_suggestion_metrics(
        self, all_data: list[dict[str, Any]]
    ) -> AISuggestionMetrics:
        """Aggregate AI suggestion usage metrics across all conversations."""
        interaction_type_breakdown: dict[str, int] = {}
        total_manual = 0
        total_auto = 0
        total_rated = 0
        total_mode_switches = 0
        conversations_with_queries = 0

        for data in all_data:
            agent_interactions = data.get("agent_interactions", [])
            conv_has_queries = False

            for interaction in agent_interactions:
                itype = interaction.get("interaction_type")
                if not itype:
                    continue

                # Update breakdown
                interaction_type_breakdown[itype] = interaction_type_breakdown.get(itype, 0) + 1

                # Count specific types
                if itype == "manual_query":
                    total_manual += 1
                    conv_has_queries = True
                elif itype == "mcp_query_auto":
                    total_auto += 1
                    conv_has_queries = True
                elif itype == "mode_switch":
                    total_mode_switches += 1

                # Count rated suggestions (ratings are stored in user_rating field)
                user_rating = interaction.get("user_rating")
                if user_rating is not None:
                    total_rated += 1

            if conv_has_queries:
                conversations_with_queries += 1

        total_interactions = sum(interaction_type_breakdown.values())
        total_queries = total_manual + total_auto
        total_conversations = len(all_data) if all_data else 1

        avg_queries = (
            total_queries / total_conversations if total_conversations > 0 else 0.0
        )
        query_usage_rate = (
            (conversations_with_queries / total_conversations * 100)
            if total_conversations > 0
            else 0.0
        )

        return AISuggestionMetrics(
            total_interactions=total_interactions,
            total_manual_queries=total_manual,
            total_auto_queries=total_auto,
            total_suggestions_rated=total_rated,
            total_mode_switches=total_mode_switches,
            interaction_type_breakdown=interaction_type_breakdown,
            avg_queries_per_conversation=avg_queries,
            conversations_with_queries=conversations_with_queries,
            query_usage_rate=query_usage_rate,
        )

    def _aggregate_manual_search_metrics(
        self, all_data: list[dict[str, Any]]
    ) -> ManualSearchMetrics:
        """Aggregate manual search metrics (queries outside listening mode)."""
        total_manual = 0
        total_outside = 0
        total_inside = 0
        conversations_with_outside = 0

        for data in all_data:
            # Parse listening mode sessions into datetime windows
            listening_sessions = data.get("listening_mode_sessions", [])
            listening_windows: list[tuple[datetime, datetime]] = []

            for session in listening_sessions:
                started_str = session.get("started_at")
                ended_str = session.get("ended_at")
                if started_str and ended_str:
                    try:
                        start = datetime.fromisoformat(started_str)
                        end = datetime.fromisoformat(ended_str)
                        listening_windows.append((start, end))
                    except (ValueError, AttributeError):
                        pass  # Skip malformed timestamps

            # Check each manual query against listening windows
            agent_interactions = data.get("agent_interactions", [])
            conv_has_outside = False

            for interaction in agent_interactions:
                if interaction.get("interaction_type") != "manual_query":
                    continue

                total_manual += 1
                timestamp_str = interaction.get("timestamp")
                if not timestamp_str:
                    # No timestamp → count as outside
                    total_outside += 1
                    conv_has_outside = True
                    continue

                try:
                    query_time = datetime.fromisoformat(timestamp_str)
                    # Check if query falls within ANY listening window
                    is_inside = any(
                        start <= query_time <= end for start, end in listening_windows
                    )
                    if is_inside:
                        total_inside += 1
                    else:
                        total_outside += 1
                        conv_has_outside = True
                except (ValueError, AttributeError):
                    # Malformed timestamp → count as outside
                    total_outside += 1
                    conv_has_outside = True

            if conv_has_outside:
                conversations_with_outside += 1

        total_conversations = len(all_data) if all_data else 1
        avg_outside = (
            total_outside / total_conversations if total_conversations > 0 else 0.0
        )
        outside_rate = (
            (total_outside / total_manual * 100) if total_manual > 0 else 0.0
        )

        return ManualSearchMetrics(
            total_manual_queries=total_manual,
            total_manual_outside_listening=total_outside,
            total_manual_inside_listening=total_inside,
            avg_outside_per_conversation=avg_outside,
            conversations_with_outside_queries=conversations_with_outside,
            outside_query_rate=outside_rate,
        )
