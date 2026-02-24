"""ACW Service for AI-powered After-Call Work features.

Provides disposition suggestions, compliance detection, and CRM field extraction.
All LLM interactions are logged to ai_interactions table for audit trail.
"""
import json
import time
from uuid import UUID
from openai import AsyncOpenAI

from app.repositories.conversation_repository import ConversationRepository
from app.constants import PRIORITY_VALUES, CASE_TYPE_VALUES, CRM_FIELD_NAMES

import structlog

logger = structlog.get_logger(__name__)


# Disposition code taxonomy (production would come from database/config)
DISPOSITION_CODES = [
    {"code": "RESOLVED", "label": "Issue Resolved"},
    {"code": "ESCALATED", "label": "Escalated to Supervisor"},
    {"code": "FOLLOWUP", "label": "Follow-up Required"},
    {"code": "TRANSFERRED", "label": "Transferred to Another Department"},
    {"code": "CALLBACK_REQUESTED", "label": "Customer Requested Callback"},
    {"code": "UNRESOLVED", "label": "Issue Unresolved"},
]

# Compliance checklist items (production would come from database/config)
COMPLIANCE_ITEMS = [
    "Verified customer identity",
    "Confirmed order number",
    "Identified root cause",
    "Explained resolution clearly",
    "Offered compensation if applicable",
    "Confirmed next steps and timeline",
    "Asked if anything else needed",
]


