"""Unit tests for Cache abstraction and implementations.

Tests the abstract Cache interface and both InMemory and Redis implementations.
Following TDD: Write tests first, then implement.
"""
import asyncio
import pytest

from app.services.cache import Cache, InMemoryCache


class TestCacheAbstraction:
    """Test that Cache is an abstract base class with required methods."""

    def test_cache_is_abstract(self):
        """Cache should be abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            Cache()  # Should raise: Can't instantiate abstract class

    def test_cache_has_abstract_methods(self):
        """Cache should define abstract methods."""
        assert hasattr(Cache, 'get')
        assert hasattr(Cache, 'set')
        assert hasattr(Cache, 'delete')
        assert hasattr(Cache, 'close')


class TestInMemoryCache:
    """Test InMemoryCache implementation."""

    @pytest.mark.asyncio
    async def test_inherits_from_cache(self):
        """InMemoryCache should inherit from Cache."""
        cache = InMemoryCache()
        assert isinstance(cache, Cache)

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = InMemoryCache()

        await cache.set("key1", "value1")
        result = await cache.get("key1")

        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self):
        """Get should return None for nonexistent key."""
        cache = InMemoryCache()
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_complex_data(self):
        """Cache should handle complex data structures."""
        cache = InMemoryCache()

        data = {
            "name": "Test",
            "count": 42,
            "nested": {"key": "value"},
            "list": [1, 2, 3]
        }

        await cache.set("complex", data)
        result = await cache.get("complex")

        assert result == data
        assert result["nested"]["key"] == "value"
        assert result["list"] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_delete(self):
        """Delete should remove key from cache."""
        cache = InMemoryCache()

        await cache.set("key1", "value1")
        await cache.delete("key1")
        result = await cache.get("key1")

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(self):
        """Delete should not raise error for nonexistent key."""
        cache = InMemoryCache()
        # Should not raise
        await cache.delete("nonexistent")

    @pytest.mark.asyncio
    async def test_overwrite_existing_key(self):
        """Set should overwrite existing values."""
        cache = InMemoryCache()

        await cache.set("key1", "value1")
        await cache.set("key1", "value2")
        result = await cache.get("key1")

        assert result == "value2"

    @pytest.mark.asyncio
    async def test_close_no_error(self):
        """Close should not raise error."""
        cache = InMemoryCache()
        await cache.set("key1", "value1")
        await cache.close()
        # InMemory cache doesn't need cleanup, but should not raise


class TestRedisCache:
    """Test RedisCache implementation (requires Redis)."""

    @pytest.mark.asyncio
    async def test_inherits_from_cache(self):
        """RedisCache should inherit from Cache."""
        try:
            from app.services.cache import RedisCache
            cache = RedisCache("redis://localhost:6379/0")
            assert isinstance(cache, Cache)
            await cache.close()
        except ImportError:
            pytest.skip("Redis not installed yet")

    @pytest.mark.asyncio
    async def test_set_and_get_with_redis(self):
        """Test Redis cache set and get."""
        try:
            from app.services.cache import RedisCache
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

        cache = RedisCache("redis://localhost:6379/0")

        await cache.set("test_key", {"data": "value"})
        result = await cache.get("test_key")

        await cache.close()

        assert result == {"data": "value"}

    @pytest.mark.asyncio
    async def test_ttl_with_redis(self):
        """Test TTL (time-to-live) functionality."""
        try:
            from app.services.cache import RedisCache
        except ImportError:
            pytest.skip("Redis not installed yet")

        try:
            import redis.asyncio as aioredis
            test_redis = await aioredis.from_url("redis://localhost:6379/0")
            await test_redis.ping()
            await test_redis.close()
        except Exception:
            pytest.skip("Redis not available")

        cache = RedisCache("redis://localhost:6379/0")

        # Set with 1 second TTL
        await cache.set("ttl_key", "value", ttl=1)

        # Should exist immediately
        result = await cache.get("ttl_key")
        assert result == "value"

        # Wait for expiration
        await asyncio.sleep(1.5)

        # Should be gone
        result = await cache.get("ttl_key")
        assert result is None

        await cache.close()

    @pytest.mark.asyncio
    async def test_delete_with_redis(self):
        """Test delete operation with Redis."""
        try:
            from app.services.cache import RedisCache
        except ImportError:
            pytest.skip("Redis not installed yet")

        try:
            import redis.asyncio as aioredis
            test_redis = await aioredis.from_url("redis://localhost:6379/0")
            await test_redis.ping()
            await test_redis.close()
        except Exception:
            pytest.skip("Redis not available")

        cache = RedisCache("redis://localhost:6379/0")

        await cache.set("delete_key", "value")
        await cache.delete("delete_key")
        result = await cache.get("delete_key")

        await cache.close()

        assert result is None

    @pytest.mark.asyncio
    async def test_shared_state_across_instances(self):
        """Test that Redis cache shares state across instances (simulating pods)."""
        try:
            from app.services.cache import RedisCache
        except ImportError:
            pytest.skip("Redis not installed yet")

        try:
            import redis.asyncio as aioredis
            test_redis = await aioredis.from_url("redis://localhost:6379/0")
            await test_redis.ping()
            await test_redis.close()
        except Exception:
            pytest.skip("Redis not available")

        # Create two cache instances (simulating different pods)
        cache1 = RedisCache("redis://localhost:6379/0")
        cache2 = RedisCache("redis://localhost:6379/0")

        # Set in cache1
        await cache1.set("shared_key", {"pod": "1"})

        # Get from cache2
        result = await cache2.get("shared_key")

        await cache1.close()
        await cache2.close()

        # Should see data from cache1
        assert result == {"pod": "1"}
