"""Event bus abstraction for event-driven architecture.

Provides abstract EventBus interface with InMemory and Redis implementations.
Follows Observer Pattern, Single Responsibility, and Dependency Inversion principles.

InMemoryEventBus: Local dev/demo (single process only)
RedisEventBus: Production-ready (works across pods/workers)
"""
import asyncio
import json
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Callable, Awaitable, Protocol
from uuid import uuid4

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class Event:
    """Event data structure.

    Follows Data Transfer Object pattern.
    """

    event_id: str
    event_type: str
    source: str
    data: dict[str, Any]
    timestamp: datetime
    conversation_id: str | None = None

    @classmethod
    def create(
        cls,
        event_type: str,
        source: str,
        data: dict[str, Any],
        conversation_id: str | None = None,
    ) -> "Event":
        """Create a new event with generated ID and timestamp.

        Args:
            event_type: Type of event (e.g., "transcript.batch")
            source: Source component (e.g., "transcript_streamer")
            data: Event payload data
            conversation_id: Optional conversation ID

        Returns:
            New Event instance
        """
        return cls(
            event_id=str(uuid4()),
            event_type=event_type,
            source=source,
            data=data,
            timestamp=datetime.now(),
            conversation_id=conversation_id,
        )


# Type alias for event handler function
EventHandler = Callable[[Event], Awaitable[None]]


class EventBusProtocol(Protocol):
    """Protocol defining event bus interface.

    Follows Interface Segregation Principle.
    """

    async def publish(self, event: Event) -> None:
        """Publish an event."""
        ...

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe to an event type."""
        ...

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Unsubscribe from an event type."""
        ...


class EventBus(ABC):
    """Abstract base class for event bus implementations.

    Follows Dependency Inversion Principle - depend on abstractions, not concretions.
    Allows swapping implementations via configuration (12-factor #4).
    """

    @abstractmethod
    async def publish(self, event: Event) -> None:
        """Publish an event to the bus.

        Args:
            event: Event to publish
        """
        pass

    @abstractmethod
    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe a handler to an event type.

        Args:
            event_type: Type of event to subscribe to
            handler: Async function to handle the event
        """
        pass

    @abstractmethod
    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Unsubscribe a handler from an event type.

        Args:
            event_type: Type of event to unsubscribe from
            handler: Handler function to remove
        """
        pass

    @abstractmethod
    async def start(self) -> None:
        """Start the event bus.

        Should be called during application startup.
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the event bus and cleanup resources.

        Should be called during application shutdown.
        """
        pass


