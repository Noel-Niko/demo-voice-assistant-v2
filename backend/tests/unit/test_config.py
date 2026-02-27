"""Tests for configuration settings."""
import pytest

from app.config import Settings


def test_mcp_discovery_endpoint_default(monkeypatch):
    """Test MCP_DISCOVERY_ENDPOINT has correct default value."""
    monkeypatch.delenv("MCP_DISCOVERY_ENDPOINT", raising=False)
    settings = Settings()
    assert settings.MCP_DISCOVERY_ENDPOINT == "/tools/discovery"


def test_mcp_discovery_endpoint_from_env(monkeypatch):
    """Test MCP_DISCOVERY_ENDPOINT can be overridden via environment variable."""
    monkeypatch.setenv("MCP_DISCOVERY_ENDPOINT", "/custom/discover")
    settings = Settings()
    assert settings.MCP_DISCOVERY_ENDPOINT == "/custom/discover"


def test_mcp_discovery_endpoint_absolute_url(monkeypatch):
    """Test MCP_DISCOVERY_ENDPOINT supports absolute URLs."""
    monkeypatch.setenv("MCP_DISCOVERY_ENDPOINT", "https://other-server.com/api/discover")
    settings = Settings()
    assert settings.MCP_DISCOVERY_ENDPOINT == "https://other-server.com/api/discover"


def test_mcp_discovery_endpoint_with_other_mcp_settings(monkeypatch):
    """Test MCP_DISCOVERY_ENDPOINT works alongside other MCP settings."""
    monkeypatch.setenv("MCP_INGRESS_URL", "http://localhost:8080")
    monkeypatch.setenv("MCP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("MCP_DISCOVERY_ENDPOINT", "/custom/api/servers")

    settings = Settings()

    assert settings.MCP_INGRESS_URL == "http://localhost:8080"
    assert settings.MCP_SECRET_KEY == "test-secret"
    assert settings.MCP_DISCOVERY_ENDPOINT == "/custom/api/servers"
