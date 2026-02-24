"""SQLAlchemy ORM models for database tables.

Follows Data Mapper pattern for clean separation between domain and persistence.
"""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Float
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Conversation(Base):
    """Conversation entity representing a customer service interaction.

    Attributes:
        id: Unique conversation identifier (UUID as string)
        status: Current status (active, completed)
        started_at: Timestamp when conversation started
        ended_at: Timestamp when conversation ended (nullable)

        # Tier 1: Legal/Regulatory (audit trail)
        agent_id: ID of agent who handled the conversation
        customer_id: ID of customer (external system reference)
        recording_id: Link to audio recording (Genesys)
        queue_name: Queue where call was routed
        interaction_id: External interaction ID (Genesys)

        # ACW (After-Call Work) fields
        disposition_code: ACW disposition code (nullable)
        wrap_up_notes: ACW wrap-up notes (nullable)
        agent_feedback: ACW agent rating - 'up', 'down', or null (nullable)
        acw_duration_secs: ACW phase duration in seconds (nullable)

        # Relationships
        transcript_lines: Related transcript lines
        summaries: Related summaries
        compliance_results: Related compliance checklist results
        crm_field_extractions: Related CRM field extractions
        ai_interactions: Related AI/LLM interactions (audit)
        disposition_suggestions: Related AI disposition suggestions
        content_edits: Related content edit history
        compliance_attempts: Related compliance detection attempts
    """

    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    status = Column(String(20), nullable=False, default="active")
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime, nullable=True)

    # Tier 1: Legal/Regulatory audit fields
    agent_id = Column(String(50), nullable=True, index=True)
    customer_id = Column(String(50), nullable=True, index=True)
    recording_id = Column(String(100), nullable=True)
    queue_name = Column(String(100), nullable=True)
    interaction_id = Column(String(100), nullable=True, index=True)

    # ACW (After-Call Work) fields
    disposition_code = Column(String(50), nullable=True)
    wrap_up_notes = Column(Text, nullable=True)
    agent_feedback = Column(String(10), nullable=True)  # 'up', 'down', or null
    acw_duration_secs = Column(Integer, nullable=True)

    # Summary configuration
    summary_interval = Column(Integer, nullable=False, default=30, server_default='30')

    # Relationships
    transcript_lines = relationship(
        "TranscriptLine",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    summaries = relationship(
        "Summary",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    compliance_results = relationship(
        "ComplianceResult",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    crm_field_extractions = relationship(
        "CRMFieldExtraction",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    ai_interactions = relationship(
        "AIInteraction",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    disposition_suggestions = relationship(
        "DispositionSuggestion",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    content_edits = relationship(
        "ContentEdit",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    compliance_attempts = relationship(
        "ComplianceDetectionAttempt",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    agent_interactions = relationship(
        "AgentInteraction",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    listening_mode_sessions = relationship(
        "ListeningModeSession",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, status={self.status}, agent_id={self.agent_id})>"


class TranscriptLine(Base):
    """Individual transcript line from conversation.

    Supports real-time streaming with interim/final updates (like Genesys).

    Attributes:
        id: Auto-increment primary key
        conversation_id: Foreign key to conversation
        line_id: Unique identifier for this logical line (tracks interim updates)
        timestamp: Original timestamp from transcript file
        speaker: Speaker role (agent, customer, unknown)
        text: Transcript text content (may be partial if is_final=False)
        sequence_number: Order in original file
        is_final: Whether this is the final version (False for interim updates)
        added_at: Timestamp when added to database
        conversation: Related conversation entity
    """

    __tablename__ = "transcript_lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        String(36),
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )
    line_id = Column(String(100), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False)
    speaker = Column(String(20), nullable=False)
    text = Column(Text, nullable=False)
    sequence_number = Column(Integer, nullable=False)
    is_final = Column(Boolean, nullable=False, default=False)
    added_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    conversation = relationship("Conversation", back_populates="transcript_lines")

    def __repr__(self) -> str:
        return (
            f"<TranscriptLine(id={self.id}, "
            f"speaker={self.speaker}, "
            f"seq={self.sequence_number})>"
        )


class Summary(Base):
    """AI-generated summary of conversation.

    Summaries are versioned to track evolution over time.

    Attributes:
        id: Auto-increment primary key
        conversation_id: Foreign key to conversation
        version: Incremental version number (1, 2, 3, ...)
        summary_text: Generated summary content
        transcript_line_count: Number of transcript lines summarized
        generated_at: Timestamp when summary was generated
        conversation: Related conversation entity
    """

    __tablename__ = "summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        String(36),
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)
    summary_text = Column(Text, nullable=False)
    transcript_line_count = Column(Integer, nullable=False)
    generated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    conversation = relationship("Conversation", back_populates="summaries")

    def __repr__(self) -> str:
        return (
            f"<Summary(id={self.id}, "
            f"conversation_id={self.conversation_id}, "
            f"version={self.version})>"
        )


class ComplianceResult(Base):
    """Compliance checklist result from ACW phase.

    Tracks which compliance items were completed, including auto-detection.

    Attributes:
        id: Auto-increment primary key
        conversation_id: Foreign key to conversation
        item_label: Description of compliance item
        is_checked: Whether agent marked this item as done
        auto_detected: Whether this was auto-detected by AI
        checked_at: Timestamp when checked
        conversation: Related conversation entity
    """

    __tablename__ = "compliance_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        String(36),
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )
    item_label = Column(String(200), nullable=False)
    is_checked = Column(Boolean, nullable=False)
    auto_detected = Column(Boolean, nullable=False, default=False)
    checked_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    conversation = relationship("Conversation", back_populates="compliance_results")

    def __repr__(self) -> str:
        return (
            f"<ComplianceResult(id={self.id}, "
            f"conversation_id={self.conversation_id}, "
            f"label={self.item_label})>"
        )


class CRMFieldExtraction(Base):
    """CRM field extracted from conversation during ACW.

    Tracks AI-extracted or transcript-derived Salesforce case fields.

    Attributes:
        id: Auto-increment primary key
        conversation_id: Foreign key to conversation
        field_name: Name of CRM field (e.g., 'Case Subject', 'Priority')
        extracted_value: Extracted value for the field
        source: Source of extraction ('AI' or 'Transcript')
        confidence: Confidence score (0.0 to 1.0)
        extracted_at: Timestamp when extracted
        conversation: Related conversation entity
    """

    __tablename__ = "crm_field_extractions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        String(36),
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )
    field_name = Column(String(100), nullable=False)
    extracted_value = Column(Text, nullable=False)
    source = Column(String(20), nullable=False)  # 'AI' or 'Transcript'
    confidence = Column(Float, nullable=False)
    extracted_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    conversation = relationship("Conversation", back_populates="crm_field_extractions")

    def __repr__(self) -> str:
        return (
            f"<CRMFieldExtraction(id={self.id}, "
            f"conversation_id={self.conversation_id}, "
            f"field={self.field_name})>"
        )


# ===== Tier 1: Legal/Regulatory Audit Tables =====


class AIInteraction(Base):
    """Audit trail for all AI/LLM interactions.

    Tracks every OpenAI API call with full prompts, responses, and costs.
    Critical for compliance, debugging, and cost tracking.

    Attributes:
        id: Auto-increment primary key
        conversation_id: Foreign key to conversation
        interaction_type: Type of AI interaction ('summary', 'disposition', 'compliance', 'crm')
        prompt_text: Full prompt sent to LLM
        response_text: Full response from LLM
        model_name: Model used (e.g., 'gpt-3.5-turbo')
        tokens_used: Total tokens consumed
        cost_usd: Cost in USD
        latency_ms: Response time in milliseconds
        created_at: Timestamp of API call
        agent_edited: Whether agent modified the AI output
        final_value: What agent actually used (if different from response_text)
        conversation: Related conversation entity
    """

    __tablename__ = "ai_interactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        String(36),
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )
    interaction_type = Column(String(50), nullable=False, index=True)
    prompt_text = Column(Text, nullable=False)
    response_text = Column(Text, nullable=False)
    model_name = Column(String(50), nullable=False)
    tokens_used = Column(Integer, nullable=False)
    cost_usd = Column(Float, nullable=False)
    latency_ms = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    agent_edited = Column(Boolean, nullable=False, default=False)
    final_value = Column(Text, nullable=True)

    # Relationships
    conversation = relationship("Conversation", back_populates="ai_interactions")

    def __repr__(self) -> str:
        return (
            f"<AIInteraction(id={self.id}, "
            f"type={self.interaction_type}, "
            f"tokens={self.tokens_used})>"
        )


class DispositionSuggestion(Base):
    """AI-generated disposition code suggestions.

    Tracks what AI recommended vs. what agent actually selected.
    Critical for measuring AI accuracy and agent agreement rates.

    Attributes:
        id: Auto-increment primary key
        conversation_id: Foreign key to conversation
        suggested_code: Disposition code suggested by AI
        suggested_label: Human-readable label
        confidence: Confidence score (0.0 to 1.0)
        reasoning: AI's explanation for suggestion
        rank: Ranking (1, 2, or 3) ordered by confidence
        was_selected: Whether agent selected this suggestion
        created_at: Timestamp when generated
        conversation: Related conversation entity
    """

    __tablename__ = "disposition_suggestions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        String(36),
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )
    suggested_code = Column(String(50), nullable=False)
    suggested_label = Column(String(200), nullable=False)
    confidence = Column(Float, nullable=False)
    reasoning = Column(Text, nullable=False)
    rank = Column(Integer, nullable=False)  # 1, 2, or 3
    was_selected = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    conversation = relationship("Conversation", back_populates="disposition_suggestions")

    def __repr__(self) -> str:
        return (
            f"<DispositionSuggestion(id={self.id}, "
            f"code={self.suggested_code}, "
            f"rank={self.rank}, "
            f"selected={self.was_selected})>"
        )


# ===== Tier 2: Quality Assurance Tables =====


class ContentEdit(Base):
    """Audit trail for agent edits to AI-generated content.

    Tracks when agents modify AI suggestions (summaries, CRM fields, etc.).
    Used for quality assurance and AI model improvement.

    Attributes:
        id: Auto-increment primary key
        conversation_id: Foreign key to conversation
        field_name: Field that was edited (e.g., 'wrap_up_notes', 'crm_field_case_subject')
        original_value: What AI generated
        edited_value: What agent changed it to
        edit_type: Type of edit ('addition', 'deletion', 'modification', 'complete_rewrite')
        edited_at: Timestamp of edit
        agent_id: ID of agent who made the edit
        conversation: Related conversation entity
    """

    __tablename__ = "content_edits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        String(36),
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )
    field_name = Column(String(50), nullable=False)
    original_value = Column(Text, nullable=False)
    edited_value = Column(Text, nullable=False)
    edit_type = Column(String(20), nullable=False)
    edited_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    agent_id = Column(String(50), nullable=False, index=True)

    # Relationships
    conversation = relationship("Conversation", back_populates="content_edits")

    def __repr__(self) -> str:
        return (
            f"<ContentEdit(id={self.id}, "
            f"field={self.field_name}, "
            f"type={self.edit_type})>"
        )


class ComplianceDetectionAttempt(Base):
    """Audit trail for AI compliance detection attempts.

    Tracks all compliance checks (auto-detected vs. manual) with agent overrides.
    Critical for measuring AI accuracy and ensuring quality standards.

    Attributes:
        id: Auto-increment primary key
        conversation_id: Foreign key to conversation
        item_label: Description of compliance item
        ai_detected: Whether AI detected this item as complete
        ai_confidence: AI's confidence score (0.0 to 1.0)
        agent_override: Whether agent disagreed with AI assessment
        final_status: What was actually saved (true/false)
        detected_at: Timestamp of detection
        conversation: Related conversation entity
    """

    __tablename__ = "compliance_detection_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        String(36),
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )
    item_label = Column(String(200), nullable=False)
    ai_detected = Column(Boolean, nullable=False)
    ai_confidence = Column(Float, nullable=False)
    agent_override = Column(Boolean, nullable=False, default=False)
    final_status = Column(Boolean, nullable=False)
    detected_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    conversation = relationship("Conversation", back_populates="compliance_attempts")

    def __repr__(self) -> str:
        return (
            f"<ComplianceDetectionAttempt(id={self.id}, "
            f"item={self.item_label}, "
            f"ai_detected={self.ai_detected}, "
            f"override={self.agent_override})>"
        )


# ===== Tier 3: Agent Interaction Metrics Tables =====


class AgentInteraction(Base):
    """Tracks all agent interactions with AI features for analytics and optimization.

    Captures comprehensive metrics including:
    - Manual vs. auto-query usage
    - User ratings on AI suggestions
    - Manual edits to AI content
    - Mode switches (listening mode toggle)
    - Raw LLM/MCP request/response data

    Attributes:
        id: Auto-increment primary key
        conversation_id: Foreign key to conversation
        interaction_type: Type of interaction (see below for values)
        timestamp: When interaction occurred
        query_text: Original query text (for MCP queries)
        llm_request: Raw LLM request payload (JSON)
        llm_response: Raw LLM response payload (JSON)
        mcp_request: Raw MCP request payload (JSON)
        mcp_response: Raw MCP response payload (JSON)
        user_rating: Agent rating ('up', 'down', null)
        manually_edited: Whether agent edited AI output
        edit_details: Before/after edit information (JSON)
        context_data: Additional context (server used, tool used, etc.) (JSON)
        conversation: Related conversation entity

    Interaction Types:
        - 'mcp_query_manual': Agent manually entered a query
        - 'mcp_query_auto': Listening mode auto-triggered a query
        - 'mode_switch': Agent toggled listening mode on/off
        - 'suggestion_rated': Agent rated an AI suggestion up/down
        - 'summary_edited': Agent manually edited AI summary
        - 'disposition_selected': Agent selected disposition (AI vs manual)
        - 'compliance_override': Agent overrode AI compliance detection
    """

    __tablename__ = "agent_interactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        String(36),
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )
    interaction_type = Column(String(50), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    query_text = Column(Text, nullable=True)
    llm_request = Column(Text, nullable=True)  # JSON string
    llm_response = Column(Text, nullable=True)  # JSON string
    mcp_request = Column(Text, nullable=True)  # JSON string
    mcp_response = Column(Text, nullable=True)  # JSON string
    user_rating = Column(String(10), nullable=True)  # 'up', 'down', null
    manually_edited = Column(Boolean, nullable=False, default=False)
    edit_details = Column(Text, nullable=True)  # JSON string
    context_data = Column(Text, nullable=True)  # JSON string (renamed from metadata to avoid SQLAlchemy conflict)

    # Relationships
    conversation = relationship("Conversation", back_populates="agent_interactions")

    def __repr__(self) -> str:
        return (
            f"<AgentInteraction(id={self.id}, "
            f"type={self.interaction_type}, "
            f"rating={self.user_rating})>"
        )


class ListeningModeSession(Base):
    """Tracks AI listening mode sessions for analytics.

    Listening mode: AI automatically detects opportunities and triggers queries
    without manual agent input. This table tracks session metrics.

    Attributes:
        id: Auto-increment primary key
        conversation_id: Foreign key to conversation
        started_at: When listening mode was enabled
        ended_at: When listening mode was disabled (null if still active)
        auto_queries_count: Number of auto-triggered queries
        products_suggested: List of products suggested (JSON array)
        orders_tracked: List of orders tracked (JSON array)
        opportunities_detected: Number of opportunities AI detected
        conversation: Related conversation entity

    JSON Formats:
        products_suggested: [
            {"sku": "1FYX7", "name": "ANSELL Gloves", "reason": "...", "timestamp": "2026-02-21T..."},
            ...
        ]
        orders_tracked: [
            {"order_number": "12345", "status": "Shipped", "delivery_date": "2/23", "timestamp": "..."},
            ...
        ]
    """

    __tablename__ = "listening_mode_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        String(36),
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime, nullable=True)
    auto_queries_count = Column(Integer, nullable=False, default=0, server_default='0')
    products_suggested = Column(Text, nullable=True)  # JSON array
    orders_tracked = Column(Text, nullable=True)  # JSON array
    opportunities_detected = Column(Integer, nullable=False, default=0, server_default='0')

    # Relationships
    conversation = relationship("Conversation", back_populates="listening_mode_sessions")

    def __repr__(self) -> str:
        duration = "active"
        if self.ended_at:
            duration = f"{(self.ended_at - self.started_at).total_seconds()}s"
        return (
            f"<ListeningModeSession(id={self.id}, "
            f"queries={self.auto_queries_count}, "
            f"duration={duration})>"
        )
