"""Pydantic schemas for dashboard data."""
from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DashboardSettings(BaseSettings):
    """Dashboard configuration (12-factor: config from env vars)."""

    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    DASHBOARD_HOST: str = "0.0.0.0"
    DASHBOARD_PORT: int = 8766
    DASHBOARD_DATA_DIR: str = "/tmp"
    DASHBOARD_LOG_LEVEL: str = "INFO"
    DASHBOARD_FILE_PATTERN: str = "conversation_data_*.json"
    DASHBOARD_MAIN_APP_URL: str = "http://localhost:8765"


class ConversationMetricsSummary(BaseModel):
    """Per-conversation row for the dashboard table."""

    conversation_id: str
    agent_id: str | None = None
    customer_id: str | None = None
    status: str = "unknown"
    started_at: str | None = None
    ended_at: str | None = None
    duration_secs: float | None = None
    disposition_code: str | None = None
    fcr: bool | None = None
    acw_duration_secs: int | None = None
    transcript_line_count: int = 0
    transcript_word_count: int = 0
    summary_count: int = 0
    total_ai_cost_usd: float = 0.0
    total_ai_tokens: int = 0
    ai_call_count: int = 0
    manual_query_count: int = 0
    auto_query_count: int = 0
    rated_up: int = 0
    rated_down: int = 0
    total_edits: int = 0
    export_file: str = ""


class AggregateKPIs(BaseModel):
    """Top-level KPI cards for the dashboard."""

    total_conversations: int = 0
    avg_duration_secs: float = 0.0
    avg_acw_pct: float = 0.0
    total_ai_cost_usd: float = 0.0
    fcr_rate: float = 0.0
    fcr_eligible_count: int = 0
    fcr_resolved_count: int = 0


class ModelCostBreakdown(BaseModel):
    """Cost and performance metrics for a single LLM model."""

    model_name: str
    call_count: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    avg_latency_ms: int = 0  # Keep for backward compatibility
    p50_latency_ms: int = 0  # Median latency
    p99_latency_ms: int = 0  # 99th percentile latency


class ComplianceMetrics(BaseModel):
    """Compliance detection accuracy metrics."""

    total_attempts: int = 0
    ai_correct: int = 0
    agent_overrides: int = 0
    override_rate: float = 0.0
    avg_confidence: float = 0.0


class ListeningModeMetrics(BaseModel):
    """Listening mode aggregate metrics."""

    total_sessions: int = 0
    total_duration_secs: float = 0.0
    total_auto_queries: int = 0
    avg_queries_per_session: float = 0.0
    total_opportunities: int = 0


class SummaryMetrics(BaseModel):
    """Summary generation aggregate metrics."""

    total_summaries: int = 0
    total_edits: int = 0
    avg_summaries_per_conversation: float = 0.0


class FeedbackMetrics(BaseModel):
    """AI suggestion feedback metrics (thumbs up/down)."""

    total_rated_up: int = 0
    total_rated_down: int = 0
    total_rated: int = 0
    approval_rate: float = 0.0


class ACWFormMetrics(BaseModel):
    """End-of-call form (ACW) metrics."""

    disposition_distribution: dict[str, int] = Field(default_factory=dict)
    total_with_disposition: int = 0
    notes_completed: int = 0
    notes_completion_rate: float = 0.0
    agent_feedback_up: int = 0
    agent_feedback_down: int = 0
    agent_feedback_none: int = 0
    crm_total_extractions: int = 0
    crm_ai_extractions: int = 0
    crm_transcript_extractions: int = 0
    crm_auto_fill_rate: float = 0.0


class AISuggestionMetrics(BaseModel):
    """AI suggestion usage metrics."""

    total_interactions: int = 0
    total_manual_queries: int = 0
    total_auto_queries: int = 0
    total_suggestions_rated: int = 0
    total_mode_switches: int = 0
    interaction_type_breakdown: dict[str, int] = Field(default_factory=dict)
    avg_queries_per_conversation: float = 0.0
    conversations_with_queries: int = 0
    query_usage_rate: float = 0.0


class ManualSearchMetrics(BaseModel):
    """Manual search frequency when listening mode is off."""

    total_manual_queries: int = 0
    total_manual_outside_listening: int = 0
    total_manual_inside_listening: int = 0
    avg_outside_per_conversation: float = 0.0
    conversations_with_outside_queries: int = 0
    outside_query_rate: float = 0.0


class DashboardData(BaseModel):
    """Complete dashboard response."""

    generated_at: str
    main_app_url: str = "http://localhost:8765"
    kpis: AggregateKPIs = AggregateKPIs()
    conversations: list[ConversationMetricsSummary] = Field(default_factory=list)
    model_breakdown: list[ModelCostBreakdown] = Field(default_factory=list)
    compliance: ComplianceMetrics = ComplianceMetrics()
    listening_mode: ListeningModeMetrics = ListeningModeMetrics()
    summary_metrics: SummaryMetrics = SummaryMetrics()
    feedback_metrics: FeedbackMetrics = FeedbackMetrics()
    acw_metrics: ACWFormMetrics = ACWFormMetrics()
    ai_suggestion_metrics: AISuggestionMetrics = AISuggestionMetrics()
    manual_search_metrics: ManualSearchMetrics = ManualSearchMetrics()
