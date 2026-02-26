"""REST API routes for conversation management.

Provides HTTP endpoints for creating and retrieving conversations.
"""
from datetime import datetime, timezone
from uuid import UUID
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_conversation_manager, get_summary_generator, get_acw_service, get_mcp_client, get_mcp_orchestrator, get_repository, get_listening_mode_manager, get_model_manager, get_data_export_service
from app.services.data_export_service import DataExportService
from app.services.conversation_manager import ConversationManager
from app.services.summary_generator import SummaryGenerator
from app.services.acw_service import ACWService
from app.services.mcp_client import MCPClient
from app.services.mcp_orchestrator import MCPOrchestrator
from app.services.listening_mode_manager import ListeningModeManager
from app.services.model_manager import ModelManager
from app.repositories.conversation_repository import ConversationRepository
from app.models.schemas import (
    ConversationCreateResponse,
    ConversationStateResponse,
    HealthCheckResponse,
    ACWCompleteRequest,
    ACWCompleteResponse,
    DispositionSuggestionsResponse,
    ComplianceDetectionResponse,
    CRMFieldsResponse,
    MCPQueryRequest,
    MCPQueryResponse,
    MCPSuggestionSchema,
    InteractionMetricsResponse,
    ListeningModeStartResponse,
    ListeningModeStopResponse,
    ListeningModeStatusResponse,
    ModelPresetSchema,
    ModelConfigResponse,
    ModelChangeRequest,
    ModelChangeResponse,
    SuggestionRatingRequest,
    SuggestionRatingResponse,
)

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api")


# ===== FCR (First Call Resolution) Calculation =====

# Import disposition codes from constants (single source of truth)
from app.constants import RESOLUTION_DISPOSITION_CODES

# Legacy alias for backwards compatibility with tests
RESOLUTION_DISPOSITIONS = RESOLUTION_DISPOSITION_CODES


def calculate_fcr(disposition_code: str | None) -> bool | None:
    """Calculate First Call Resolution from disposition code.

    FCR indicates whether the customer's issue was resolved on the first contact.
    This is a standard contact center metric used for agent performance reporting.

    Note: This simplified calculation does NOT account for inbound transfers.
    In production environments, FCR calculation should also check whether the
    call was transferred TO this agent from another department/agent, as that
    would typically disqualify it from being counted as first-call resolution.

    Args:
        disposition_code: Disposition code selected by agent (e.g., 'RESOLVED', 'ESCALATED')
                         Can be None if disposition not yet selected.

    Returns:
        True if disposition indicates resolution, False if not resolved, None if no disposition

    Examples:
        >>> calculate_fcr("RESOLVED")
        True
        >>> calculate_fcr("ESCALATED")
        False
        >>> calculate_fcr(None)
        None
    """
    if disposition_code is None or disposition_code == "":
        return None

    return disposition_code in RESOLUTION_DISPOSITIONS


@router.get("/dispositions")
async def get_disposition_codes() -> dict:
    """Return fixed disposition code taxonomy for agent selection.

    Returns all available disposition codes that agents can select during ACW.
    This is a static list (no AI involvement) that does not vary by conversation.

    Disposition codes are organized by category:
    - RESOLVED: Issue resolved on first contact (FCR = Yes)
    - PENDING: Requires follow-up (FCR = No)
    - ESCALATED: Transferred to another team (FCR = No)
    - NO_RESOLUTION: Could not resolve (FCR = No)

    Returns:
        dict: {
            "dispositions": List of disposition code objects with metadata,
            "version": "1.0"  # For future taxonomy updates
        }

    Example:
        GET /api/dispositions
        Response: {
            "dispositions": [
                {
                    "code": "RESOLVED",
                    "label": "Issue Resolved",
                    "category": "RESOLVED",
                    "fcr_eligible": true,
                    "description": "Customer issue fully resolved on first contact"
                },
                ...
            ],
            "version": "1.0"
        }
    """
    from app.constants import DISPOSITION_CODES

    return {
        "dispositions": DISPOSITION_CODES,
        "version": "1.0",
    }


# ===== Model Selection Endpoints =====


@router.get("/model", response_model=ModelConfigResponse)
async def get_model_config(
    model_manager: ModelManager = Depends(get_model_manager),
) -> ModelConfigResponse:
    """Get current LLM model configuration and available presets.

    Returns the currently active model and all available model presets
    that can be selected via PUT /api/model.

    Returns:
        ModelConfigResponse with current model and all presets

    Example:
        GET /api/model
        Response: {
            "current_model_id": "gpt-4.1-mini",
            "current": { ... },
            "available": [ ... ]
        }
    """
    current_preset = model_manager.get_current_preset()
    all_presets = model_manager.list_presets()

    return ModelConfigResponse(
        current_model_id=model_manager.current_model_id,
        current=ModelPresetSchema(
            model_id=current_preset.model_id,
            model_name=current_preset.model_name,
            display_name=current_preset.display_name,
            reasoning_effort=current_preset.reasoning_effort,
            description=current_preset.description,
        ),
        available=[
            ModelPresetSchema(
                model_id=p.model_id,
                model_name=p.model_name,
                display_name=p.display_name,
                reasoning_effort=p.reasoning_effort,
                description=p.description,
            )
            for p in all_presets
        ],
    )


