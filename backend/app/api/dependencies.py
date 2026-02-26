"""Dependency injection for FastAPI using app.state pattern.

Uses FastAPI's app.state instead of global variables.
Follows Dependency Inversion Principle without global keyword.
"""
from typing import Annotated
from fastapi import Depends, HTTPException, Request, WebSocket

from app.services.event_bus import EventBus
from app.services.cache import Cache
from app.services.conversation_manager import ConversationManager
from app.services.summary_generator import SummaryGenerator
from app.services.acw_service import ACWService
from app.services.mcp_client import MCPClient
from app.services.mcp_orchestrator import MCPOrchestrator
from app.services.listening_mode_manager import ListeningModeManager
from app.services.model_manager import ModelManager
from app.services.data_export_service import DataExportService
from app.config import settings
from app.repositories.conversation_repository import ConversationRepository

import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# FastAPI app.state pattern - No global keyword needed!
# Works with both Request (HTTP) and WebSocket connections
# ============================================================================


def get_event_bus(request: Request) -> EventBus:
    """Get event bus from app state (HTTP endpoints).

    No global keyword needed - reads from app.state set during lifespan.

    Args:
        request: FastAPI request (auto-injected)

    Returns:
        Event bus singleton (InMemory or Redis)

    Raises:
        RuntimeError: If event bus not initialized
    """
    if not hasattr(request.app.state, "event_bus"):
        raise RuntimeError("Event bus not initialized. Check lifespan setup.")
    return request.app.state.event_bus


def get_event_bus_ws(websocket: WebSocket) -> EventBus:
    """Get event bus from app state (WebSocket endpoints).

    No global keyword needed - reads from app.state set during lifespan.

    Args:
        websocket: FastAPI WebSocket (auto-injected)

    Returns:
        Event bus singleton (InMemory or Redis)

    Raises:
        RuntimeError: If event bus not initialized
    """
    if not hasattr(websocket.app.state, "event_bus"):
        raise RuntimeError("Event bus not initialized. Check lifespan setup.")
    return websocket.app.state.event_bus


def get_cache(request: Request) -> Cache:
    """Get cache from app state.

    Args:
        request: FastAPI request (auto-injected)

    Returns:
        Cache singleton (InMemory or Redis)

    Raises:
        RuntimeError: If cache not initialized
    """
    if not hasattr(request.app.state, "cache"):
        raise RuntimeError("Cache not initialized. Check lifespan setup.")
    return request.app.state.cache


def get_conversation_manager(request: Request) -> ConversationManager:
    """Get conversation manager from app state.

    Args:
        request: FastAPI request (auto-injected)

    Returns:
        Conversation manager singleton

    Raises:
        RuntimeError: If conversation manager not initialized
    """
    if not hasattr(request.app.state, "conversation_manager"):
        raise RuntimeError("Conversation manager not initialized. Check lifespan setup.")
    return request.app.state.conversation_manager


def get_summary_generator(request: Request) -> SummaryGenerator:
    """Get summary generator from app state.

    Args:
        request: FastAPI request (auto-injected)

    Returns:
        Summary generator singleton

    Raises:
        RuntimeError: If summary generator not initialized
    """
    if not hasattr(request.app.state, "summary_generator"):
        raise RuntimeError("Summary generator not initialized. Check lifespan setup.")
    return request.app.state.summary_generator


def get_repository(request: Request) -> ConversationRepository:
    """Get conversation repository from app state.

    Args:
        request: FastAPI request (auto-injected)

    Returns:
        Conversation repository singleton

    Raises:
        RuntimeError: If repository not initialized
    """
    if not hasattr(request.app.state, "repository"):
        raise RuntimeError("Repository not initialized. Check lifespan setup.")
    return request.app.state.repository


def get_session_maker(request: Request):
    """Get session maker from app state.

    Args:
        request: FastAPI request (auto-injected)

    Returns:
        Async session maker

    Raises:
        RuntimeError: If session maker not initialized
    """
    if not hasattr(request.app.state, "session_maker"):
        raise RuntimeError("Session maker not initialized. Check lifespan setup.")
    return request.app.state.session_maker

def get_mcp_client(request: Request) -> MCPClient:
    """Get MCP client from app state.

    Args:
        request: FastAPI request (auto-injected)

    Returns:
        MCP client singleton

    Raises:
        HTTPException: If MCP client not available (graceful degradation)
    """
    if not hasattr(request.app.state, "mcp_client") or request.app.state.mcp_client is None:
        logger.warning("mcp_client_not_available")
        raise HTTPException(
            status_code=503,
            detail="MCP features not available. MCP_SECRET_KEY not configured."
        )
    return request.app.state.mcp_client


