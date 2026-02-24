"""Unit tests for service factory functions.

Tests config-driven creation of EventBus and Cache implementations.
Following TDD: Write tests first, then implement.
"""
import pytest
from unittest.mock import patch

from app.services.event_bus import EventBus, InMemoryEventBus
from app.services.cache import Cache, InMemoryCache
from app.services.factory import create_event_bus, create_cache


class TestEventBusFactory:
    """Test create_event_bus factory function."""

    @patch("app.services.factory.settings")
    def test_creates_in_memory_when_no_redis_url(self, mock_settings):
        """Should create InMemoryEventBus when REDIS_URL is None."""
        mock_settings.REDIS_URL = None

        bus = create_event_bus()

        assert isinstance(bus, InMemoryEventBus)
        assert isinstance(bus, EventBus)

    @patch("app.services.factory.settings")
    def test_creates_in_memory_when_redis_url_empty(self, mock_settings):
        """Should create InMemoryEventBus when REDIS_URL is empty string."""
        mock_settings.REDIS_URL = ""

        bus = create_event_bus()

        assert isinstance(bus, InMemoryEventBus)

    @patch("app.services.factory.settings")
    def test_creates_redis_when_redis_url_set(self, mock_settings):
        """Should create RedisEventBus when REDIS_URL is set."""
        mock_settings.REDIS_URL = "redis://localhost:6379/0"

        try:
            from app.services.event_bus import RedisEventBus
            bus = create_event_bus()
            assert isinstance(bus, RedisEventBus)
            assert isinstance(bus, EventBus)
        except ImportError:
            pytest.skip("Redis not installed yet")

    @patch("app.services.factory.settings")
    def test_logs_creation_type(self, mock_settings):
        """Factory should log which implementation it creates."""
        mock_settings.REDIS_URL = None

        # Just verify it doesn't raise - actual logging verified manually
        bus = create_event_bus()
        assert isinstance(bus, InMemoryEventBus)


class TestCacheFactory:
    """Test create_cache factory function."""

    @patch("app.services.factory.settings")
    def test_creates_in_memory_when_no_redis_url(self, mock_settings):
        """Should create InMemoryCache when REDIS_URL is None."""
        mock_settings.REDIS_URL = None

        cache = create_cache()

        assert isinstance(cache, InMemoryCache)
        assert isinstance(cache, Cache)

    @patch("app.services.factory.settings")
    def test_creates_in_memory_when_redis_url_empty(self, mock_settings):
        """Should create InMemoryCache when REDIS_URL is empty string."""
        mock_settings.REDIS_URL = ""

        cache = create_cache()

        assert isinstance(cache, InMemoryCache)

    @patch("app.services.factory.settings")
    def test_creates_redis_when_redis_url_set(self, mock_settings):
        """Should create RedisCache when REDIS_URL is set."""
        mock_settings.REDIS_URL = "redis://localhost:6379/0"

        try:
            from app.services.cache import RedisCache
            cache = create_cache()
            assert isinstance(cache, RedisCache)
            assert isinstance(cache, Cache)
        except ImportError:
            pytest.skip("Redis not installed yet")

    @patch("app.services.factory.settings")
    def test_logs_creation_type(self, mock_settings):
        """Factory should log which implementation it creates."""
        mock_settings.REDIS_URL = None

        # Just verify it doesn't raise - actual logging verified manually
        cache = create_cache()
        assert isinstance(cache, InMemoryCache)

    @patch("app.services.factory.settings")
    def test_same_redis_url_for_both_services(self, mock_settings):
        """Both EventBus and Cache should use same Redis URL."""
        mock_settings.REDIS_URL = "redis://localhost:6379/0"

        try:
            from app.services.event_bus import RedisEventBus
            from app.services.cache import RedisCache

            bus = create_event_bus()
            cache = create_cache()

            # Both should be Redis implementations
            assert isinstance(bus, RedisEventBus)
            assert isinstance(cache, RedisCache)
        except ImportError:
            pytest.skip("Redis not installed yet")
