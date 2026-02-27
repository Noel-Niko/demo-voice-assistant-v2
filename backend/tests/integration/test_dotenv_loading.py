"""Integration tests for .env file loading."""
import os
import tempfile
from pathlib import Path

import pytest
from dotenv import load_dotenv

from app.config import Settings


def test_dotenv_loads_into_settings(tmp_path, monkeypatch):
    """Test that .env values are loaded into Settings."""
    # Create temporary .env file
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=test-key-from-dotenv\n"
        "MCP_DISCOVERY_ENDPOINT=/custom/from/dotenv\n"
    )

    # Clear any existing env vars
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MCP_DISCOVERY_ENDPOINT", raising=False)

    # Load .env file
    load_dotenv(dotenv_path=env_file, override=False)

    # Create settings (should pick up values from environment)
    settings = Settings()

    assert settings.OPENAI_API_KEY == "test-key-from-dotenv"
    assert settings.MCP_DISCOVERY_ENDPOINT == "/custom/from/dotenv"


def test_environment_variables_override_dotenv(tmp_path, monkeypatch):
    """Test that environment variables take precedence over .env (12-factor compliance)."""
    # Create temporary .env file
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=dotenv-key\n"
        "MCP_DISCOVERY_ENDPOINT=/dotenv/endpoint\n"
    )

    # Set environment variables
    monkeypatch.setenv("OPENAI_API_KEY", "env-var-key")
    monkeypatch.setenv("MCP_DISCOVERY_ENDPOINT", "/env/var/endpoint")

    # Load .env file with override=False (environment vars should win)
    load_dotenv(dotenv_path=env_file, override=False)

    # Create settings
    settings = Settings()

    # Environment variables should take precedence
    assert settings.OPENAI_API_KEY == "env-var-key"
    assert settings.MCP_DISCOVERY_ENDPOINT == "/env/var/endpoint"


def test_dotenv_override_false_behavior(tmp_path, monkeypatch):
    """Test that load_dotenv(override=False) doesn't overwrite existing env vars."""
    # Create temporary .env file
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_VAR=from-dotenv\n")

    # Set environment variable first
    monkeypatch.setenv("TEST_VAR", "from-env")

    # Load .env with override=False
    load_dotenv(dotenv_path=env_file, override=False)

    # Environment variable should remain unchanged
    assert os.environ["TEST_VAR"] == "from-env"


def test_dotenv_missing_file_no_error(tmp_path, monkeypatch):
    """Test that load_dotenv doesn't error if .env file doesn't exist."""
    non_existent_file = tmp_path / ".env.does.not.exist"

    # Clear any existing env vars for clean test
    monkeypatch.delenv("MCP_DISCOVERY_ENDPOINT", raising=False)

    # Should not raise error
    load_dotenv(dotenv_path=non_existent_file, override=False)

    # Should be able to create settings with defaults
    settings = Settings()
    assert settings.MCP_DISCOVERY_ENDPOINT == "/tools/discovery"


def test_dotenv_partial_config(tmp_path, monkeypatch):
    """Test that .env can provide partial configuration with defaults."""
    # Create .env with only some variables
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=test-key\n"
        # MCP_DISCOVERY_ENDPOINT not set - should use default
    )

    # Clear env vars
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MCP_DISCOVERY_ENDPOINT", raising=False)

    # Load .env
    load_dotenv(dotenv_path=env_file, override=False)

    # Create settings
    settings = Settings()

    # Should have value from .env
    assert settings.OPENAI_API_KEY == "test-key"
    # Should have default value
    assert settings.MCP_DISCOVERY_ENDPOINT == "/tools/discovery"


def test_dotenv_with_mcp_settings(tmp_path, monkeypatch):
    """Test loading all MCP-related settings from .env."""
    # Create .env with all MCP settings
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MCP_INGRESS_URL=http://test-mcp-server:8080\n"
        "MCP_SECRET_KEY=test-secret\n"
        "MCP_DISCOVERY_ENDPOINT=/custom/discovery\n"
    )

    # Clear env vars
    monkeypatch.delenv("MCP_INGRESS_URL", raising=False)
    monkeypatch.delenv("MCP_SECRET_KEY", raising=False)
    monkeypatch.delenv("MCP_DISCOVERY_ENDPOINT", raising=False)

    # Load .env
    load_dotenv(dotenv_path=env_file, override=False)

    # Create settings
    settings = Settings()

    # All MCP settings should be loaded from .env
    assert settings.MCP_INGRESS_URL == "http://test-mcp-server:8080"
    assert settings.MCP_SECRET_KEY == "test-secret"
    assert settings.MCP_DISCOVERY_ENDPOINT == "/custom/discovery"