def get_model_manager(request: Request) -> ModelManager:
    """Get model manager from app state.

    Args:
        request: FastAPI request (auto-injected)

    Returns:
        ModelManager singleton

    Raises:
        RuntimeError: If model manager not initialized
    """
    if not hasattr(request.app.state, "model_manager"):
        raise RuntimeError("Model manager not initialized. Check lifespan setup.")
    return request.app.state.model_manager


def get_data_export_service(request: Request) -> DataExportService:
    """Get data export service from app state.

    Args:
        request: FastAPI request (auto-injected)

    Returns:
        DataExportService singleton
    """
    if not hasattr(request.app.state, "data_export_service"):
        raise RuntimeError("DataExportService not initialized. Check lifespan setup.")
    return request.app.state.data_export_service


def get_listening_mode_manager(request: Request) -> ListeningModeManager | None:
    """Get listening mode manager from app state (graceful degradation if None).

    Args:
        request: FastAPI request (auto-injected)

    Returns:
        Listening mode manager singleton or None if feature disabled
    """
    return getattr(request.app.state, "listening_mode_manager", None)


async def get_mcp_orchestrator(
    mcp_client: MCPClient = Depends(get_mcp_client)
) -> MCPOrchestrator:
    """Get MCP orchestrator for LLM-driven tool selection.

    Args:
        mcp_client: MCP client dependency

    Returns:
        MCP orchestrator instance

    Raises:
        RuntimeError: If OPENAI_API_KEY not configured
    """
    if not settings.OPENAI_API_KEY:
        error_msg = (
            "OPENAI_API_KEY is required for MCP orchestrator (LLM-driven tool selection).\n\n"
            "To fix this:\n"
            "  export OPENAI_API_KEY=sk-your-key-here\n"
        )
        logger.error("openai_api_key_missing_for_mcp")
        raise RuntimeError(error_msg)

    return MCPOrchestrator(
        mcp_client=mcp_client,
        openai_api_key=settings.OPENAI_API_KEY
    )


async def get_acw_service(request: Request) -> ACWService:
    """Get ACW service instance for dependency injection.

    Uses lazy initialization via app.state to avoid startup failures
    if OPENAI_API_KEY is not available.

    Args:
        request: FastAPI request (auto-injected) for accessing app state

    Returns:
        ACW service singleton

    Raises:
        RuntimeError: If OPENAI_API_KEY not set or ACW service initialization fails
    """
    # Check if already initialized in app.state
    if not hasattr(request.app.state, "acw_service") or request.app.state.acw_service is None:
        # Validate OpenAI API key is set
        if not settings.OPENAI_API_KEY:
            error_msg = (
                "OPENAI_API_KEY is required for ACW service but not set.\n\n"
                "To fix this:\n"
                "  export OPENAI_API_KEY=sk-your-key-here\n"
            )
            logger.error("openai_api_key_missing")
            raise RuntimeError(error_msg)

        # Get current model from ModelManager (fixes race condition)
        model_manager = get_model_manager(request)
        preset = model_manager.get_current_preset()

        # Lazy initialization and store in app.state
        session_maker = get_session_maker(request)
        repository = ConversationRepository(session_maker)
        request.app.state.acw_service = ACWService(
            repository=repository,
            openai_api_key=settings.OPENAI_API_KEY,
            model=preset.model_name,  # Use current model, not config default
        )

        # Register callback for model changes
        model_manager.register_callback(request.app.state.acw_service.set_model)

        logger.info("acw_service_lazy_initialized", model=preset.model_name)

    return request.app.state.acw_service


# ============================================================================
# Type aliases for cleaner route signatures
# ============================================================================

ModelManagerDep = Annotated[ModelManager, Depends(get_model_manager)]
EventBusDep = Annotated[EventBus, Depends(get_event_bus)]
CacheDep = Annotated[Cache, Depends(get_cache)]
ConversationManagerDep = Annotated[ConversationManager, Depends(get_conversation_manager)]
SummaryGeneratorDep = Annotated[SummaryGenerator, Depends(get_summary_generator)]
ACWServiceDep = Annotated[ACWService, Depends(get_acw_service)]
MCPClientDep = Annotated[MCPClient, Depends(get_mcp_client)]
DataExportServiceDep = Annotated[DataExportService, Depends(get_data_export_service)]
ListeningModeManagerDep = Annotated[ListeningModeManager | None, Depends(get_listening_mode_manager)]
