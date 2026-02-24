"""Unit tests for MCP Orchestrator streaming progress updates."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.mcp_orchestrator import MCPOrchestrator


class TestMCPOrchestratorProgressStreaming:
    """Test progress callback and streaming functionality."""

    @pytest.fixture
    def mock_mcp_client(self):
        """Mock MCP client."""
        client = AsyncMock()
        client.list_servers = AsyncMock(return_value={
            "servers": [
                {
                    "name": "product_retrieval_server",
                    "path": "/product_retrieval",
                    "roles": ["product_retrieval"],
                    "category": "product",
                    "priority": "high"
                }
            ],
            "total_count": 1
        })
        client.list_tools_with_schemas = AsyncMock(return_value=[
            {
                "name": "get_product_docs",
                "description": "Retrieve product documents",
                "inputSchema": {"type": "object"}
            }
        ])
        client.call_tool = AsyncMock(return_value={
            "content": [{"type": "text", "text": "Product result"}]
        })
        return client

    @pytest.fixture
    def orchestrator(self, mock_mcp_client):
        """Create orchestrator with mocked dependencies."""
        return MCPOrchestrator(
            mcp_client=mock_mcp_client,
            openai_api_key="test-key"
        )

    @pytest.mark.asyncio
    async def test_progress_callback_emits_all_steps(self, orchestrator, mock_mcp_client):
        """Test that progress callback is called for all major steps."""
        progress_messages = []

        def progress_callback(message: str):
            progress_messages.append(message)

        orchestrator.set_progress_callback(progress_callback)

        with patch.object(orchestrator.openai.chat.completions, 'create', new_callable=AsyncMock) as mock_openai:
            mock_openai.side_effect = [
                # Server selection
                MagicMock(choices=[MagicMock(message=MagicMock(content="/product_retrieval"))]),
                # Tool selection
                MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
                    "tool_name": "get_product_docs",
                    "arguments": {"inputs": {"query": "test"}}
                })))]),
                # Result formatting
                MagicMock(choices=[MagicMock(message=MagicMock(content="Formatted result"))])
            ]

            await orchestrator.query("test query")

            # Verify all expected progress messages were emitted
            expected_messages = [
                "🔍 Discovering available servers...",
                "🤖 AI selecting best server for your query...",
                "✓ Selected server: /product_retrieval",
                "🔧 Discovering available tools...",
                "✓ Found 1 available tools",
                "🧠 Analyzing query and selecting best tool...",
                "✓ Selected tool: get_product_docs",
                "⚡ Calling tool: get_product_docs...",
                "✓ Received response from server",
                "✨ Formatting response for you...",
                "✅ Complete!"
            ]

            assert len(progress_messages) == len(expected_messages)
            for i, expected in enumerate(expected_messages):
                assert progress_messages[i] == expected

    @pytest.mark.asyncio
    async def test_progress_callback_with_preferred_server(self, orchestrator, mock_mcp_client):
        """Test progress messages when using preferred server (skips LLM selection)."""
        progress_messages = []

        def progress_callback(message: str):
            progress_messages.append(message)

        orchestrator.set_progress_callback(progress_callback)

        with patch.object(orchestrator.openai.chat.completions, 'create', new_callable=AsyncMock) as mock_openai:
            mock_openai.side_effect = [
                # Tool selection only (no server selection)
                MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
                    "tool_name": "get_product_docs",
                    "arguments": {"inputs": {"query": "test"}}
                })))]),
                # Result formatting
                MagicMock(choices=[MagicMock(message=MagicMock(content="Formatted result"))])
            ]

            await orchestrator.query("test query", preferred_server="/product_retrieval")

            # Should skip server discovery, use preferred server
            assert any("Using preferred server" in msg for msg in progress_messages)
            assert not any("AI selecting best server" in msg for msg in progress_messages)

    @pytest.mark.asyncio
    async def test_progress_callback_not_called_without_setting(self, orchestrator, mock_mcp_client):
        """Test that orchestrator works without progress callback set."""
        # Don't set progress callback
        with patch.object(orchestrator.openai.chat.completions, 'create', new_callable=AsyncMock) as mock_openai:
            mock_openai.side_effect = [
                MagicMock(choices=[MagicMock(message=MagicMock(content="/product_retrieval"))]),
                MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
                    "tool_name": "get_product_docs",
                    "arguments": {"inputs": {"query": "test"}}
                })))]),
                MagicMock(choices=[MagicMock(message=MagicMock(content="Formatted result"))])
            ]

            # Should not raise error even without callback
            result = await orchestrator.query("test query")

            assert result["tool_name"] == "get_product_docs"

    @pytest.mark.asyncio
    async def test_emit_progress_logs_message(self, orchestrator):
        """Test that _emit_progress logs messages even without callback."""
        with patch('app.services.mcp_orchestrator.logger') as mock_logger:
            await orchestrator._emit_progress("Test message")

            # Verify logger was called
            mock_logger.info.assert_called_once_with("mcp_progress", message="Test message")

    @pytest.mark.asyncio
    async def test_progress_messages_include_emojis(self, orchestrator, mock_mcp_client):
        """Test that progress messages include appropriate emojis for UX."""
        progress_messages = []

        def progress_callback(message: str):
            progress_messages.append(message)

        orchestrator.set_progress_callback(progress_callback)

        with patch.object(orchestrator.openai.chat.completions, 'create', new_callable=AsyncMock) as mock_openai:
            mock_openai.side_effect = [
                MagicMock(choices=[MagicMock(message=MagicMock(content="/product_retrieval"))]),
                MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
                    "tool_name": "get_product_docs",
                    "arguments": {"inputs": {"query": "test"}}
                })))]),
                MagicMock(choices=[MagicMock(message=MagicMock(content="Formatted result"))])
            ]

            await orchestrator.query("test query")

            # Check for expected emojis
            emoji_messages = [msg for msg in progress_messages if any(emoji in msg for emoji in ["🔍", "🤖", "✓", "🔧", "🧠", "⚡", "✨", "✅"])]
            assert len(emoji_messages) > 0  # Should have multiple emoji messages

    @pytest.mark.asyncio
    async def test_progress_callback_called_in_order(self, orchestrator, mock_mcp_client):
        """Test that progress messages are emitted in correct sequential order."""
        progress_messages = []

        def progress_callback(message: str):
            progress_messages.append(message)

        orchestrator.set_progress_callback(progress_callback)

        with patch.object(orchestrator.openai.chat.completions, 'create', new_callable=AsyncMock) as mock_openai:
            mock_openai.side_effect = [
                MagicMock(choices=[MagicMock(message=MagicMock(content="/product_retrieval"))]),
                MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
                    "tool_name": "get_product_docs",
                    "arguments": {"inputs": {"query": "test"}}
                })))]),
                MagicMock(choices=[MagicMock(message=MagicMock(content="Formatted result"))])
            ]

            await orchestrator.query("test query")

            # Verify logical order: discover -> select -> call -> format -> complete
            assert progress_messages[0].startswith("🔍 Discovering")
            assert any("selecting" in msg.lower() for msg in progress_messages[1:3])
            assert any("Calling tool" in msg for msg in progress_messages)
            assert any("Formatting" in msg for msg in progress_messages)
            assert progress_messages[-1] == "✅ Complete!"
