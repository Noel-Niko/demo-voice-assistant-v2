"""Pydantic schemas for API request/response validation.

These DTOs handle serialization/deserialization at the API boundary.
Follows DTO pattern for clean separation between API and domain models.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TranscriptLineSchema(BaseModel):
    """Transcript line schema for API responses.

    Supports real-time streaming with interim/final updates.

    Attributes:
        line_id: Unique identifier for logical line (tracks updates)
        timestamp: Original timestamp from transcript
        speaker: Speaker role (agent, customer, unknown)
        text: Transcript text content (may be partial if is_final=False)
        sequence_number: Order in original file
        is_final: Whether this is the final version (False for interim)
    """

    line_id: str
    timestamp: datetime
    speaker: str
    text: str
    sequence_number: int
    is_final: bool = Field(default=True, description="True if final, False if interim")

    model_config = {"from_attributes": True}


class SummarySchema(BaseModel):
    """Summary schema for API responses.

    Attributes:
        version: Summary version number
        summary_text: Generated summary content
        transcript_line_count: Number of lines summarized
        generated_at: Timestamp of generation
    """

    version: int
    summary_text: str
    transcript_line_count: int
    generated_at: datetime

    model_config = {"from_attributes": True}


class ConversationCreateResponse(BaseModel):
    """Response schema for conversation creation.

    Attributes:
        conversation_id: Unique conversation identifier
        status: Initial conversation status
        started_at: Timestamp when conversation started
    """

    conversation_id: str
    status: Literal["active", "completed"]
    started_at: datetime


class ConversationStateResponse(BaseModel):
    """Response schema for conversation state retrieval.

    Attributes:
        conversation_id: Unique conversation identifier
        status: Current conversation status
        started_at: Timestamp when conversation started
        ended_at: Timestamp when conversation ended (if completed)
        transcript_lines: All transcript lines
        summaries: All generated summaries
        summary_interval: Summary generation interval in seconds
        disposition_code: ACW disposition code (nullable)
        wrap_up_notes: ACW wrap-up notes (nullable)
        agent_feedback: ACW agent rating (nullable)
        acw_duration_secs: ACW phase duration (nullable)
        compliance_results: ACW compliance checklist results
        crm_field_extractions: ACW CRM field extractions
    """

    conversation_id: str
    status: Literal["active", "completed"]
    started_at: datetime
    ended_at: datetime | None
    transcript_lines: list[TranscriptLineSchema]
    summaries: list[SummarySchema]
    summary_interval: int
    disposition_code: str | None = None
    wrap_up_notes: str | None = None
    agent_feedback: str | None = None
    acw_duration_secs: int | None = None
    compliance_results: list["ComplianceResultSchema"] = []
    crm_field_extractions: list["CRMFieldExtractionSchema"] = []


class HealthCheckResponse(BaseModel):
    """Health check response schema.

    Attributes:
        status: Health status indicator
        timestamp: Current server timestamp
    """

    status: Literal["healthy", "unhealthy"]
    timestamp: datetime


# ===== ACW (After-Call Work) Schemas =====


class ComplianceCheckItemSchema(BaseModel):
    """Compliance checklist item schema.

    Attributes:
        label: Description of compliance item
        checked: Whether agent marked as complete
        auto_detected: Whether AI auto-detected this item
    """

    label: str
    checked: bool
    auto_detected: bool = Field(default=False)


class CRMFieldSchema(BaseModel):
    """CRM field extraction schema.

    Attributes:
        field_name: Name of CRM field
        extracted_value: Extracted value
        source: Extraction source (AI or Transcript)
        confidence: Confidence score (0.0 to 1.0)
    """

    field_name: str
    extracted_value: str
    source: Literal["AI", "Transcript"]
    confidence: float = Field(ge=0.0, le=1.0)


class ComplianceResultSchema(BaseModel):
    """Persisted compliance result schema for responses.

    Attributes:
        item_label: Description of compliance item
        is_checked: Whether agent marked as complete
        auto_detected: Whether AI auto-detected this item
        checked_at: Timestamp when checked
    """

    item_label: str
    is_checked: bool
    auto_detected: bool
    checked_at: datetime

    model_config = {"from_attributes": True}


class CRMFieldExtractionSchema(BaseModel):
    """Persisted CRM field extraction schema for responses.

    Attributes:
        field_name: Name of CRM field
        extracted_value: Extracted value
        source: Extraction source (AI or Transcript)
        confidence: Confidence score (0.0 to 1.0)
        extracted_at: Timestamp when extracted
    """

    field_name: str
    extracted_value: str
    source: str
    confidence: float
    extracted_at: datetime

    model_config = {"from_attributes": True}


class ACWCompleteRequest(BaseModel):
    """Request schema for completing a conversation with ACW data.

    All fields are optional to allow flexible partial updates.

    Attributes:
        disposition_code: Disposition code (e.g., RESOLVED, ESCALATED)
        wrap_up_notes: Agent's wrap-up notes
        agent_feedback: Agent rating (up or down)
        acw_duration_secs: ACW phase duration in seconds
        compliance_checklist: List of compliance items
        crm_fields: List of extracted CRM fields
    """

    disposition_code: str | None = None
    wrap_up_notes: str | None = None
    agent_feedback: Literal["up", "down"] | None = None
    acw_duration_secs: int | None = None
    compliance_checklist: list[ComplianceCheckItemSchema] | None = None
    crm_fields: list[CRMFieldSchema] | None = None


class ACWCompleteResponse(BaseModel):
    """Response schema for conversation completion.

    Returns the completed conversation state with ACW data.

    Attributes:
        conversation_id: Unique conversation identifier
        status: Conversation status (should be 'completed')
        started_at: Timestamp when conversation started
        ended_at: Timestamp when conversation ended
        disposition_code: Disposition code
        wrap_up_notes: Agent's wrap-up notes
        agent_feedback: Agent rating
        acw_duration_secs: ACW phase duration
        fcr: First Call Resolution (True/False/None)
        compliance_results: Saved compliance checklist
        crm_field_extractions: Saved CRM fields
    """

    conversation_id: str
    status: Literal["active", "completed"]
    started_at: datetime
    ended_at: datetime | None
    disposition_code: str | None = None
    wrap_up_notes: str | None = None
    agent_feedback: str | None = None
    acw_duration_secs: int | None = None
    fcr: bool | None = None
    compliance_results: list[ComplianceResultSchema] = []
    crm_field_extractions: list[CRMFieldExtractionSchema] = []


# ===== AI-Powered ACW Schemas (Phase 3) =====


class DispositionSuggestionSchema(BaseModel):
    """AI-suggested disposition code with confidence.

    Attributes:
        code: Disposition code (e.g., RESOLVED, ESCALATED)
        label: Human-readable label
        confidence: Confidence score (0.0 to 1.0)
        reasoning: Brief explanation for the suggestion
    """

    code: str
    label: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class DispositionSuggestionsResponse(BaseModel):
    """Response containing AI-generated disposition suggestions.

    Attributes:
        conversation_id: Conversation UUID
        suggestions: List of suggested dispositions (max 3, ordered by confidence)
    """

    conversation_id: str
    suggestions: list[DispositionSuggestionSchema]


class ComplianceItemDetectionSchema(BaseModel):
    """AI-detected compliance item.

    Attributes:
        label: Compliance item description
        detected: Whether AI detected this as completed
        confidence: Confidence score (0.0 to 1.0)
    """

    label: str
    detected: bool
    confidence: float = Field(ge=0.0, le=1.0)


class ComplianceDetectionResponse(BaseModel):
    """Response containing AI-detected compliance items.

    Attributes:
        conversation_id: Conversation UUID
        items: List of detected compliance items
    """

    conversation_id: str
    items: list[ComplianceItemDetectionSchema]


class CRMFieldExtractionResultSchema(BaseModel):
    """AI-extracted CRM field result.

    Attributes:
        field_name: CRM field name (e.g., "Case Subject", "Priority")
        value: Extracted value
        confidence: Confidence score (0.0 to 1.0)
    """

    field_name: str
    value: str
    confidence: float = Field(ge=0.0, le=1.0)


class CRMFieldsResponse(BaseModel):
    """Response containing AI-extracted CRM fields.

    Attributes:
        conversation_id: Conversation UUID
        fields: List of extracted CRM fields with confidence scores
    """

    conversation_id: str
    fields: list[CRMFieldExtractionResultSchema]


# ===== MCP (Model Context Protocol) Schemas =====


class MCPQueryRequest(BaseModel):
    """Request to query MCP server with LLM-driven tool selection.

    Attributes:
        query: User's natural language query
        conversation_id: UUID of conversation for metrics tracking
        preferred_server: Optional preferred server (e.g., "/product_retrieval")

    Note:
        Uses LLM (OpenAI GPT-3.5-turbo) to:
        1. Discover available tools dynamically via MCP protocol
        2. Select the most appropriate tool for the query
        3. Generate correct arguments based on tool's inputSchema
        4. Execute the tool call

        This is the proper MCP (Model Context Protocol) pattern.
        No hardcoded tools or arguments.
    """

    query: str = Field(..., min_length=1, max_length=500, description="User's natural language query")
    conversation_id: UUID = Field(..., description="Conversation UUID for metrics tracking")
    preferred_server: str | None = Field(default=None, description="Optional preferred server path (e.g., '/product_retrieval')")


class MCPSuggestionSchema(BaseModel):
    """MCP suggestion result.

    Attributes:
        title: Suggestion title
        content: Suggestion content/summary
        source: Source URL or identifier
        relevance: Relevance score (0.0 to 1.0)
    """

    title: str
    content: str
    source: str | None = None
    relevance: float = Field(default=1.0, ge=0.0, le=1.0)


class MCPQueryResponse(BaseModel):
    """Response from MCP query.

    Attributes:
        query: Original query
        suggestions: List of suggestions from MCP
        server_path: Server that handled the query
        tool_name: Tool that was called
    """

    query: str
    suggestions: list[MCPSuggestionSchema]
    server_path: str
    tool_name: str


class InteractionMetricsResponse(BaseModel):
    """Aggregated interaction metrics for conversation.

    Attributes:
        manual_queries: Count of manual MCP queries
        auto_queries: Count of automated MCP queries
        listening_mode_active: Whether listening mode is currently active
        total_opportunities: Total opportunities detected
        summary_ratings: Count of up/down ratings on summaries
        summary_edits: Count of manual summary edits
    """

    manual_queries: int = 0
    auto_queries: int = 0
    listening_mode_active: bool = False
    total_opportunities: int = 0
    summary_ratings: dict[str, int] = Field(default_factory=lambda: {"up": 0, "down": 0})
    summary_edits: int = 0


# ===== Listening Mode Schemas =====


class ListeningModeStartResponse(BaseModel):
    """Response schema for starting a listening mode session.

    Attributes:
        session_id: Database ID of the session
        conversation_id: Conversation UUID
        started_at: Timestamp when session started
        status: Session status (always 'active')
    """

    session_id: int
    conversation_id: str
    started_at: datetime
    status: Literal["active"]


class ListeningModeStopResponse(BaseModel):
    """Response schema for stopping a listening mode session.

    Attributes:
        session_id: Database ID of the session
        conversation_id: Conversation UUID
        ended_at: Timestamp when session ended
        auto_queries_count: Total auto-queries executed
        opportunities_detected: Total opportunities detected
        duration_seconds: Session duration in seconds
    """

    session_id: int
    conversation_id: str
    ended_at: datetime
    auto_queries_count: int
    opportunities_detected: int
    duration_seconds: float


# ===== Model Selection Schemas =====


class ModelPresetSchema(BaseModel):
    """Schema for a single model preset.

    Attributes:
        model_id: Unique preset identifier
        model_name: OpenAI API model name
        display_name: Human-readable label for UI
        reasoning_effort: Reasoning effort level (None for non-reasoning models)
        description: Short description for tooltip
    """

    model_id: str
    model_name: str
    display_name: str
    reasoning_effort: str | None = None
    description: str


class ModelConfigResponse(BaseModel):
    """Response schema for GET /api/model.

    Returns current model configuration and all available presets.

    Attributes:
        current_model_id: Currently active model ID
        current: Current model preset details
        available: All available model presets
    """

    current_model_id: str
    current: ModelPresetSchema
    available: list[ModelPresetSchema]


class ModelChangeRequest(BaseModel):
    """Request schema for PUT /api/model.

    Attributes:
        model_id: Model preset ID to switch to
    """

    model_id: str


class ModelChangeResponse(BaseModel):
    """Response schema for PUT /api/model.

    Attributes:
        status: Update status ("updated")
        model_id: New active model ID
        display_name: Human-readable name of new model
    """

    status: str
    model_id: str
    display_name: str


class ListeningModeStatusResponse(BaseModel):
    """Response schema for listening mode session status.

    Attributes:
        available: Whether listening mode feature is configured (MCP connected)
        is_active: Whether listening mode is currently active
        session_id: Database ID of the session (None if not active)
        conversation_id: Conversation UUID
        started_at: Timestamp when session started (None if not active)
        ended_at: Timestamp when session ended (None if active or never started)
        auto_queries_count: Total auto-queries executed
        opportunities_detected: Total opportunities detected
        elapsed_seconds: Session elapsed time in seconds (None if not active)
    """

    available: bool
    is_active: bool
    session_id: int | None
    conversation_id: str
    started_at: datetime | None
    ended_at: datetime | None
    auto_queries_count: int
    opportunities_detected: int
    elapsed_seconds: float | None


# ===== Suggestion Rating Schemas (Fix 2) =====


class SuggestionRatingRequest(BaseModel):
    """Request schema for rating an MCP suggestion.

    Attributes:
        rating: User rating ("up" for thumbs up, "down" for thumbs down)
    """

    rating: Literal["up", "down"]


class SuggestionRatingResponse(BaseModel):
    """Response schema for suggestion rating.

    Attributes:
        status: Status message (e.g., "rated")
        interaction_id: String representation of interaction ID
        rating: The rating that was applied
    """

    status: str
    interaction_id: str
    rating: str
