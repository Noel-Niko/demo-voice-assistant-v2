"""Unit tests for EventBus abstraction and implementations.

Tests the abstract EventBus interface and both InMemory and Redis implementations.
Following TDD: Write tests first, then implement.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.event_bus import Event, EventBus, InMemoryEventBus


class TestEventBusAbstraction:
    """Test that EventBus is an abstract base class with required methods."""

    def test_event_bus_is_abstract(self):
        """EventBus should be abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            EventBus()  # Should raise: Can't instantiate abstract class

    def test_event_bus_has_abstract_methods(self):
        """EventBus should define abstract methods."""
        # Check that required methods exist as abstract
        assert hasattr(EventBus, 'publish')
        assert hasattr(EventBus, 'subscribe')
        assert hasattr(EventBus, 'start')
        assert hasattr(EventBus, 'stop')


class TestInMemoryEventBus:
    """Test InMemoryEventBus implementation."""

    @pytest.mark.asyncio
    async def test_inherits_from_event_bus(self):
        """InMemoryEventBus should inherit from EventBus."""
        bus = InMemoryEventBus()
        assert isinstance(bus, EventBus)

    @pytest.mark.asyncio
    async def test_publish_subscribe_flow(self):
        """Test basic publish/subscribe pattern."""
        bus = InMemoryEventBus()
        await bus.start()

        received_events = []

        async def handler(event: Event):
            received_events.append(event)

        # Subscribe handler
        bus.subscribe("test.event", handler)

        # Publish event
        event = Event.create(
            event_type="test.event",
            source="test",
            data={"message": "hello"}
        )
        await bus.publish(event)

        # Wait for processing
        await asyncio.sleep(0.1)

        await bus.stop()

        # Verify handler received event
        assert len(received_events) == 1
        assert received_events[0].event_type == "test.event"
        assert received_events[0].data["message"] == "hello"

    @pytest.mark.asyncio
    async def test_multiple_handlers_same_event(self):
        """Multiple handlers should receive the same event."""
        bus = InMemoryEventBus()
        await bus.start()

        handler1_calls = []
        handler2_calls = []

        async def handler1(event: Event):
            handler1_calls.append(event)

        async def handler2(event: Event):
            handler2_calls.append(event)

        bus.subscribe("test.event", handler1)
        bus.subscribe("test.event", handler2)

        event = Event.create("test.event", "test", {"data": "value"})
        await bus.publish(event)

        await asyncio.sleep(0.1)
        await bus.stop()

        assert len(handler1_calls) == 1
        assert len(handler2_calls) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        """Handler should not receive events after unsubscribe."""
        bus = InMemoryEventBus()
        await bus.start()

        received = []

        async def handler(event: Event):
            received.append(event)

        bus.subscribe("test.event", handler)
        bus.unsubscribe("test.event", handler)

        event = Event.create("test.event", "test", {})
        await bus.publish(event)

        await asyncio.sleep(0.1)
        await bus.stop()

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self):
        """Test proper startup and shutdown."""
        bus = InMemoryEventBus()

        # Should not be running initially
        assert not bus._running

        await bus.start()
        assert bus._running

        await bus.stop()
        assert not bus._running


class TestRedisEventBus:
    """Test RedisEventBus implementation (requires Redis)."""

    @pytest.mark.asyncio
    async def test_inherits_from_event_bus(self):
        """RedisEventBus should inherit from EventBus."""
        # Import here to avoid import error if redis not installed yet
        try:
            from app.services.event_bus import RedisEventBus
            bus = RedisEventBus("redis://localhost:6379/0")
            assert isinstance(bus, EventBus)
            await bus.stop()  # Cleanup
        except ImportError:
            pytest.skip("Redis not installed yet - test will pass after implementation")

    @pytest.mark.asyncio
    async def test_publish_subscribe_with_redis(self):
        """Test Redis pub/sub works across 'pods' (simulated with 2 bus instances)."""
        try:
            from app.services.event_bus import RedisEventBus
        except ImportError:
            pytest.skip("Redis not installed yet")

        # Skip if Redis not available
        try:
            import redis.asyncio as aioredis
            test_redis = await aioredis.from_url("redis://localhost:6379/0")
            await test_redis.ping()
            await test_redis.close()
        except Exception:
            pytest.skip("Redis not available at localhost:6379")

        # Create two bus instances (simulating different workers/pods)
        bus1 = RedisEventBus("redis://localhost:6379/0")
        bus2 = RedisEventBus("redis://localhost:6379/0")

        await bus1.start()
        await bus2.start()

        received_on_bus2 = []

        async def handler(event: Event):
            received_on_bus2.append(event)

        # Subscribe on bus2 (synchronous call, no await needed)
        bus2.subscribe("test.event", handler)
        await asyncio.sleep(0.5)  # Wait for subscription to register in Redis

        # Publish on bus1
        event = Event.create("test.event", "test", {"cross_pod": True})
        await bus1.publish(event)

        # Wait for message propagation
        await asyncio.sleep(0.3)

        await bus1.stop()
        await bus2.stop()

        # Verify cross-pod delivery
        assert len(received_on_bus2) == 1
        assert received_on_bus2[0].data["cross_pod"] is True

    @pytest.mark.asyncio
    async def test_close_cleanup(self):
        """Test proper cleanup of Redis connections."""
        try:
            from app.services.event_bus import RedisEventBus
        except ImportError:
            pytest.skip("Redis not installed yet")

        try:
            import redis.asyncio as aioredis
            test_redis = await aioredis.from_url("redis://localhost:6379/0")
            await test_redis.ping()
            await test_redis.close()
        except Exception:
            pytest.skip("Redis not available")

        bus = RedisEventBus("redis://localhost:6379/0")
        await bus.start()
        await bus.stop()

        # Should be able to start/stop multiple times
        await bus.start()
        await bus.stop()