class ACWService:
    """Service for AI-powered ACW features.

    Handles disposition suggestions, compliance detection, and CRM extraction.
    Logs all LLM interactions for compliance and cost tracking.
    """

    def __init__(
        self,
        repository: ConversationRepository,
        openai_api_key: str,
        model: str = "gpt-3.5-turbo",
    ):
        """Initialize ACW service.

        Args:
            repository: Conversation repository for data access
            openai_api_key: OpenAI API key
            model: OpenAI model to use (default: gpt-3.5-turbo)
        """
        self.repository = repository
        self.model = model
        self._reasoning_effort: str | None = None
        self.client = AsyncOpenAI(api_key=openai_api_key, timeout=60.0)  # 60 second timeout

    def set_model(self, model: str, reasoning_effort: str | None = None) -> None:
        """Update the LLM model used for ACW features.

        Args:
            model: OpenAI model name
            reasoning_effort: Optional reasoning effort level
        """
        self.model = model
        self._reasoning_effort = reasoning_effort
        logger.info(
            "acw_service_model_updated",
            model=model,
            reasoning_effort=reasoning_effort,
        )

    def _get_current_model_config(self) -> tuple[str, str | None]:
        """Get current model config atomically.

        Returns model and reasoning_effort as a tuple to avoid race conditions
        when model is changed mid-operation.

        Returns:
            Tuple of (model, reasoning_effort)
        """
        return (self.model, self._reasoning_effort)

    def _build_api_kwargs(self, base_temp: float, model: str, reasoning_effort: str | None) -> dict:
        """Build API kwargs based on model type.

        o1-family models require reasoning_effort instead of temperature.

        Args:
            base_temp: Default temperature for non-o1 models
            model: Model name to use (captured atomically)
            reasoning_effort: Reasoning effort level (captured atomically)

        Returns:
            Dict of API kwargs compatible with the current model
        """
        kwargs = {
            "model": model,
        }

        # o1 models (gpt-5, o1-preview, o1-mini) require reasoning_effort instead of temperature
        is_o1_model = model.startswith("o1-") or model == "gpt-5"

        if is_o1_model and reasoning_effort is not None:
            kwargs["reasoning_effort"] = reasoning_effort
        else:
            kwargs["temperature"] = base_temp

        return kwargs

    async def generate_disposition_suggestions(
        self, conversation_id: UUID
    ) -> dict:
        """Generate AI disposition code suggestions.

        Analyzes summary and transcript to suggest top 3 disposition codes
        with confidence scores. Logs interaction to ai_interactions table
        and saves suggestions to disposition_suggestions table.

        Args:
            conversation_id: Conversation UUID

        Returns:
            Dict with 'suggestions' list containing code, label, confidence, reasoning
        """
        # Capture model config atomically at the start to avoid race conditions
        # when model changes mid-operation
        model, reasoning_effort = self._get_current_model_config()

        start_time = time.time()

        # Get conversation context (prefer summary, fallback to transcript)
        summary = await self.repository.get_latest_summary(conversation_id)
        if summary:
            context_text = f"Summary: {summary.summary_text}"
        else:
            # Fallback to transcript
            lines = await self.repository.get_all_transcript_lines(conversation_id)
            transcript_text = "\n".join([f"{line.speaker}: {line.text}" for line in lines[:20]])  # First 20 lines
            context_text = f"Transcript excerpt:\n{transcript_text}"

        # Build prompt
        codes_list = "\n".join([f"- {c['code']}: {c['label']}" for c in DISPOSITION_CODES])
        prompt = f"""Analyze this customer service conversation and suggest the top 3 most appropriate disposition codes.

Available disposition codes:
{codes_list}

Conversation context:
{context_text}

Return your analysis as JSON with this exact structure:
{{
  "suggestions": [
    {{"code": "DISPOSITION_CODE", "label": "Human Label", "confidence": 0.95, "reasoning": "Brief explanation"}},
    ...
  ]
}}

Provide 1-3 suggestions ordered by confidence (highest first). Each suggestion must include:
- code: One of the available codes above
- label: The human-readable label
- confidence: Float between 0.0 and 1.0
- reasoning: Brief explanation (1-2 sentences)"""

        # Call OpenAI - use captured model config to prevent race conditions
        api_kwargs = self._build_api_kwargs(
            base_temp=0.3,
            model=model,
            reasoning_effort=reasoning_effort
        )
        response = await self.client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert customer service analyst. Analyze conversations and suggest appropriate disposition codes.",
                },
                {"role": "user", "content": prompt},
            ],
            **api_kwargs
        )

        # Parse response
        response_text = response.choices[0].message.content
        latency_ms = int((time.time() - start_time) * 1000)

        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            logger.warning(
                "disposition_parsing_failed",
                conversation_id=str(conversation_id),
                response_text=response_text,
            )
            # Return default low-confidence suggestion
            result = {
                "suggestions": [
                    {
                        "code": "UNRESOLVED",
                        "label": "Issue Unresolved",
                        "confidence": 0.3,
                        "reasoning": "Unable to parse AI response",
                    }
                ]
            }

        # Log AI interaction (audit trail)
        await self.repository.save_ai_interaction(
            conversation_id=conversation_id,
            interaction_type="disposition",
            prompt_text=prompt,
            response_text=response_text,
            model_name=model,  # Use captured model to avoid race
            tokens_used=response.usage.total_tokens,
            cost_usd=self._calculate_cost(response.usage.total_tokens),
            latency_ms=latency_ms,
        )

        # Save suggestions to database (for analytics)
        suggestions = result.get("suggestions", [])
        if suggestions:
            await self.repository.save_disposition_suggestions(
                conversation_id=conversation_id,
                suggestions=[
                    {
                        **s,
                        "rank": idx + 1,
                    }
                    for idx, s in enumerate(suggestions[:3])  # Max 3
                ],
            )

        logger.info(
            "disposition_suggestions_generated",
            conversation_id=str(conversation_id),
            suggestion_count=len(suggestions),
            top_suggestion=suggestions[0]["code"] if suggestions else None,
            tokens=response.usage.total_tokens,
        )

        return result

    async def detect_compliance_items(
        self, conversation_id: UUID
    ) -> dict:
        """Detect compliance item completion from transcript.

        Analyzes transcript to determine which compliance items were completed
        by the agent. Logs interaction to ai_interactions and saves attempts
        to compliance_detection_attempts table.

        Args:
            conversation_id: Conversation UUID

        Returns:
            Dict with 'items' list containing label, detected (bool), confidence
        """
        # Capture model config atomically at the start to avoid race conditions
        # when model changes mid-operation
        model, reasoning_effort = self._get_current_model_config()

        start_time = time.time()

        # Get transcript
        lines = await self.repository.get_all_transcript_lines(conversation_id)
        if not lines:
            logger.warning(
                "compliance_detection_no_transcript",
                conversation_id=str(conversation_id),
            )
            return {"items": []}

        # Build transcript text (limit to last 50 lines for context)
        transcript_text = "\n".join(
            [f"{line.speaker}: {line.text}" for line in lines[-50:]]
        )

        # Build prompt
        items_list = "\n".join([f"- {item}" for item in COMPLIANCE_ITEMS])
        prompt = f"""Analyze this customer service transcript and determine which compliance items were completed by the agent.

Compliance checklist:
{items_list}

Transcript:
{transcript_text}

For each compliance item, determine:
1. Was it completed? (true/false)
2. Your confidence level (0.0 to 1.0)

Return JSON with this exact structure:
{{
  "items": [
    {{"label": "Item text", "detected": true, "confidence": 0.95}},
    ...
  ]
}}

Be strict: only mark as true if you have clear evidence in the transcript."""

        # Call OpenAI - use captured model config to prevent race conditions
        api_kwargs = self._build_api_kwargs(
            base_temp=0.2,
            model=model,
            reasoning_effort=reasoning_effort
        )
        response = await self.client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a compliance analyst. Review transcripts and identify completed compliance items.",
                },
                {"role": "user", "content": prompt},
            ],
            **api_kwargs
        )

        response_text = response.choices[0].message.content
        latency_ms = int((time.time() - start_time) * 1000)

        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            logger.warning(
                "compliance_parsing_failed",
                conversation_id=str(conversation_id),
                response_text=response_text,
            )
            result = {"items": []}

        # Log AI interaction
        await self.repository.save_ai_interaction(
            conversation_id=conversation_id,
            interaction_type="compliance",
            prompt_text=prompt,
            response_text=response_text,
            model_name=model,  # Use captured model to avoid race
            tokens_used=response.usage.total_tokens,
            cost_usd=self._calculate_cost(response.usage.total_tokens),
            latency_ms=latency_ms,
        )

        # Save compliance detection attempts (for analytics)
        items = result.get("items", [])
        if items:
            await self.repository.save_compliance_attempts(
                conversation_id=conversation_id,
                attempts=[
                    {
                        "item_label": item["label"],
                        "ai_detected": item["detected"],
                        "ai_confidence": item["confidence"],
                        "agent_override": False,  # Will be updated when agent saves ACW
                        "final_status": item["detected"],  # Default to AI detection
                    }
                    for item in items
                ],
            )

        logger.info(
            "compliance_items_detected",
            conversation_id=str(conversation_id),
            detected_count=sum(1 for item in items if item["detected"]),
            total_items=len(items),
            tokens=response.usage.total_tokens,
        )

        return result

    async def extract_crm_fields(
        self, conversation_id: UUID
    ) -> dict:
        """Extract structured CRM fields from transcript.

        Analyzes full transcript to extract Salesforce case fields with
        constrained taxonomies for Case Type and Priority. Logs interaction
        to ai_interactions and saves extractions to crm_field_extractions table.

        Args:
            conversation_id: Conversation UUID

        Returns:
            Dict with 'fields' list containing field_name, value, confidence
        """
        # Capture model config atomically at the start to avoid race conditions
        # when model changes mid-operation
        model, reasoning_effort = self._get_current_model_config()

        start_time = time.time()

        # Get full transcript (all lines)
        lines = await self.repository.get_all_transcript_lines(conversation_id)
        if not lines:
            logger.warning(
                "crm_extraction_no_transcript",
                conversation_id=str(conversation_id),
            )
            return {"fields": []}

        # Build full transcript text (use all lines for comprehensive extraction)
        transcript_text = "\n".join(
            [f"{line.speaker}: {line.text}" for line in lines]
        )

        # Build prompt with constrained taxonomies
        case_types = ", ".join(CASE_TYPE_VALUES)
        priorities = ", ".join(PRIORITY_VALUES)

        prompt = f"""Analyze this customer service conversation and extract structured CRM fields for a Salesforce case.

TRANSCRIPT:
{transcript_text}

Extract the following fields:

1. **{CRM_FIELD_NAMES['CASE_SUBJECT']}** (string, max 100 chars): A brief headline summarizing the interaction
2. **{CRM_FIELD_NAMES['CASE_TYPE']}** (must be one of: {case_types})
3. **{CRM_FIELD_NAMES['PRIORITY']}** (must be one of: {priorities})
4. **{CRM_FIELD_NAMES['ROOT_CAUSE']}** (string): The underlying reason for the customer's issue
5. **{CRM_FIELD_NAMES['RESOLUTION_ACTION']}** (string): What action the agent took to resolve the issue

IMPORTANT CONSTRAINTS:
- Case Type MUST be exactly one of: {case_types}
- Priority MUST be exactly one of: {priorities}
- Use "Other" for Case Type if none fit perfectly
- Base Priority on urgency and impact mentioned in conversation

Return JSON with this exact structure:
{{
  "fields": [
    {{"field_name": "Case Subject", "value": "Brief summary", "confidence": 0.95}},
    {{"field_name": "Case Type", "value": "Order Tracking", "confidence": 0.90}},
    {{"field_name": "Priority", "value": "High", "confidence": 0.85}},
    {{"field_name": "Root Cause", "value": "Description", "confidence": 0.88}},
    {{"field_name": "Resolution Action", "value": "Action taken", "confidence": 0.92}}
  ]
}}

Each field must include:
- field_name: Exact field name from list above
- value: Extracted value (constrained to taxonomy for Case Type and Priority)
- confidence: Float between 0.0 and 1.0

Be specific and factual. Extract actual numbers, order IDs, and details from the transcript."""

        # Call OpenAI - use captured model config to prevent race conditions
        api_kwargs = self._build_api_kwargs(
            base_temp=0.2,
            model=model,
            reasoning_effort=reasoning_effort
        )
        response = await self.client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a CRM data extraction specialist. Extract structured fields from customer service conversations following strict taxonomies.",
                },
                {"role": "user", "content": prompt},
            ],
            **api_kwargs
        )

        response_text = response.choices[0].message.content
        latency_ms = int((time.time() - start_time) * 1000)

        try:
            result = json.loads(response_text)

            # Validate taxonomy constraints
            fields = result.get("fields", [])
            for field in fields:
                field_name = field.get("field_name")
                value = field.get("value")

                # Validate Case Type against taxonomy
                if field_name == CRM_FIELD_NAMES['CASE_TYPE'] and value not in CASE_TYPE_VALUES:
                    logger.warning(
                        "crm_invalid_case_type",
                        conversation_id=str(conversation_id),
                        extracted_value=value,
                        valid_values=CASE_TYPE_VALUES,
                    )
                    field["value"] = "Other"  # Fallback to Other
                    field["confidence"] = max(0.5, field.get("confidence", 0.5) - 0.2)

                # Validate Priority against taxonomy
                if field_name == CRM_FIELD_NAMES['PRIORITY'] and value not in PRIORITY_VALUES:
                    logger.warning(
                        "crm_invalid_priority",
                        conversation_id=str(conversation_id),
                        extracted_value=value,
                        valid_values=PRIORITY_VALUES,
                    )
                    field["value"] = "Medium"  # Fallback to Medium
                    field["confidence"] = max(0.5, field.get("confidence", 0.5) - 0.2)

        except json.JSONDecodeError:
            logger.warning(
                "crm_extraction_parsing_failed",
                conversation_id=str(conversation_id),
                response_text=response_text,
            )
            result = {"fields": []}

        # Log AI interaction
        await self.repository.save_ai_interaction(
            conversation_id=conversation_id,
            interaction_type="crm_extraction",
            prompt_text=prompt,
            response_text=response_text,
            model_name=model,  # Use captured model to avoid race
            tokens_used=response.usage.total_tokens,
            cost_usd=self._calculate_cost(response.usage.total_tokens),
            latency_ms=latency_ms,
        )

        # Save CRM field extractions (for audit trail)
        fields = result.get("fields", [])
        if fields:
            await self.repository.save_crm_fields(
                conversation_id=conversation_id,
                fields=[
                    {
                        "field_name": field["field_name"],
                        "extracted_value": field["value"],
                        "source": "AI",  # AI-extracted
                        "confidence": field["confidence"],
                    }
                    for field in fields
                ],
            )

        logger.info(
            "crm_fields_extracted",
            conversation_id=str(conversation_id),
            field_count=len(fields),
            tokens=response.usage.total_tokens,
        )

        return result

    def _calculate_cost(self, tokens: int) -> float:
        """Calculate OpenAI API cost using shared utility.

        Args:
            tokens: Total tokens used

        Returns:
            Cost in USD
        """
        from app.utils.cost import estimate_cost
        return estimate_cost(tokens)