@router.put("/model", response_model=ModelChangeResponse)
async def change_model(
    request: ModelChangeRequest,
    model_manager: ModelManager = Depends(get_model_manager),
) -> ModelChangeResponse:
    """Switch the global LLM model for all services.

    Changes the model used by summary generation, ACW features,
    opportunity detection, and MCP orchestration. Takes effect
    immediately without restart.

    Args:
        request: ModelChangeRequest with model_id to switch to

    Returns:
        ModelChangeResponse confirming the change

    Raises:
        HTTPException: 400 if model_id is invalid

    Example:
        PUT /api/model
        Body: {"model_id": "gpt-4o"}
        Response: {"status": "updated", "model_id": "gpt-4o", "display_name": "GPT-4o"}
    """
    try:
        model_manager.set_model(request.model_id)

        preset = model_manager.get_current_preset()

        logger.info(
            "model_changed_via_api",
            model_id=request.model_id,
            display_name=preset.display_name,
        )

        return ModelChangeResponse(
            status="updated",
            model_id=model_manager.current_model_id,
            display_name=preset.display_name,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/conversations", response_model=ConversationCreateResponse)
async def create_conversation(
    manager: ConversationManager = Depends(get_conversation_manager),
) -> ConversationCreateResponse:
    """Create a new conversation and start transcript streaming.

    Returns:
        ConversationCreateResponse with conversation_id, status, and started_at

    Example:
        POST /api/conversations
        Response: {
            "conversation_id": "uuid",
            "status": "active",
            "started_at": "2026-02-19T10:00:00"
        }
    """
    try:
        conversation_id = await manager.start_conversation()

        logger.info(
            "conversation_created_via_api",
            conversation_id=str(conversation_id),
        )

        # Get conversation details
        conversation_state = await manager.get_conversation_state(conversation_id)

        if not conversation_state:
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve created conversation",
            )

        return ConversationCreateResponse(
            conversation_id=conversation_state.conversation_id,
            status=conversation_state.status,
            started_at=conversation_state.started_at,
        )

    except Exception as e:
        logger.error(
            "conversation_creation_failed",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create conversation: {str(e)}",
        )


@router.get("/conversations/{conversation_id}", response_model=ConversationStateResponse)
async def get_conversation(
    conversation_id: UUID,
    manager: ConversationManager = Depends(get_conversation_manager),
) -> ConversationStateResponse:
    """Get current state of conversation.

    Args:
        conversation_id: UUID of conversation to retrieve

    Returns:
        ConversationStateResponse with full conversation data

    Raises:
        HTTPException: 404 if conversation not found

    Example:
        GET /api/conversations/{uuid}
        Response: {
            "conversation_id": "uuid",
            "status": "active",
            "transcript_lines": [...],
            "summaries": [...]
        }
    """
    try:
        conversation_state = await manager.get_conversation_state(conversation_id)

        if not conversation_state:
            raise HTTPException(
                status_code=404,
                detail=f"Conversation {conversation_id} not found",
            )

        return conversation_state

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "conversation_retrieval_failed",
            conversation_id=str(conversation_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve conversation: {str(e)}",
        )