class InMemoryEventBus(EventBus):
    """In-memory event bus implementation.

    Follows Single Responsibility and Observer Pattern.
    Uses asyncio.Queue for thread-safe event processing.
    """

    def __init__(self, queue_size: int = 1000) -> None:
        """Initialize event bus.

        Args:
            queue_size: Maximum size of event queue
        """
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=queue_size)
        self._worker_task: asyncio.Task | None = None
        self._running: bool = False

    async def start(self) -> None:
        """Start event bus worker.

        Should be called during application startup.
        """
        if self._running:
            logger.warning("event_bus_already_running")
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._process_events())
        logger.info("event_bus_started")

    async def stop(self) -> None:
        """Stop event bus worker.

        Should be called during application shutdown.
        """
        if not self._running:
            return

        self._running = False

        # Wait for queue to empty
        await self._queue.join()

        # Cancel worker task
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        logger.info("event_bus_stopped")

    async def publish(self, event: Event) -> None:
        """Publish an event to the bus.

        Args:
            event: Event to publish

        Raises:
            RuntimeError: If event bus is not running
        """
        if not self._running:
            raise RuntimeError("Event bus is not running. Call start() first.")

        await self._queue.put(event)
        logger.debug(
            "event_published",
            event_id=event.event_id,
            event_type=event.event_type,
            conversation_id=event.conversation_id,
        )

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe a handler to an event type.

        Args:
            event_type: Type of event to subscribe to
            handler: Async function to handle the event
        """
        self._handlers[event_type].append(handler)
        logger.info(
            "handler_subscribed",
            event_type=event_type,
            handler=handler.__name__,
        )

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Unsubscribe a handler from an event type.

        Args:
            event_type: Type of event to unsubscribe from
            handler: Handler function to remove
        """
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
                logger.info(
                    "handler_unsubscribed",
                    event_type=event_type,
                    handler=handler.__name__,
                )
            except ValueError:
                logger.warning(
                    "handler_not_found",
                    event_type=event_type,
                    handler=handler.__name__,
                )

    async def _process_events(self) -> None:
        """Worker task to process events from the queue.

        Runs continuously while event bus is running.
        """
        logger.info("event_worker_started")

        while self._running:
            try:
                # Get event from queue with timeout
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)

                # Dispatch to handlers
                await self._dispatch_event(event)

                # Mark task as done
                self._queue.task_done()

            except asyncio.TimeoutError:
                # No events in queue, continue waiting
                continue
            except Exception as e:
                logger.error(
                    "event_processing_error",
                    error=str(e),
                    exc_info=True,
                )

        logger.info("event_worker_stopped")

    async def _dispatch_event(self, event: Event) -> None:
        """Dispatch an event to all subscribed handlers.

        Args:
            event: Event to dispatch
        """
        handlers = self._handlers.get(event.event_type, [])

        if not handlers:
            logger.debug(
                "no_handlers_for_event",
                event_type=event.event_type,
                event_id=event.event_id,
            )
            return

        logger.debug(
            "dispatching_event",
            event_type=event.event_type,
            event_id=event.event_id,
            handler_count=len(handlers),
        )

        # Run handlers concurrently
        tasks = [self._run_handler(handler, event) for handler in handlers]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_handler(self, handler: EventHandler, event: Event) -> None:
        """Run a single event handler with error handling.

        Args:
            handler: Event handler function
            event: Event to handle
        """
        try:
            await handler(event)
            logger.debug(
                "handler_completed",
                handler=handler.__name__,
                event_id=event.event_id,
            )
        except Exception as e:
            logger.error(
                "handler_error",
                handler=handler.__name__,
                event_id=event.event_id,
                error=str(e),
                exc_info=True,
            )


