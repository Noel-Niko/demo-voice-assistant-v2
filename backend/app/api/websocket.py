"""WebSocket endpoint for real-time conversation updates.

Implements queue-per-connection pattern for efficient event broadcasting.
Pattern copied from voice-seiv-be-interview-prep reference project.
"""
import asyncio
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

from app.api.dependencies import get_event_bus_ws
from app.services.event_bus import Event, EventBus

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.websocket("/api/ws/{conversation_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    conversation_id: UUID,
    event_bus: EventBus = Depends(get_event_bus_ws),
) -> None:
    """WebSocket endpoint for real-time conversation updates.

    Subscribes to events for specific conversation and streams them to client.
    Uses queue-per-connection pattern to avoid blocking other connections.

    Args:
        websocket: WebSocket connection
        conversation_id: UUID of conversation to subscribe to
        event_bus: Event bus for subscribing to events

    Event Types Sent to Client:
        - connection.established: Sent immediately after connection
        - transcript.word.interim: Partial word-by-word transcript update
        - transcript.word.final: Final complete transcript line
        - summary.start: Summary generation started
        - summary.token: Individual token from streaming summary
        - summary.complete: Summary generation completed
        - streaming.complete: Transcript streaming finished
        - listening_mode.session.started: Listening mode session started
        - listening_mode.session.ended: Listening mode session ended
        - listening_mode.opportunity.detected: Opportunity detected
        - listening_mode.query.started: Auto-query started
        - listening_mode.query.complete: Auto-query completed
        - listening_mode.query.error: Auto-query failed
        - ping: Keepalive message (every 1 second)

    Example Client Event:
        {
            "event_type": "transcript.word.final",
            "data": {
                "conversation_id": "uuid",
                "line_id": "uuid-seq-1",
                "speaker": "agent",
                "text": "Hello, how can I help?",
                "is_final": true,
                "timestamp": "...",
                "sequence_number": 1
            },
            "timestamp": "2026-02-19T10:00:00"
        }
    """
    await websocket.accept()

    logger.info(
        "websocket_connected",
        conversation_id=str(conversation_id),
        client=websocket.client.host if websocket.client else "unknown",
    )

    # Create event queue for this connection
    event_queue: asyncio.Queue[Event] = asyncio.Queue()

    # Event handler: filter events by conversation_id and forward to queue
    async def handle_event(event: Event) -> None:
        """Filter and forward events to this connection's queue."""
        if event.conversation_id == str(conversation_id):
            await event_queue.put(event)

    # Subscribe to all event types this conversation needs
    event_types = [
        "transcript.word.interim",
        "transcript.word.final",
        "summary.start",
        "summary.token",
        "summary.complete",
        "streaming.complete",
        "conversation.started",
        "listening_mode.session.started",
        "listening_mode.session.ended",
        "listening_mode.opportunity.detected",
        "listening_mode.query.started",
        "listening_mode.query.complete",
        "listening_mode.query.error",
    ]

    for event_type in event_types:
        event_bus.subscribe(event_type, handle_event)

    try:
        # Send connection confirmation
        await websocket.send_json({
            "event_type": "connection.established",
            "data": {
                "conversation_id": str(conversation_id),
                "message": "Connected to conversation updates",
            },
            "timestamp": None,  # Will be set by client
        })

        logger.debug(
            "connection_established_sent",
            conversation_id=str(conversation_id),
        )

        # Process events in loop
        while True:
            try:
                # Wait for event with timeout to check connection health
                event = await asyncio.wait_for(event_queue.get(), timeout=1.0)

                # Send event to client
                await websocket.send_json({
                    "event_type": event.event_type,
                    "data": event.data,
                    "timestamp": event.timestamp.isoformat(),
                })

                logger.debug(
                    "event_sent_to_client",
                    conversation_id=str(conversation_id),
                    event_type=event.event_type,
                    event_id=event.event_id,
                )

            except asyncio.TimeoutError:
                # No events in queue, send ping to keep connection alive
                try:
                    await websocket.send_json({"event_type": "ping"})
                except Exception:
                    # Client disconnected during ping
                    break

    except WebSocketDisconnect:
        logger.info(
            "websocket_disconnected",
            conversation_id=str(conversation_id),
        )

    except Exception as e:
        logger.error(
            "websocket_error",
            conversation_id=str(conversation_id),
            error=str(e),
            exc_info=True,
        )

    finally:
        # Clean up: unsubscribe from all events
        for event_type in event_types:
            event_bus.unsubscribe(event_type, handle_event)

        logger.info(
            "websocket_cleanup_complete",
            conversation_id=str(conversation_id),
        )
