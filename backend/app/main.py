"""FastAPI application entry point.

Manages application lifecycle with lifespan context manager.
Initializes all services and configures middleware.
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models.database import init_db, close_db, get_session_maker
from app.services.factory import create_event_bus, create_cache
from app.services.transcript_parser import TranscriptParser
from app.services.transcript_streamer import TranscriptStreamer
from app.services.word_streamer import WordStreamer
from app.services.summary_generator import SummaryGenerator
from app.services.conversation_manager import ConversationManager
from app.services.model_manager import ModelManager
from app.services.mcp_token_manager import MCPTokenManager
from app.services.mcp_client import MCPClient
from app.repositories.conversation_repository import ConversationRepository
from app.services.data_export_service import DataExportService
from app.api import routes, websocket

import structlog

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    Handles startup and shutdown of services.
    Services are initialized once and shared across requests.

    Startup:
        1. Initialize database tables
        2. Create event bus and cache (factory pattern based on config)
        3. Initialize parser, repository, streamer
        4. Initialize summary generator (subscribes to events)
        5. Create conversation manager
        6. Set dependencies for DI

    Shutdown:
        1. Stop MCP services
        2. Stop event bus and cache
        3. Close database connections
    """
    # ============ STARTUP ============
    logger.info(
        "application_starting",
        environment="development",
        config={
            "openai_model": settings.OPENAI_MODEL,
            "summary_interval": settings.SUMMARY_INTERVAL_SECONDS,
            "words_per_second": settings.TRANSCRIPT_WORDS_PER_SECOND,
        },
    )

    try:
        # Initialize database
        await init_db()
        logger.info("database_initialized")

        # Create event bus (InMemory or Redis based on REDIS_URL)
        event_bus = create_event_bus()
        await event_bus.start()
        logger.info(
            "event_bus_started",
            type=type(event_bus).__name__,
            redis_enabled=settings.REDIS_URL is not None
        )

        # Create cache (InMemory or Redis based on REDIS_URL)
        cache = create_cache()
        logger.info(
            "cache_initialized",
            type=type(cache).__name__,
            redis_enabled=settings.REDIS_URL is not None
        )

        # Get database session maker
        session_maker = get_session_maker()

        # Initialize transcript parser
        parser = TranscriptParser(file_path=settings.TRANSCRIPT_FILE_PATH)
        logger.info("transcript_parser_initialized", path=settings.TRANSCRIPT_FILE_PATH)

        # Initialize repository
        repository = ConversationRepository(session_maker)
        logger.info("conversation_repository_initialized")

        # Initialize word streamer (handles word-by-word delivery)
        word_streamer = WordStreamer(
            repository=repository,
            event_bus=event_bus,
            words_per_second=settings.TRANSCRIPT_WORDS_PER_SECOND,
        )
        logger.info("word_streamer_initialized")

        # Initialize transcript streamer (orchestrates line sequencing)
        streamer = TranscriptStreamer(
            parser=parser,
            repository=repository,
            event_bus=event_bus,
            word_streamer=word_streamer,
            initial_delay=settings.TRANSCRIPT_INITIAL_DELAY,
            inter_line_delay=settings.TRANSCRIPT_INTER_LINE_DELAY,
        )
        logger.info("transcript_streamer_initialized")

        # Initialize model manager (central model state holder)
        model_manager = ModelManager(model_id=settings.OPENAI_MODEL)
        logger.info("model_manager_initialized", model=settings.OPENAI_MODEL)

        # Initialize summary generator (subscribes to events internally)
        summary_generator = SummaryGenerator(
            repository=repository,
            event_bus=event_bus,
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_MODEL,
            interval_seconds=settings.SUMMARY_INTERVAL_SECONDS,
        )
        logger.info("summary_generator_initialized")

        # Initialize utterance boundary detector (heuristic-based boundary detection)
        from app.services.utterance_boundary_detector import UtteranceBoundaryDetector
        utterance_detector = UtteranceBoundaryDetector(
            min_words_complete=settings.UTT_MIN_WORDS_COMPLETE,
            min_words_question=settings.UTT_MIN_WORDS_QUESTION,
            min_words_command=settings.UTT_MIN_WORDS_COMMAND,
            confidence_threshold=settings.UTT_CONFIDENCE_GOOD,
        )
        logger.info("utterance_boundary_detector_initialized")

        # Initialize semantic checker (optional, graceful degradation)
        semantic_checker = None
        if not settings.UTT_DISABLE_SPACY_SEMANTIC:
            try:
                from app.services.spacy_semantic_checker import SpacySemanticChecker
                semantic_checker = SpacySemanticChecker()
                logger.info("spacy_semantic_checker_initialized", model="en_core_web_sm")
            except ImportError:
                logger.warning("spacy_not_installed", message="Using heuristics only")
            except OSError as e:
                logger.warning("spacy_model_not_found", error=str(e))
        else:
            logger.info("spacy_semantic_disabled", reason="UTT_DISABLE_SPACY_SEMANTIC=true")

        # Initialize utterance manager (subscribes to transcript events)
        from app.services.utterance_manager import UtteranceManager
        utterance_manager = UtteranceManager(
            event_bus=event_bus,
            boundary_detector=utterance_detector,
            short_timeout=settings.UTT_SHORT_TIMEOUT_S,
            medium_timeout=settings.UTT_MEDIUM_TIMEOUT_S,
            long_timeout=settings.UTT_LONG_TIMEOUT_S,
            hard_max_timeout=settings.UTT_HARD_MAX_TIMEOUT_S,
            confidence_high=settings.UTT_CONFIDENCE_HIGH,
            confidence_good=settings.UTT_CONFIDENCE_GOOD,
            semantic_checker=semantic_checker,
            semantic_confidence_threshold=settings.UTT_SEMANTIC_CONFIDENCE_THRESHOLD,
        )
        logger.info(
            "utterance_manager_initialized",
            semantic_enabled=semantic_checker is not None,
        )

        # Initialize conversation manager (facade)
        manager = ConversationManager(
            repository=repository,
            streamer=streamer,
            event_bus=event_bus,
        )
        logger.info("conversation_manager_initialized")

        # Initialize MCP client (optional - graceful degradation if key missing)
        mcp_client = None
        mcp_token_manager = None
        if settings.MCP_SECRET_KEY:
            try:
                mcp_token_manager = MCPTokenManager(
                    secret_key=settings.MCP_SECRET_KEY,
                    algorithm=settings.MCP_SECRET_ALGORITHM,
                )
                mcp_token_manager.start_background_refresh()
                logger.info("mcp_token_manager_started")

                mcp_client = MCPClient(
                    base_url=settings.MCP_INGRESS_URL,
                    token_manager=mcp_token_manager,
                    timeout=settings.MCP_REQUEST_TIMEOUT,
                )
                logger.info("mcp_client_initialized")
            except Exception as e:
                logger.warning(
                    "mcp_initialization_failed",
                    error=str(e),
                    exc_info=True,
                )
                # Continue without MCP - graceful degradation
        else:
            logger.info("mcp_disabled_no_secret_key")

        # Initialize listening mode services (if enabled and MCP available)
        opportunity_detector = None
        listening_mode_manager = None
        mcp_orchestrator = None

        if settings.LISTENING_MODE_ENABLED and mcp_client and settings.OPENAI_API_KEY:
            try:
                # Initialize MCP orchestrator (needed by ListeningModeManager)
                from app.services.mcp_orchestrator import MCPOrchestrator
                mcp_orchestrator = MCPOrchestrator(
                    mcp_client=mcp_client,
                    openai_api_key=settings.OPENAI_API_KEY,
                    model=settings.OPENAI_MODEL,
                )
                logger.info("mcp_orchestrator_initialized")

                # Initialize opportunity detector (with utterance mode)
                from app.services.opportunity_detector import OpportunityDetector
                opportunity_detector = OpportunityDetector(
                    repository=repository,
                    event_bus=event_bus,
                    cache=cache,
                    api_key=settings.OPENAI_API_KEY,
                    model=settings.OPENAI_MODEL,
                    confidence_threshold=0.7,
                    dedup_ttl=30,
                    use_utterances=settings.LISTENING_MODE_USE_UTTERANCES,
                )
                logger.info(
                    "opportunity_detector_initialized",
                    mode="utterance" if settings.LISTENING_MODE_USE_UTTERANCES else "polling"
                )

                # Initialize listening mode manager
                from app.services.listening_mode_manager import ListeningModeManager
                listening_mode_manager = ListeningModeManager(
                    repository=repository,
                    event_bus=event_bus,
                    mcp_orchestrator=mcp_orchestrator,
                    cache=cache,
                )
                logger.info("listening_mode_manager_initialized")

            except Exception as e:
                logger.warning(
                    "listening_mode_initialization_failed",
                    error=str(e),
                    exc_info=True,
                )
                # Continue without listening mode - graceful degradation
                opportunity_detector = None
                listening_mode_manager = None
                mcp_orchestrator = None
        else:
            reasons = []
            if not settings.LISTENING_MODE_ENABLED:
                reasons.append("LISTENING_MODE_ENABLED=false")
            if not mcp_client:
                reasons.append("no_mcp_client")
            if not settings.OPENAI_API_KEY:
                reasons.append("no_openai_api_key")
            logger.info("listening_mode_disabled", reasons=", ".join(reasons))

        # Register model change callbacks (Observer pattern)
        # When model changes via PUT /api/model, all services update simultaneously
        model_manager.register_callback(summary_generator.set_model)
        if opportunity_detector:
            model_manager.register_callback(opportunity_detector.set_model)
        if mcp_orchestrator:
            model_manager.register_callback(mcp_orchestrator.set_model)
        logger.info("model_manager_callbacks_registered")

        # Store all dependencies in app.state (replaces set_dependencies)
        # Using app.state pattern instead of global variables
        app.state.model_manager = model_manager
        app.state.event_bus = event_bus
        app.state.cache = cache
        app.state.repository = repository
        app.state.data_export_service = DataExportService(repository)
        app.state.conversation_manager = manager
        app.state.summary_generator = summary_generator
        app.state.utterance_manager = utterance_manager
        app.state.transcript_streamer = streamer  # Add transcript streamer for shutdown
        app.state.mcp_token_manager = mcp_token_manager
        app.state.mcp_client = mcp_client
        app.state.mcp_orchestrator = mcp_orchestrator
        app.state.opportunity_detector = opportunity_detector
        app.state.listening_mode_manager = listening_mode_manager

        logger.info(
            "application_startup_complete",
            event_bus_type=type(event_bus).__name__,
            cache_type=type(cache).__name__,
            mcp_enabled=mcp_client is not None,
            listening_mode_enabled=listening_mode_manager is not None,
            utterance_mode=settings.LISTENING_MODE_USE_UTTERANCES if settings.LISTENING_MODE_ENABLED else None,
            production_ready=settings.REDIS_URL is not None,
            dependency_pattern="app.state"
        )

    except Exception as e:
        logger.error(
            "application_startup_failed",
            error=str(e),
            exc_info=True,
        )
        raise

    yield

    # ============ SHUTDOWN ============
    logger.info("application_shutting_down")

    try:
        # Stop MCP token manager if initialized
        if app.state.mcp_token_manager:
            await app.state.mcp_token_manager.stop_background_refresh()
            logger.info("mcp_token_manager_stopped")

        # Close MCP client if initialized
        if app.state.mcp_client:
            await app.state.mcp_client.close()
            logger.info("mcp_client_closed")

        # Shutdown utterance manager (cancel pending tasks)
        if hasattr(app.state, "utterance_manager") and app.state.utterance_manager:
            try:
                await asyncio.wait_for(
                    app.state.utterance_manager.shutdown(),
                    timeout=5.0
                )
                logger.info("utterance_manager_stopped")
            except asyncio.TimeoutError:
                logger.warning("utterance_manager_shutdown_timeout")

        # Shutdown transcript streamer (cancel active streaming tasks before event bus stops)
        if hasattr(app.state, "transcript_streamer") and app.state.transcript_streamer:
            try:
                await asyncio.wait_for(
                    app.state.transcript_streamer.shutdown(),
                    timeout=5.0
                )
                logger.info("transcript_streamer_stopped")
            except asyncio.TimeoutError:
                logger.warning("transcript_streamer_shutdown_timeout")

        # Shutdown summary generator (cancel periodic tasks before stopping event bus)
        if hasattr(app.state, "summary_generator") and app.state.summary_generator:
            try:
                await asyncio.wait_for(
                    app.state.summary_generator.shutdown(),
                    timeout=5.0
                )
                logger.info("summary_generator_stopped")
            except asyncio.TimeoutError:
                logger.warning("summary_generator_shutdown_timeout")

        # Shutdown opportunity detector (cancel analysis tasks)
        if hasattr(app.state, "opportunity_detector") and app.state.opportunity_detector:
            try:
                await asyncio.wait_for(
                    app.state.opportunity_detector.shutdown(),
                    timeout=5.0
                )
                logger.info("opportunity_detector_stopped")
            except asyncio.TimeoutError:
                logger.warning("opportunity_detector_shutdown_timeout")

        # Shutdown listening mode manager (prevent new work)
        if hasattr(app.state, "listening_mode_manager") and app.state.listening_mode_manager:
            try:
                await asyncio.wait_for(
                    app.state.listening_mode_manager.shutdown(),
                    timeout=5.0
                )
                logger.info("listening_mode_manager_stopped")
            except asyncio.TimeoutError:
                logger.warning("listening_mode_manager_shutdown_timeout")

        # Stop event bus and close cache
        if hasattr(app.state, "event_bus"):
            await app.state.event_bus.stop()
            logger.info("event_bus_stopped")

        if hasattr(app.state, "cache"):
            await app.state.cache.close()
            logger.info("cache_closed")

        # Close database
        await close_db()
        logger.info("database_closed")

        logger.info("application_shutdown_complete")

    except Exception as e:
        logger.error(
            "application_shutdown_failed",
            error=str(e),
            exc_info=True,
        )


# Create FastAPI application
app = FastAPI(
    title="Transcript & Summary Streaming API",
    description="Production-Lite streaming transcript and LLM summarization system",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware (allow all origins for demo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(routes.router, tags=["conversations"])
app.include_router(websocket.router, tags=["websocket"])


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Transcript & Summary Streaming API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "create_conversation": "POST /api/conversations",
            "get_conversation": "GET /api/conversations/{id}",
            "websocket": "WS /api/ws/{conversation_id}",
        },
    }


# For running with: python -m app.main
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )
