"""Service factory for creating backing service implementations.

Creates EventBus and Cache instances based on configuration.
Follows 12-factor #4: Backing services as attached resources.

Without REDIS_URL: Creates InMemory implementations (local dev)
With REDIS_URL: Creates Redis implementations (production)
"""
from app.config import settings
from app.services.event_bus import EventBus, InMemoryEventBus, RedisEventBus
from app.services.cache import Cache, InMemoryCache, RedisCache

import structlog

logger = structlog.get_logger(__name__)


def create_event_bus() -> EventBus:
    """Factory: Create event bus based on configuration.

    Returns InMemoryEventBus if REDIS_URL not set (local dev).
    Returns RedisEventBus if REDIS_URL set (production).

    Returns:
        EventBus implementation instance

    Example:
        # REDIS_URL not set
        bus = create_event_bus()  # Returns InMemoryEventBus

        # export REDIS_URL=redis://localhost:6379/0
        bus = create_event_bus()  # Returns RedisEventBus
    """
    if settings.REDIS_URL:
        logger.info(
            "event_bus_created",
            type="redis",
            url=settings.REDIS_URL,
            production_ready=True
        )
        return RedisEventBus(settings.REDIS_URL)
    else:
        logger.warning(
            "event_bus_created",
            type="in_memory",
            production_ready=False,
            warning="State not shared across workers. Set REDIS_URL for production."
        )
        return InMemoryEventBus()


def create_cache() -> Cache:
    """Factory: Create cache based on configuration.

    Returns InMemoryCache if REDIS_URL not set (local dev).
    Returns RedisCache if REDIS_URL set (production).

    Returns:
        Cache implementation instance

    Example:
        # REDIS_URL not set
        cache = create_cache()  # Returns InMemoryCache

        # export REDIS_URL=redis://localhost:6379/0
        cache = create_cache()  # Returns RedisCache
    """
    if settings.REDIS_URL:
        logger.info(
            "cache_created",
            type="redis",
            url=settings.REDIS_URL,
            production_ready=True
        )
        return RedisCache(settings.REDIS_URL)
    else:
        logger.warning(
            "cache_created",
            type="in_memory",
            production_ready=False,
            warning="State not shared across workers. Set REDIS_URL for production."
        )
        return InMemoryCache()
