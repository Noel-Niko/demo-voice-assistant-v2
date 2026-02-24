"""Data Export Service - Generate tmp files for developer review.

Exports complete conversation data to JSON files for review before
migrating to production analytics (Snowflake/Aurora).
"""
import json
import os
from datetime import datetime
from typing import Dict, Any

import structlog

from app.repositories.conversation_repository import ConversationRepository

logger = structlog.get_logger(__name__)


class DataExportService:
    """Service for exporting conversation data to tmp files."""

    def __init__(self, repository: ConversationRepository):
        """Initialize export service.

        Args:
            repository: Conversation repository for data access
        """
        self.repository = repository

    async def export_conversation_data(self, conversation_id: str) -> str:
        """Generate tmp JSON file with all conversation data for review.

        Exports comprehensive data including:
        - Conversation metadata
        - Transcript statistics
        - All summaries
        - Agent interactions (MCP queries, ratings, edits)
        - AI interactions (LLM calls, costs, tokens)
        - Metrics summary (query counts, ratings, costs)

        Args:
            conversation_id: UUID of conversation to export

        Returns:
            Path to generated tmp file

        Example:
            >>> service = DataExportService(repo)
            >>> path = await service.export_conversation_data("abc-123")
            >>> print(path)
            /tmp/conversation_data_abc-123_20260221_153045.json
        """
        logger.info("data_export_start", conversation_id=conversation_id)

        # Gather all data from repository
        conversation = await self.repository.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        summaries = await self.repository.get_all_summaries(conversation_id)
        agent_interactions = await self.repository.get_agent_interactions(conversation_id)
        ai_interactions = await self.repository.get_ai_interactions(conversation_id)
        compliance_attempts = await self.repository.get_compliance_attempts(conversation_id)
        content_edits = await self.repository.get_content_edits(conversation_id)
        disposition_suggestions = await self.repository.get_disposition_suggestions(conversation_id)
        listening_sessions = await self.repository.get_listening_mode_sessions(conversation_id)
        crm_extractions = await self.repository.get_crm_field_extractions(conversation_id)

        # Build comprehensive export data
        data = {
            "export_metadata": {
                "exported_at": datetime.now().isoformat(),
                "conversation_id": conversation_id,
                "format_version": "2.0"
            },
            "conversation": {
                "id": conversation_id,
                "agent_id": conversation.agent_id,
                "customer_id": conversation.customer_id,
                "recording_id": conversation.recording_id,
                "queue_name": conversation.queue_name,
                "interaction_id": conversation.interaction_id,
                "status": conversation.status,
                "started_at": conversation.started_at.isoformat() if conversation.started_at else None,
                "ended_at": conversation.ended_at.isoformat() if conversation.ended_at else None,
                "disposition_code": conversation.disposition_code,
                "wrap_up_notes": conversation.wrap_up_notes,
                "agent_feedback": conversation.agent_feedback,
                "acw_duration_secs": conversation.acw_duration_secs
            },
            "transcript": {
                "line_count": len(conversation.transcript_lines) if conversation.transcript_lines else 0,
                "word_count": sum(
                    len(line.text.split())
                    for line in conversation.transcript_lines
                ) if conversation.transcript_lines else 0,
                "duration_secs": (
                    (conversation.ended_at - conversation.started_at).total_seconds()
                    if conversation.ended_at and conversation.started_at
                    else None
                )
            },
            "summaries": [
                {
                    "version": s.version,
                    "generated_at": s.generated_at.isoformat() if s.generated_at else None,
                    "summary_text": s.summary_text,
                    "transcript_line_count": s.transcript_line_count
                }
                for s in summaries
            ] if summaries else [],
            "agent_interactions": [
                {
                    "interaction_type": i.interaction_type,
                    "timestamp": i.timestamp.isoformat() if i.timestamp else None,
                    "query_text": i.query_text,
                    "llm_request": self._parse_json_or_text(i.llm_request),
                    "llm_response": self._parse_json_or_text(i.llm_response),
                    "mcp_request": self._parse_json_or_text(i.mcp_request),
                    "mcp_response": self._parse_json_or_text(i.mcp_response),
                    "user_rating": i.user_rating,
                    "manually_edited": i.manually_edited,
                    "edit_details": self._parse_json_or_text(i.edit_details),
                    "context_data": self._parse_json_or_text(i.context_data)
                }
                for i in agent_interactions
            ] if agent_interactions else [],
            "ai_calls": [
                {
                    "interaction_type": ai.interaction_type,
                    "model_name": ai.model_name,
                    "prompt": ai.prompt_text[:500] if ai.prompt_text else None,  # Truncate for readability
                    "response": ai.response_text[:500] if ai.response_text else None,
                    "tokens_used": ai.tokens_used,
                    "cost_usd": ai.cost_usd,
                    "latency_ms": ai.latency_ms,
                    "agent_edited": ai.agent_edited,
                    "created_at": ai.created_at.isoformat() if ai.created_at else None
                }
                for ai in ai_interactions
            ] if ai_interactions else [],
            "compliance_detection_attempts": [
                {
                    "item_label": a.item_label,
                    "ai_detected": a.ai_detected,
                    "ai_confidence": a.ai_confidence,
                    "agent_override": a.agent_override,
                    "final_status": a.final_status,
                    "detected_at": a.detected_at.isoformat() if a.detected_at else None,
                }
                for a in compliance_attempts
            ] if compliance_attempts else [],
            "content_edits": [
                {
                    "field_name": e.field_name,
                    "original_value": e.original_value[:200] if e.original_value else None,
                    "edited_value": e.edited_value[:200] if e.edited_value else None,
                    "edit_type": e.edit_type,
                    "edited_at": e.edited_at.isoformat() if e.edited_at else None,
                    "agent_id": e.agent_id,
                }
                for e in content_edits
            ] if content_edits else [],
            "disposition_suggestions": [
                {
                    "suggested_code": d.suggested_code,
                    "suggested_label": d.suggested_label,
                    "confidence": d.confidence,
                    "reasoning": d.reasoning[:200] if d.reasoning else None,
                    "rank": d.rank,
                    "was_selected": d.was_selected,
                }
                for d in disposition_suggestions
            ] if disposition_suggestions else [],
            "listening_mode_sessions": [
                {
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                    "auto_queries_count": s.auto_queries_count,
                    "opportunities_detected": s.opportunities_detected,
                    "products_suggested": self._parse_json_or_text(s.products_suggested),
                    "orders_tracked": self._parse_json_or_text(s.orders_tracked),
                    "duration_secs": (
                        (s.ended_at - s.started_at).total_seconds()
                        if s.ended_at and s.started_at else None
                    ),
                }
                for s in listening_sessions
            ] if listening_sessions else [],
            "crm_extractions": [
                {
                    "field_name": c.field_name,
                    "extracted_value": c.extracted_value,
                    "source": c.source,
                    "confidence": c.confidence,
                    "extracted_at": c.extracted_at.isoformat() if c.extracted_at else None,
                }
                for c in crm_extractions
            ] if crm_extractions else [],
            "metrics": self._calculate_metrics(agent_interactions, ai_interactions)
        }

        # Write to tmp file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        tmp_file = f"/tmp/conversation_data_{conversation_id}_{timestamp}.json"

        with open(tmp_file, 'w') as f:
            json.dump(data, f, indent=2)

        file_size = os.path.getsize(tmp_file)
        logger.info(
            "data_export_complete",
            file=tmp_file,
            size_bytes=file_size,
            size_kb=round(file_size / 1024, 2)
        )

        return tmp_file

    def _parse_json_or_text(self, value: str | None) -> Any:
        """Parse JSON string or return as text.

        Args:
            value: JSON string or plain text

        Returns:
            Parsed JSON object or original text
        """
        if not value:
            return None

        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    def _calculate_metrics(
        self,
        agent_interactions: list,
        ai_interactions: list
    ) -> Dict[str, Any]:
        """Calculate summary metrics from interactions.

        Args:
            agent_interactions: List of agent interaction records
            ai_interactions: List of AI interaction records

        Returns:
            Dictionary of calculated metrics
        """
        metrics = {
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

        # Calculate agent interaction metrics
        if agent_interactions:
            for interaction in agent_interactions:
                if interaction.interaction_type == 'manual_query':
                    metrics["mcp_queries"]["manual_count"] += 1
                elif interaction.interaction_type == 'mcp_query_auto':
                    metrics["mcp_queries"]["auto_count"] += 1

                if interaction.user_rating == 'up':
                    metrics["mcp_queries"]["rated_up"] += 1
                elif interaction.user_rating == 'down':
                    metrics["mcp_queries"]["rated_down"] += 1

                if interaction.manually_edited:
                    if interaction.interaction_type == 'summary_edited':
                        metrics["edits"]["summaries_edited"] += 1
                    else:
                        metrics["edits"]["suggestions_edited"] += 1
                    metrics["edits"]["total_edits"] += 1

            metrics["mcp_queries"]["total_count"] = (
                metrics["mcp_queries"]["manual_count"] +
                metrics["mcp_queries"]["auto_count"]
            )
            metrics["mcp_queries"]["unrated"] = (
                metrics["mcp_queries"]["total_count"] -
                metrics["mcp_queries"]["rated_up"] -
                metrics["mcp_queries"]["rated_down"]
            )

        # Calculate AI cost metrics
        if ai_interactions:
            metrics["ai_costs"]["call_count"] = len(ai_interactions)
            metrics["ai_costs"]["total_tokens"] = sum(
                ai.tokens_used for ai in ai_interactions
            )
            metrics["ai_costs"]["total_cost_usd"] = sum(
                ai.cost_usd for ai in ai_interactions
            )
            metrics["ai_costs"]["avg_tokens_per_call"] = (
                metrics["ai_costs"]["total_tokens"] // metrics["ai_costs"]["call_count"]
                if metrics["ai_costs"]["call_count"] > 0
                else 0
            )

            # Model breakdown aggregation
            model_breakdown: Dict[str, Any] = {}
            type_breakdown: Dict[str, Any] = {}
            for ai in ai_interactions:
                model = ai.model_name or "unknown"
                if model not in model_breakdown:
                    model_breakdown[model] = {
                        "call_count": 0,
                        "total_tokens": 0,
                        "total_cost_usd": 0.0,
                        "total_latency_ms": 0,
                    }
                model_breakdown[model]["call_count"] += 1
                model_breakdown[model]["total_tokens"] += ai.tokens_used
                model_breakdown[model]["total_cost_usd"] += ai.cost_usd
                model_breakdown[model]["total_latency_ms"] += ai.latency_ms

                itype = ai.interaction_type or "unknown"
                if itype not in type_breakdown:
                    type_breakdown[itype] = {
                        "call_count": 0,
                        "total_cost_usd": 0.0,
                        "total_tokens": 0,
                    }
                type_breakdown[itype]["call_count"] += 1
                type_breakdown[itype]["total_cost_usd"] += ai.cost_usd
                type_breakdown[itype]["total_tokens"] += ai.tokens_used

            for stats in model_breakdown.values():
                total_latency = stats.pop("total_latency_ms")
                stats["avg_latency_ms"] = (
                    total_latency // stats["call_count"]
                    if stats["call_count"] > 0 else 0
                )

            metrics["ai_costs_by_model"] = model_breakdown
            metrics["ai_costs_by_type"] = type_breakdown

        return metrics
