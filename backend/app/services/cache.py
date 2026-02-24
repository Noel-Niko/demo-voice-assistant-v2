"""Cache abstraction for state management.

Provides abstract Cache interface with InMemory and Redis implementations.
Follows Dependency Inversion Principle for swappable backing services.

InMemoryCache: Local dev/demo (single process only, state NOT shared)
RedisCache: Production-ready (shared state across pods/workers)
"""
import json
from abc import ABC, abstractmethod
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class Cache(ABC):
    """Abstract base class for cache implementations.

    Follows Dependency Inversion Principle - depend on abstractions.
    Allows swapping implementations via configuration (12-factor #4).
    """

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable for Redis)
            ttl: Time-to-live in seconds (None = no expiration)
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete key from cache.

        Args:
            key: Cache key to delete
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Cleanup resources and close connections.

        Should be called during application shutdown.
        """
        pass


class InMemoryCache(Cache):
    """In-memory cache implementation.

    WARNING: State is NOT shared across workers/pods.
    Suitable for local dev/demo only.

    Violates 12-factor #6 in multi-worker environments.
    Use RedisCache for production.
    """

    def __init__(self) -> None:
        """Initialize in-memory cache."""
        self._store: dict[str, Any] = {}
        logger.info("in_memory_cache_initialized")

    async def get(self, key: str) -> Optional[Any]:
        """Get value from in-memory store.

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        value = self._store.get(key)
        logger.debug("cache_get", key=key, found=value is not None)
        return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in in-memory store.

        Note: TTL not implemented for simplicity in local dev.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Ignored for in-memory cache
        """
        self._store[key] = value
        logger.debug("cache_set", key=key, has_ttl=ttl is not None)

    async def delete(self, key: str) -> None:
        """Delete key from in-memory store.

        Args:
            key: Cache key
        """
        self._store.pop(key, None)
        logger.debug("cache_delete", key=key)

    async def close(self) -> None:
        """No cleanup needed for in-memory cache."""
        logger.info("in_memory_cache_closed")


class RedisCache(Cache):
    """Production-ready cache using Redis.

    State shared across all pods/workers.
    Follows 12-factor #6: Stateless processes (state in backing service).
    """

    def __init__(self, redis_url: str) -> None:
        """Initialize Redis cache.

        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379/0)
        """
        self._redis_url = redis_url
        self._redis = None
        self._initialized = False

    async def _ensure_connected(self) -> None:
        """Lazy initialization of Redis connection."""
        if self._initialized:
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
        self._initialized = True
        logger.info("redis_cache_initialized", redis_url=self._redis_url)

    async def get(self, key: str) -> Optional[Any]:
        """Get value from Redis.

        Args:
            key: Cache key

        Returns:
            Deserialized value or None
        """
        await self._ensure_connected()

        value_json = await self._redis.get(key)
        if value_json is None:
            logger.debug("cache_get_redis", key=key, found=False)
            return None

        try:
            value = json.loads(value_json)
            logger.debug("cache_get_redis", key=key, found=True)
            return value
        except json.JSONDecodeError as e:
            logger.error("cache_get_json_decode_error", key=key, error=str(e))
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in Redis.

        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable)
            ttl: Time-to-live in seconds (None = no expiration)

        Raises:
            TypeError: If value is not JSON-serializable
        """
        await self._ensure_connected()

        try:
            value_json = json.dumps(value)
        except TypeError as e:
            logger.error("cache_set_json_encode_error", key=key, error=str(e))
            raise TypeError(f"Value must be JSON-serializable: {e}")

        if ttl:
            await self._redis.setex(key, ttl, value_json)
            logger.debug("cache_set_redis", key=key, ttl=ttl)
        else:
            await self._redis.set(key, value_json)
            logger.debug("cache_set_redis", key=key, ttl=None)

    async def delete(self, key: str) -> None:
        """Delete key from Redis.

        Args:
            key: Cache key
        """
        await self._ensure_connected()

        await self._redis.delete(key)
        logger.debug("cache_delete_redis", key=key)

    async def close(self) -> None:
        """Close Redis connection.

        Should be called during application shutdown.
        """
        if self._redis:
            await self._redis.close()
            logger.info("redis_cache_closed")