@router.get("/conversations/{conversation_id}/metrics", response_model=InteractionMetricsResponse)
async def get_interaction_metrics(
    conversation_id: UUID,
    repository: ConversationRepository = Depends(get_repository),
) -> InteractionMetricsResponse:
    """Get aggregated interaction metrics for conversation.

    Args:
        conversation_id: UUID of conversation

    Returns:
        InteractionMetricsResponse with aggregated metrics

    Example:
        GET /api/conversations/{uuid}/metrics
        Response: {
            "manual_queries": 5,
            "auto_queries": 3,
            "listening_mode_active": true,
            "total_opportunities": 8,
            "summary_ratings": {"up": 2, "down": 0},
            "summary_edits": 1
        }
    """
    try:
        # Get all agent interactions for this conversation
        interactions = await repository.get_agent_interactions(conversation_id)

        # Aggregate metrics
        manual_queries = sum(1 for i in interactions if i.interaction_type == "manual_query")
        auto_queries = sum(1 for i in interactions if i.interaction_type == "mcp_query_auto")
        summary_ratings_up = sum(1 for i in interactions if i.user_rating == "up")
        summary_ratings_down = sum(1 for i in interactions if i.user_rating == "down")
        summary_edits = sum(1 for i in interactions if i.interaction_type == "summary_edited" and i.manually_edited)

        # Check if listening mode is active
        listening_session = await repository.get_active_listening_mode_session(conversation_id)
        listening_mode_active = listening_session is not None

        total_opportunities = listening_session.opportunities_detected if listening_session else 0

        return InteractionMetricsResponse(
            manual_queries=manual_queries,
            auto_queries=auto_queries,
            listening_mode_active=listening_mode_active,
            total_opportunities=total_opportunities,
            summary_ratings={"up": summary_ratings_up, "down": summary_ratings_down},
            summary_edits=summary_edits,
        )

    except Exception as e:
        logger.error(
            "metrics_retrieval_failed",
            conversation_id=str(conversation_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve metrics: {str(e)}",
        )


@router.put("/conversations/{conversation_id}/summary-interval")
async def update_summary_interval(
    conversation_id: UUID,
    interval_seconds: int,
    manager: ConversationManager = Depends(get_conversation_manager),
    summary_generator: SummaryGenerator = Depends(get_summary_generator),
    repository: ConversationRepository = Depends(get_repository),
) -> dict:
    """Update the summary generation interval for a conversation.

    Args:
        conversation_id: UUID of conversation
        interval_seconds: New interval in seconds (5-120)

    Returns:
        Confirmation message

    Example:
        PUT /api/conversations/{uuid}/summary-interval?interval_seconds=15
        Response: {"status": "updated", "interval": 15}
    """
    if interval_seconds < 5 or interval_seconds > 120:
        raise HTTPException(
            status_code=400,
            detail="Interval must be between 5 and 120 seconds",
        )

    try:
        # Verify conversation exists
        conversation = await manager.get_conversation_state(conversation_id)
        if not conversation:
            raise HTTPException(
                status_code=404,
                detail=f"Conversation {conversation_id} not found",
            )

        # Persist interval to database
        await repository.update_summary_interval(conversation_id, interval_seconds)

        # Update in-memory cache
        summary_generator.set_interval(conversation_id, interval_seconds)

        logger.info(
            "summary_interval_updated",
            conversation_id=str(conversation_id),
            interval_seconds=interval_seconds,
        )

        return {
            "status": "updated",
            "interval": interval_seconds,
            "conversation_id": str(conversation_id),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "summary_interval_update_failed",
            conversation_id=str(conversation_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update summary interval: {str(e)}",
        )


@router.put("/conversations/{conversation_id}/complete", response_model=ACWCompleteResponse)
async def complete_conversation(
    conversation_id: UUID,
    acw_data: ACWCompleteRequest,
    request: Request,
    manager: ConversationManager = Depends(get_conversation_manager),
) -> ACWCompleteResponse:
    """Complete conversation with ACW (After-Call Work) data.

    Saves disposition, wrap-up notes, compliance checklist, CRM fields,
    and marks the conversation as completed.

    Args:
        conversation_id: UUID of conversation to complete
        acw_data: ACW data including disposition, notes, checklist, etc.

    Returns:
        ACWCompleteResponse with updated conversation state

    Raises:
        HTTPException: 404 if conversation not found

    Example:
        PUT /api/conversations/{uuid}/complete
        Body: {
            "disposition_code": "RESOLVED",
            "wrap_up_notes": "Customer satisfied",
            "agent_feedback": "up",
            "compliance_checklist": [...],
            "crm_fields": [...]
        }
        Response: {
            "conversation_id": "uuid",
            "status": "completed",
            "ended_at": "2026-02-20T...",
            ...
        }
    """
    try:
        # Convert request schemas to dicts for repository
        compliance_checklist = None
        if acw_data.compliance_checklist:
            compliance_checklist = [
                {
                    "label": item.label,
                    "checked": item.checked,
                    "auto_detected": item.auto_detected,
                }
                for item in acw_data.compliance_checklist
            ]

        crm_fields = None
        if acw_data.crm_fields:
            crm_fields = [
                {
                    "field_name": field.field_name,
                    "extracted_value": field.extracted_value,
                    "source": field.source,
                    "confidence": field.confidence,
                }
                for field in acw_data.crm_fields
            ]

        # Calculate FCR from disposition code
        fcr = calculate_fcr(acw_data.disposition_code)

        # Complete conversation
        conversation_state = await manager.complete_conversation(
            conversation_id=conversation_id,
            disposition_code=acw_data.disposition_code,
            wrap_up_notes=acw_data.wrap_up_notes,
            agent_feedback=acw_data.agent_feedback,
            acw_duration_secs=acw_data.acw_duration_secs,
            compliance_checklist=compliance_checklist,
            crm_fields=crm_fields,
        )

        if not conversation_state:
            raise HTTPException(
                status_code=404,
                detail=f"Conversation {conversation_id} not found",
            )

        logger.info(
            "conversation_completed_via_api",
            conversation_id=str(conversation_id),
            disposition_code=acw_data.disposition_code,
        )

        # Export conversation data for dashboard (fire-and-forget)
        try:
            export_service = request.app.state.data_export_service
            export_path = await export_service.export_conversation_data(str(conversation_id))
            logger.info("data_export_on_complete", path=export_path)
        except Exception as export_err:
            logger.warning("data_export_failed", error=str(export_err))

        # Return ACWCompleteResponse
        return ACWCompleteResponse(
            conversation_id=conversation_state.conversation_id,
            status=conversation_state.status,
            started_at=conversation_state.started_at,
            ended_at=conversation_state.ended_at,
            disposition_code=conversation_state.disposition_code,
            wrap_up_notes=conversation_state.wrap_up_notes,
            agent_feedback=conversation_state.agent_feedback,
            acw_duration_secs=conversation_state.acw_duration_secs,
            fcr=fcr,
            compliance_results=conversation_state.compliance_results,
            crm_field_extractions=conversation_state.crm_field_extractions,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "conversation_completion_failed",
            conversation_id=str(conversation_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to complete conversation: {str(e)}",
        )


@router.get(
    "/conversations/{conversation_id}/disposition-suggestions",
    response_model=DispositionSuggestionsResponse,
)
async def get_disposition_suggestions(
    conversation_id: UUID,
    acw_service: ACWService = Depends(get_acw_service),
) -> DispositionSuggestionsResponse:
    """Get AI-generated disposition code suggestions.

    Analyzes the conversation summary and transcript to suggest appropriate
    disposition codes with confidence scores. Useful for ACW phase.

    Args:
        conversation_id: UUID of conversation
        acw_service: ACW service dependency

    Returns:
        DispositionSuggestionsResponse with ranked suggestions

    Raises:
        HTTPException: 500 if generation fails

    Example:
        GET /api/conversations/{uuid}/disposition-suggestions
        Response: {
            "conversation_id": "uuid",
            "suggestions": [
                {
                    "code": "RESOLVED",
                    "label": "Issue Resolved",
                    "confidence": 0.95,
                    "reasoning": "Customer satisfied with resolution"
                }
            ]
        }
    """
    try:
        result = await acw_service.generate_disposition_suggestions(conversation_id)

        return DispositionSuggestionsResponse(
            conversation_id=str(conversation_id),
            suggestions=result["suggestions"],
        )

    except Exception as e:
        logger.error(
            "disposition_suggestion_failed",
            conversation_id=str(conversation_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate disposition suggestions: {str(e)}",
        )


@router.get(
    "/conversations/{conversation_id}/compliance-check",
    response_model=ComplianceDetectionResponse,
)
async def get_compliance_detection(
    conversation_id: UUID,
    acw_service: ACWService = Depends(get_acw_service),
) -> ComplianceDetectionResponse:
    """Get AI-detected compliance items.

    Analyzes the conversation transcript to detect which compliance items
    were completed by the agent. Useful for ACW phase quality assurance.

    Args:
        conversation_id: UUID of conversation
        acw_service: ACW service dependency

    Returns:
        ComplianceDetectionResponse with detected items

    Raises:
        HTTPException: 500 if detection fails

    Example:
        GET /api/conversations/{uuid}/compliance-check
        Response: {
            "conversation_id": "uuid",
            "items": [
                {
                    "label": "Verified customer identity",
                    "detected": true,
                    "confidence": 0.95
                }
            ]
        }
    """
    try:
        result = await acw_service.detect_compliance_items(conversation_id)

        return ComplianceDetectionResponse(
            conversation_id=str(conversation_id),
            items=result["items"],
        )

    except Exception as e:
        logger.error(
            "compliance_detection_failed",
            conversation_id=str(conversation_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to detect compliance items: {str(e)}",
        )


@router.get(
    "/conversations/{conversation_id}/crm-fields",
    response_model=CRMFieldsResponse,
)
async def get_crm_fields(
    conversation_id: UUID,
    acw_service: ACWService = Depends(get_acw_service),
) -> CRMFieldsResponse:
    """Get AI-extracted CRM fields.

    Analyzes the full conversation transcript to extract structured
    Salesforce case fields with taxonomy constraints. Useful for ACW phase
    to pre-populate CRM fields.

    Args:
        conversation_id: UUID of conversation
        acw_service: ACW service dependency

    Returns:
        CRMFieldsResponse with extracted fields and confidence scores

    Raises:
        HTTPException: 500 if extraction fails

    Example:
        GET /api/conversations/{uuid}/crm-fields
        Response: {
            "conversation_id": "uuid",
            "fields": [
                {
                    "field_name": "Case Subject",
                    "value": "Order tracking inquiry for order 771903",
                    "confidence": 0.95
                },
                {
                    "field_name": "Case Type",
                    "value": "Order Tracking",
                    "confidence": 0.98
                },
                {
                    "field_name": "Priority",
                    "value": "High",
                    "confidence": 0.85
                }
            ]
        }
    """
    try:
        result = await acw_service.extract_crm_fields(conversation_id)

        return CRMFieldsResponse(
            conversation_id=str(conversation_id),
            fields=result["fields"],
        )

    except Exception as e:
        logger.error(
            "crm_extraction_failed",
            conversation_id=str(conversation_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to extract CRM fields: {str(e)}",
        )


@router.post("/mcp/query")
async def mcp_query(
    request: MCPQueryRequest,
    orchestrator: MCPOrchestrator = Depends(get_mcp_orchestrator),
    repository: ConversationRepository = Depends(get_repository),
) -> StreamingResponse:
    """Query MCP server using LLM-driven dynamic tool discovery and execution.

    This endpoint implements the proper MCP (Model Context Protocol) pattern:
    1. Discovers available tools dynamically via MCP protocol
    2. Uses LLM (GPT-3.5-turbo) to select the most appropriate tool
    3. LLM generates correct arguments based on tool's inputSchema
    4. Executes the tool call and returns results

    No hardcoded tools or arguments - fully dynamic!

    Args:
        request: MCP query request with user's natural language query
        orchestrator: MCP orchestrator for LLM-driven tool selection

    Returns:
        MCPQueryResponse with suggestions and metadata (streamed via SSE)

    Raises:
        HTTPException: 503 if MCP not available, 500 if query fails

    Example:
        POST /api/mcp/query
        Body: {
            "query": "recommend a ladder for industrial use",
            "preferred_server": null
        }
        Response: Stream of SSE events with progress updates
    """
    async def generate_sse_stream():
        """Generate Server-Sent Events stream with real-time progress updates."""
        progress_queue: asyncio.Queue = asyncio.Queue()
        orchestration_complete = asyncio.Event()
        orchestration_result = None
        orchestration_error = None

        def progress_callback(message: str):
            """Callback to capture progress messages and stream immediately."""
            # Use asyncio.create_task for thread-safe queue insertion
            asyncio.create_task(progress_queue.put(message))

        try:
            logger.info("mcp_query_start_with_llm", query=request.query[:100])

            # Set progress callback on orchestrator
            orchestrator.set_progress_callback(progress_callback)

            # Run orchestrator query in background task
            async def run_query():
                nonlocal orchestration_result, orchestration_error
                try:
                    orchestration_result = await orchestrator.query(
                        user_query=request.query,
                        preferred_server=request.preferred_server
                    )
                except Exception as e:
                    orchestration_error = e
                finally:
                    orchestration_complete.set()

            query_task = asyncio.create_task(run_query())

            # Stream progress messages as they arrive
            while not orchestration_complete.is_set():
                try:
                    # Wait for next progress message with timeout
                    progress = await asyncio.wait_for(progress_queue.get(), timeout=0.1)
                    event_data = json.dumps({"type": "progress", "message": progress})
                    yield f"data: {event_data}\n\n"
                except asyncio.TimeoutError:
                    # No progress message, continue waiting
                    await asyncio.sleep(0.05)

            # Drain any remaining progress messages
            while not progress_queue.empty():
                try:
                    progress = progress_queue.get_nowait()
                    event_data = json.dumps({"type": "progress", "message": progress})
                    yield f"data: {event_data}\n\n"
                except asyncio.QueueEmpty:
                    break

            # Ensure query task completed
            await query_task

            # Check for orchestration errors
            if orchestration_error:
                raise orchestration_error

            # Parse MCP result to suggestions
            result = orchestration_result["result"]
            server_path = orchestration_result["server_path"]
            tool_name = orchestration_result["tool_name"]

            logger.info(
                "mcp_orchestration_complete",
                server_path=server_path,
                tool_name=tool_name,
                query=request.query[:50]
            )

            suggestions = []
            if isinstance(result, dict) and "content" in result:
                # MCP returns {"content": [...]} format
                for item in result.get("content", []):
                    if isinstance(item, dict):
                        # Extract text content
                        text_content = item.get("text", item.get("content", ""))

                        suggestions.append(
                            {
                                "title": item.get("title", "MCP Result"),
                                "content": text_content if isinstance(text_content, str) else str(text_content),
                                "source": item.get("url", item.get("source")),
                                "relevance": item.get("score", 1.0),
                            }
                        )

            logger.info(
                "mcp_query_completed",
                query=request.query,
                server_path=server_path,
                tool_name=tool_name,
                suggestion_count=len(suggestions),
            )

            # Save manual query interaction for dashboard metrics (fire-and-forget)
            interaction_id = None
            try:
                interaction_id = await repository.save_agent_interaction(
                    conversation_id=request.conversation_id,
                    interaction_type="manual_query",
                    query_text=request.query,
                    mcp_request=json.dumps({
                        "query": request.query,
                        "preferred_server": request.preferred_server,
                    }),
                    mcp_response=json.dumps({
                        "server_path": server_path,
                        "tool_name": tool_name,
                        "suggestion_count": len(suggestions),
                        "result": result,
                    }),
                )
            except Exception as tracking_err:
                logger.warning(
                    "manual_query_interaction_tracking_failed",
                    conversation_id=str(request.conversation_id),
                    error=str(tracking_err),
                )

            # Send final result
            final_result = {
                "type": "result",
                "data": {
                    "query": request.query,
                    "suggestions": suggestions,
                    "server_path": server_path,
                    "tool_name": tool_name,
                    "interaction_id": interaction_id,  # For rating functionality
                }
            }
            yield f"data: {json.dumps(final_result)}\n\n"
            yield "data: [DONE]\n\n"

        except HTTPException as e:
            error_event = json.dumps({
                "type": "error",
                "message": str(e.detail),
                "status_code": e.status_code
            })
            yield f"data: {error_event}\n\n"
        except Exception as e:
            error_detail = str(e) or repr(e) or type(e).__name__
            logger.error(
                "mcp_query_failed",
                query=request.query,
                error=error_detail,
                error_type=type(e).__name__,
                exc_info=True,
            )
            error_event = json.dumps({
                "type": "error",
                "message": f"MCP query failed: {error_detail}",
                "status_code": 500
            })
            yield f"data: {error_event}\n\n"

    return StreamingResponse(
        generate_sse_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Connection": "keep-alive",
        }
    )


@router.post("/suggestions/{interaction_id}/rate")
async def rate_suggestion(
    interaction_id: int,
    request: SuggestionRatingRequest,
    repository: ConversationRepository = Depends(get_repository),
) -> SuggestionRatingResponse:
    """Rate an MCP suggestion with thumbs up/down.

    Args:
        interaction_id: Integer primary key of the agent interaction
        request: Rating request containing "up" or "down"
        repository: Conversation repository dependency

    Returns:
        Confirmation response with status, interaction_id, and rating

    Raises:
        HTTPException: 404 if interaction not found, 500 on other errors
    """
    try:
        # Look up the interaction
        interaction = await repository.get_agent_interaction(interaction_id)
        if not interaction:
            raise HTTPException(
                status_code=404,
                detail=f"Interaction {interaction_id} not found",
            )

        # Update the rating
        await repository.update_agent_interaction_rating(
            interaction_id=interaction_id,
            rating=request.rating,
        )

        logger.info(
            "suggestion_rated",
            interaction_id=interaction_id,
            rating=request.rating,
        )

        return SuggestionRatingResponse(
            status="rated",
            interaction_id=str(interaction_id),
            rating=request.rating,
        )

    except HTTPException:
        # Re-raise HTTP exceptions (like 404)
        raise
    except Exception as e:
        logger.error(
            "suggestion_rating_failed",
            interaction_id=interaction_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to rate suggestion: {str(e)}",
        )


@router.get("/mcp/servers")
async def list_mcp_servers(
    mcp_client: MCPClient = Depends(get_mcp_client),
) -> dict:
    """List all available MCP servers using discovery endpoint.

    Returns:
        Discovery data including:
        - servers: List of server objects
        - total_count: Number of servers
        - available_roles: List of all available roles
        - available_categories: List of all categories

    Raises:
        HTTPException: 503 if MCP not available, 500 if query fails

    Example:
        GET /api/mcp/servers
        Response: {
            "servers": [
                {
                    "name": "product_retrieval_server",
                    "path": "/product_retrieval",
                    "roles": ["product_retrieval", "aggregated_product_tools"],
                    "category": "product",
                    "priority": "high"
                }
            ],
            "total_count": 10,
            "available_roles": [...],
            "available_categories": [...]
        }
    """
    try:
        discovery = await mcp_client.list_servers()
        logger.info("mcp_servers_listed", server_count=discovery.get("total_count", 0) if isinstance(discovery, dict) else 0)
        return discovery
    except Exception as e:
        logger.error("mcp_servers_list_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list MCP servers: {str(e)}")


@router.get("/mcp/servers/{server_path}/tools")
async def list_mcp_tools(
    server_path: str,
    mcp_client: MCPClient = Depends(get_mcp_client),
) -> dict:
    """List tools available on a specific MCP server.

    Args:
        server_path: MCP server path (e.g., "product_retrieval")

    Returns:
        List of available tools on the server

    Raises:
        HTTPException: 503 if MCP not available, 500 if query fails

    Example:
        GET /api/mcp/servers/product_retrieval/tools
        Response: {
            "server_path": "product_retrieval",
            "tools": [...]
        }
    """
    try:
        tools = await mcp_client.list_tools(server_path)
        logger.info("mcp_tools_listed", server_path=server_path, tool_count=len(tools) if isinstance(tools, list) else 0)
        return {"server_path": server_path, "tools": tools}
    except Exception as e:
        logger.error("mcp_tools_list_failed", server_path=server_path, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list tools for {server_path}: {str(e)}")


@router.post(
    "/conversations/{conversation_id}/listening-mode/start",
    response_model=ListeningModeStartResponse,
    status_code=201,
)
async def start_listening_mode(
    conversation_id: UUID,
    manager: ConversationManager = Depends(get_conversation_manager),
    listening_mode_manager: ListeningModeManager | None = Depends(get_listening_mode_manager),
    repository: ConversationRepository = Depends(get_repository),
) -> ListeningModeStartResponse:
    """Start listening mode session for conversation.

    Enables automated opportunity detection and MCP query execution.

    Args:
        conversation_id: UUID of conversation
        manager: Conversation manager dependency
        listening_mode_manager: Listening mode manager dependency
        repository: Repository dependency

    Returns:
        ListeningModeStartResponse with session details

    Raises:
        HTTPException: 503 if feature disabled, 404 if conversation not found,
                       409 if session already active

    Example:
        POST /api/conversations/{uuid}/listening-mode/start
        Response: {
            "session_id": 123,
            "conversation_id": "uuid",
            "started_at": "2026-02-22T...",
            "status": "active"
        }
    """
    try:
        # Check if listening mode manager is available
        if listening_mode_manager is None:
            raise HTTPException(
                status_code=503,
                detail="Listening mode not available. Feature disabled or not configured.",
            )

        # Verify conversation exists
        conversation = await manager.get_conversation_state(conversation_id)
        if not conversation:
            raise HTTPException(
                status_code=404,
                detail=f"Conversation {conversation_id} not found",
            )

        # Check if session already active (idempotent: return existing session)
        existing_session = await repository.get_active_listening_mode_session(conversation_id)
        if existing_session:
            logger.info(
                "listening_mode_session_already_active",
                conversation_id=str(conversation_id),
                session_id=existing_session.id,
            )
            return ListeningModeStartResponse(
                session_id=existing_session.id,
                conversation_id=str(conversation_id),
                started_at=existing_session.started_at,
                status="active",
            )

        # Start new session
        session_id = await listening_mode_manager.start_session(conversation_id)

        # Get session details
        session = await repository.get_active_listening_mode_session(conversation_id)
        if not session:
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve created session",
            )

        logger.info(
            "listening_mode_started_via_api",
            conversation_id=str(conversation_id),
            session_id=session_id,
        )

        return ListeningModeStartResponse(
            session_id=session.id,
            conversation_id=str(conversation_id),
            started_at=session.started_at,
            status="active",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "listening_mode_start_failed",
            conversation_id=str(conversation_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start listening mode: {str(e)}",
        )


@router.post(
    "/conversations/{conversation_id}/listening-mode/stop",
    response_model=ListeningModeStopResponse,
)
async def stop_listening_mode(
    conversation_id: UUID,
    manager: ConversationManager = Depends(get_conversation_manager),
    listening_mode_manager: ListeningModeManager | None = Depends(get_listening_mode_manager),
    repository: ConversationRepository = Depends(get_repository),
) -> ListeningModeStopResponse:
    """Stop listening mode session for conversation.

    Ends automated opportunity detection and returns session metrics.

    Args:
        conversation_id: UUID of conversation
        manager: Conversation manager dependency
        listening_mode_manager: Listening mode manager dependency
        repository: Repository dependency

    Returns:
        ListeningModeStopResponse with session metrics

    Raises:
        HTTPException: 503 if feature disabled, 404 if conversation or session not found

    Example:
        POST /api/conversations/{uuid}/listening-mode/stop
        Response: {
            "session_id": 123,
            "conversation_id": "uuid",
            "ended_at": "2026-02-22T...",
            "auto_queries_count": 5,
            "opportunities_detected": 8,
            "duration_seconds": 245.3
        }
    """
    try:
        # Check if listening mode manager is available
        if listening_mode_manager is None:
            raise HTTPException(
                status_code=503,
                detail="Listening mode not available. Feature disabled or not configured.",
            )

        # Verify conversation exists
        conversation = await manager.get_conversation_state(conversation_id)
        if not conversation:
            raise HTTPException(
                status_code=404,
                detail=f"Conversation {conversation_id} not found",
            )

        # Check if session exists
        session = await repository.get_active_listening_mode_session(conversation_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"No active listening mode session for conversation {conversation_id}",
            )

        # Capture session data before stopping (since it will be updated)
        session_id = session.id
        started_at = session.started_at
        auto_queries_count = session.auto_queries_count
        opportunities_detected = session.opportunities_detected

        # Calculate duration (ended_at will be now)
        # Database stores UTC as naive datetime, so use now(UTC) and strip timezone
        ended_at_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        duration_seconds = (ended_at_naive - started_at).total_seconds()

        # Return timezone-aware datetime in response (ISO 8601 format)
        ended_at = datetime.now(timezone.utc)

        # Stop session (updates database with ended_at timestamp)
        await listening_mode_manager.stop_session(conversation_id)

        logger.info(
            "listening_mode_stopped_via_api",
            conversation_id=str(conversation_id),
            session_id=session_id,
            auto_queries=auto_queries_count,
            opportunities=opportunities_detected,
        )

        return ListeningModeStopResponse(
            session_id=session_id,
            conversation_id=str(conversation_id),
            ended_at=ended_at,
            auto_queries_count=auto_queries_count,
            opportunities_detected=opportunities_detected,
            duration_seconds=duration_seconds,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "listening_mode_stop_failed",
            conversation_id=str(conversation_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop listening mode: {str(e)}",
        )


@router.get(
    "/conversations/{conversation_id}/listening-mode/status",
    response_model=ListeningModeStatusResponse,
)
async def get_listening_mode_status(
    conversation_id: UUID,
    listening_mode_manager: ListeningModeManager | None = Depends(get_listening_mode_manager),
    repository: ConversationRepository = Depends(get_repository),
) -> ListeningModeStatusResponse:
    """Get listening mode session status for conversation.

    Returns current session state and metrics.

    Args:
        conversation_id: UUID of conversation
        listening_mode_manager: Listening mode manager dependency
        repository: Repository dependency

    Returns:
        ListeningModeStatusResponse with session state

    Example:
        GET /api/conversations/{uuid}/listening-mode/status
        Response: {
            "is_active": true,
            "session_id": 123,
            "conversation_id": "uuid",
            "started_at": "2026-02-22T...",
            "ended_at": null,
            "auto_queries_count": 3,
            "opportunities_detected": 5,
            "elapsed_seconds": 145.2
        }
    """
    try:
        # Check if listening mode manager is available
        if listening_mode_manager is None:
            # Return unavailable status if feature disabled (no MCP configured)
            return ListeningModeStatusResponse(
                available=False,
                is_active=False,
                session_id=None,
                conversation_id=str(conversation_id),
                started_at=None,
                ended_at=None,
                auto_queries_count=0,
                opportunities_detected=0,
                elapsed_seconds=None,
            )

        # Get active session
        session = await repository.get_active_listening_mode_session(conversation_id)

        if not session:
            # No active session
            return ListeningModeStatusResponse(
                available=True,
                is_active=False,
                session_id=None,
                conversation_id=str(conversation_id),
                started_at=None,
                ended_at=None,
                auto_queries_count=0,
                opportunities_detected=0,
                elapsed_seconds=None,
            )

        # Calculate elapsed time (database stores UTC as naive, so strip timezone)
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        elapsed_seconds = (now_naive - session.started_at).total_seconds()

        logger.debug(
            "listening_mode_status_retrieved",
            conversation_id=str(conversation_id),
            session_id=session.id,
            is_active=True,
        )

        return ListeningModeStatusResponse(
            available=True,
            is_active=True,
            session_id=session.id,
            conversation_id=str(conversation_id),
            started_at=session.started_at,
            ended_at=session.ended_at,
            auto_queries_count=session.auto_queries_count,
            opportunities_detected=session.opportunities_detected,
            elapsed_seconds=elapsed_seconds,
        )

    except Exception as e:
        logger.error(
            "listening_mode_status_failed",
            conversation_id=str(conversation_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get listening mode status: {str(e)}",
        )


@router.get("/health", response_model=HealthCheckResponse)
async def health_check() -> HealthCheckResponse:
    """Health check endpoint.

    Returns:
        HealthCheckResponse indicating service health

    Example:
        GET /health
        Response: {
            "status": "healthy",
            "timestamp": "2026-02-19T10:00:00"
        }
    """
    return HealthCheckResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc),
    )


@router.post("/dashboard/backfill")
async def backfill_dashboard_exports(
    request: Request,
    repository: ConversationRepository = Depends(get_repository),
    export_service: DataExportService = Depends(get_data_export_service),
):
    """Export all existing conversations to /tmp for dashboard backfill.

    One-time admin endpoint to populate the dashboard with historical data.
    Iterates all conversations in the database and exports each to JSON.

    Returns:
        Summary of exported and failed conversations
    """
    from sqlalchemy import select
    from app.models.domain import Conversation

    async with repository.session_maker() as session:
        stmt = select(Conversation.id)
        result = await session.execute(stmt)
        conversation_ids = [row[0] for row in result.all()]

    exported = 0
    failed = 0
    for conv_id in conversation_ids:
        try:
            await export_service.export_conversation_data(conv_id)
            exported += 1
        except Exception as e:
            logger.warning("backfill_export_failed", conversation_id=conv_id, error=str(e))
            failed += 1

    logger.info(
        "dashboard_backfill_complete",
        total=len(conversation_ids),
        exported=exported,
        failed=failed,
    )

    return {
        "status": "complete",
        "total_conversations": len(conversation_ids),
        "exported": exported,
        "failed": failed,
    }