class RedisEventBus(EventBus):
    """Production-ready event bus using Redis Pub/Sub.

    Works across multiple pods/workers - events published on one worker
    are received by all subscribed workers.

    Follows 12-factor #6: Stateless processes (state in backing service).
    """

    def __init__(self, redis_url: str) -> None:
        """Initialize Redis event bus.

        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379/0)
        """
        self._redis_url = redis_url
        self._redis = None
        self._pubsub = None
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._listener_task: asyncio.Task | None = None
        self._running: bool = False

    async def start(self) -> None:
        """Start Redis event bus and background listener."""
        if self._running:
            logger.warning("redis_event_bus_already_running")
            return

        try:
            import redis.asyncio as aioredis
        except ImportError:
            raise ImportError(
                "redis package not installed. Install with: pip install redis[hiredis]"
            )

        self._redis = aioredis.from_url(
            self._redis_url,
            decode_responses=True,
            encoding="utf-8"
        )
        self._pubsub = self._redis.pubsub()

        self._running = True
        # Start listener if there are subscriptions
        if self._handlers:
            self._listener_task = asyncio.create_task(self._listen())

        logger.info("redis_event_bus_started", redis_url=self._redis_url)

    async def stop(self) -> None:
        """Stop Redis event bus and cleanup connections."""
        if not self._running:
            return

        self._running = False

        # Stop listener task
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        # Close pubsub and redis connections
        if self._pubsub:
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()

        logger.info("redis_event_bus_stopped")

    async def publish(self, event: Event) -> None:
        """Publish event to Redis channel.

        Args:
            event: Event to publish

        Raises:
            RuntimeError: If event bus not started
        """
        if not self._running or not self._redis:
            raise RuntimeError("Redis event bus not started. Call start() first.")

        # Serialize event to JSON
        event_dict = asdict(event)
        # Convert datetime to ISO string for JSON serialization
        event_dict["timestamp"] = event.timestamp.isoformat()
        event_json = json.dumps(event_dict)

        # Publish to Redis channel (channel name = event_type)
        await self._redis.publish(event.event_type, event_json)

        logger.debug(
            "event_published_redis",
            event_id=event.event_id,
            event_type=event.event_type,
            conversation_id=event.conversation_id,
        )

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe handler to event type.

        Note: This is synchronous. Call start() to begin receiving events.

        Args:
            event_type: Type of event to subscribe to
            handler: Async function to handle events
        """
        self._handlers[event_type].append(handler)
        logger.info(
            "handler_subscribed_redis",
            event_type=event_type,
            handler=handler.__name__,
        )

        # If already running, need to update Redis subscription
        if self._running and self._pubsub:
            # Schedule subscription update in background
            asyncio.create_task(self._update_subscriptions())

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Unsubscribe handler from event type.

        Args:
            event_type: Type of event to unsubscribe from
            handler: Handler function to remove
        """
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
                logger.info(
                    "handler_unsubscribed_redis",
                    event_type=event_type,
                    handler=handler.__name__,
                )

                # If no more handlers for this event type, unsubscribe from Redis
                if not self._handlers[event_type] and self._running and self._pubsub:
                    asyncio.create_task(self._pubsub.unsubscribe(event_type))

            except ValueError:
                logger.warning(
                    "handler_not_found_redis",
                    event_type=event_type,
                    handler=handler.__name__,
                )

    async def _update_subscriptions(self) -> None:
        """Update Redis subscriptions based on current handlers."""
        if not self._pubsub:
            return

        # Subscribe to all event types that have handlers
        event_types = [et for et in self._handlers.keys() if self._handlers[et]]
        if event_types:
            await self._pubsub.subscribe(*event_types)

            # Start listener if not already running
            if not self._listener_task or self._listener_task.done():
                self._listener_task = asyncio.create_task(self._listen())

    async def _listen(self) -> None:
        """Background task to listen for Redis messages and dispatch to handlers."""
        logger.info("redis_listener_started")

        try:
            async for message in self._pubsub.listen():
                if not self._running:
                    break

                if message["type"] == "message":
                    await self._handle_redis_message(message)

        except asyncio.CancelledError:
            logger.info("redis_listener_cancelled")
            raise
        except Exception as e:
            logger.error(
                "redis_listener_error",
                error=str(e),
                exc_info=True,
            )

        logger.info("redis_listener_stopped")

    async def _handle_redis_message(self, message: dict[str, Any]) -> None:
        """Handle incoming Redis message by deserializing and dispatching.

        Args:
            message: Redis message dict with 'channel' and 'data'
        """
        try:
            event_type = message["channel"]
            event_json = message["data"]

            # Deserialize event
            event_dict = json.loads(event_json)
            # Convert ISO string back to datetime
            event_dict["timestamp"] = datetime.fromisoformat(event_dict["timestamp"])
            event = Event(**event_dict)

            # Dispatch to handlers
            handlers = self._handlers.get(event_type, [])
            if handlers:
                logger.debug(
                    "dispatching_redis_event",
                    event_type=event_type,
                    event_id=event.event_id,
                    handler_count=len(handlers),
                )
                tasks = [self._run_handler(handler, event) for handler in handlers]
                await asyncio.gather(*tasks, return_exceptions=True)
            else:
                logger.debug(
                    "no_handlers_for_redis_event",
                    event_type=event_type,
                    event_id=event.event_id,
                )

        except Exception as e:
            logger.error(
                "redis_message_handling_error",
                error=str(e),
                exc_info=True,
            )

    async def _run_handler(self, handler: EventHandler, event: Event) -> None:
        """Run a single event handler with error handling.

        Args:
            handler: Event handler function
            event: Event to handle
        """
        try:
            await handler(event)
            logger.debug(
                "handler_completed_redis",
                handler=handler.__name__,
                event_id=event.event_id,
            )
        except Exception as e:
            logger.error(
                "handler_error_redis",
                handler=handler.__name__,
                event_id=event.event_id,
                error=str(e),
                exc_info=True,
            )
