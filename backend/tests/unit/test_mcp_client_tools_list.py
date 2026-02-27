"""Unit tests for MCP Client tools/list method and SSE parsing."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.mcp_client import MCPClient
from app.services.mcp_token_manager import MCPTokenManager


class TestMCPClientToolsList:
    """Test MCP Client's tools/list JSON-RPC method."""

    @pytest.fixture
    def token_manager(self):
        """Mock token manager."""
        manager = MagicMock(spec=MCPTokenManager)
        manager.get_valid_token = MagicMock(return_value="test-token")
        return manager

    @pytest.fixture
    def mcp_client(self, token_manager):
        """Create MCP client with mocked dependencies."""
        return MCPClient(
            base_url="https://test-mcp.example.com",
            token_manager=token_manager,
            timeout=30.0,
            discovery_endpoint="/tools/discovery"  # Explicit for clarity
        )

    @pytest.mark.asyncio
    async def test_list_tools_sends_correct_jsonrpc_request(self, mcp_client):
        """Test that list_tools_with_schemas sends correct JSON-RPC request."""
        mock_response_text = """event: message
data: {"jsonrpc":"2.0","id":"123","result":{"tools":[{"name":"test_tool","description":"Test","inputSchema":{}}]}}

data: [DONE]
"""

        with patch.object(mcp_client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response_text

            tools = await mcp_client.list_tools_with_schemas("/product_retrieval")

            # Verify JSON-RPC request structure
            call_args = mock_request.call_args
            rpc_request = call_args.kwargs['json_data']

            assert rpc_request["jsonrpc"] == "2.0"
            assert rpc_request["method"] == "tools/list"
            assert "id" in rpc_request
            assert rpc_request["params"] == {}

    @pytest.mark.asyncio
    async def test_list_tools_returns_tools_array(self, mcp_client):
        """Test that list_tools_with_schemas extracts tools array from result."""
        mock_response_text = """data: {"jsonrpc":"2.0","id":"123","result":{"tools":[{"name":"tool1"},{"name":"tool2"}]}}

data: [DONE]
"""

        with patch.object(mcp_client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response_text

            tools = await mcp_client.list_tools_with_schemas("/product_retrieval")

            assert isinstance(tools, list)
            assert len(tools) == 2
            assert tools[0]["name"] == "tool1"
            assert tools[1]["name"] == "tool2"

    @pytest.mark.asyncio
    async def test_list_tools_with_input_schemas(self, mcp_client):
        """Test parsing tools with complete inputSchemas."""
        # JSON must be on single line for SSE parsing
        mock_response_text = """data: {"jsonrpc":"2.0","id":"123","result":{"tools":[{"name":"get_product_docs","description":"Retrieve product documents","inputSchema":{"type":"object","properties":{"inputs":{"type":"object","properties":{"query":{"type":"string"},"vector_store":{"type":"string"}}}}}}]}}

data: [DONE]
"""

        with patch.object(mcp_client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response_text

            tools = await mcp_client.list_tools_with_schemas("/product_retrieval")

            assert len(tools) == 1
            tool = tools[0]
            assert tool["name"] == "get_product_docs"
            assert tool["description"] == "Retrieve product documents"
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"
            assert "properties" in tool["inputSchema"]

    @pytest.mark.asyncio
    async def test_list_tools_handles_empty_tools(self, mcp_client):
        """Test handling response with no tools."""
        mock_response_text = """data: {"jsonrpc":"2.0","id":"123","result":{"tools":[]}}

data: [DONE]
"""

        with patch.object(mcp_client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response_text

            tools = await mcp_client.list_tools_with_schemas("/product_retrieval")

            assert isinstance(tools, list)
            assert len(tools) == 0

    @pytest.mark.asyncio
    async def test_list_tools_normalizes_server_path(self, mcp_client):
        """Test that server path is normalized to include leading slash."""
        mock_response_text = """data: {"jsonrpc":"2.0","id":"123","result":{"tools":[]}}

data: [DONE]
"""

        with patch.object(mcp_client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response_text

            # Pass server_path without leading slash
            await mcp_client.list_tools_with_schemas("product_retrieval")

            # Verify URL was constructed with leading slash
            call_args = mock_request.call_args
            url = call_args.args[1]
            assert url == "https://test-mcp.example.com/product_retrieval/mcp"

    @pytest.mark.asyncio
    async def test_list_tools_handles_errors_gracefully(self, mcp_client):
        """Test that errors return empty list instead of raising."""
        with patch.object(mcp_client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = Exception("Connection error")

            tools = await mcp_client.list_tools_with_schemas("/product_retrieval")

            # Should return empty list on error, not raise
            assert isinstance(tools, list)
            assert len(tools) == 0


class TestMCPClientSSEParsing:
    """Test SSE response parsing logic."""

    @pytest.fixture
    def token_manager(self):
        """Mock token manager."""
        manager = MagicMock(spec=MCPTokenManager)
        manager.get_valid_token = MagicMock(return_value="test-token")
        return manager

    @pytest.fixture
    def mcp_client(self, token_manager):
        """Create MCP client."""
        return MCPClient(
            base_url="https://test-mcp.example.com",
            token_manager=token_manager,
            timeout=30.0,
            discovery_endpoint="/tools/discovery"  # Explicit for clarity
        )

    def test_parse_sse_single_line(self, mcp_client):
        """Test parsing SSE with single data line."""
        sse_text = """data: {"jsonrpc":"2.0","id":"123","result":{"content":[{"type":"text","text":"Hello"}]}}

data: [DONE]
"""

        result = mcp_client._parse_sse_response(sse_text)

        assert isinstance(result, dict)
        assert "content" in result
        assert len(result["content"]) == 1
        assert result["content"][0]["text"] == "Hello"

    def test_parse_sse_multiple_data_lines(self, mcp_client):
        """Test parsing SSE with multiple data lines."""
        sse_text = """event: message
data: {"jsonrpc":"2.0","id":"123","result":{"content":[{"type":"text","text":"Line 1"}]}}

event: message
data: {"jsonrpc":"2.0","id":"124","result":{"content":[{"type":"text","text":"Line 2"}]}}

data: [DONE]
"""

        # Parse first result
        result = mcp_client._parse_sse_response(sse_text)

        # Should parse first valid JSON-RPC result
        assert isinstance(result, dict)
        assert "content" in result

    def test_parse_sse_with_error(self, mcp_client):
        """Test parsing SSE response with error."""
        sse_text = """data: {"jsonrpc":"2.0","id":"123","error":{"code":-32600,"message":"Invalid request"}}

data: [DONE]
"""

        with pytest.raises(ValueError, match="MCP tool error"):
            mcp_client._parse_sse_response(sse_text)

    def test_parse_sse_skips_empty_lines(self, mcp_client):
        """Test that empty lines are skipped during parsing."""
        sse_text = """

data: {"jsonrpc":"2.0","id":"123","result":{"content":[]}}


data: [DONE]

"""

        result = mcp_client._parse_sse_response(sse_text)

        assert isinstance(result, dict)
        assert "content" in result

    def test_parse_sse_skips_done_marker(self, mcp_client):
        """Test that [DONE] marker is skipped."""
        sse_text = """data: {"jsonrpc":"2.0","id":"123","result":{"tools":[]}}

data: [DONE]
"""

        result = mcp_client._parse_sse_response(sse_text)

        # Should not include [DONE] in result
        assert result != "[DONE]"
        assert isinstance(result, dict)

    def test_parse_sse_no_valid_result_raises_error(self, mcp_client):
        """Test that missing result raises ValueError."""
        sse_text = """data: [DONE]
"""

        with pytest.raises(ValueError, match="No valid JSON-RPC result"):
            mcp_client._parse_sse_response(sse_text)

    def test_parse_sse_invalid_json_skips_line(self, mcp_client):
        """Test that invalid JSON lines are skipped."""
        sse_text = """data: invalid json

data: {"jsonrpc":"2.0","id":"123","result":{"content":[]}}

data: [DONE]
"""

        # Should skip invalid JSON and parse valid line
        result = mcp_client._parse_sse_response(sse_text)

        assert isinstance(result, dict)
        assert "content" in result


class TestMCPClientDiscoveryEndpoint:
    """Test MCP Client's configurable discovery endpoint feature."""

    @pytest.fixture
    def token_manager(self):
        """Mock token manager."""
        manager = MagicMock(spec=MCPTokenManager)
        manager.get_valid_token = MagicMock(return_value="test-token")
        return manager

    @pytest.mark.asyncio
    async def test_default_discovery_endpoint(self, token_manager):
        """Test MCPClient uses default /tools/discovery endpoint when not specified."""
        client = MCPClient(
            base_url="https://test-mcp-server.com",
            token_manager=token_manager,
        )

        mock_response = [{"name": "default_server", "path": "/default"}]

        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            servers = await client.list_servers()

            assert len(servers) == 1

            # Verify default endpoint was used
            call_args = mock_request.call_args
            url = call_args.args[1]
            assert url == "https://test-mcp-server.com/tools/discovery"

        await client.close()

    @pytest.mark.asyncio
    async def test_custom_discovery_endpoint_relative_path(self, token_manager):
        """Test MCPClient uses custom relative discovery endpoint path."""
        client = MCPClient(
            base_url="https://test-mcp-server.com",
            token_manager=token_manager,
            discovery_endpoint="/custom/discover",
        )

        mock_response = [{"name": "test_server", "path": "/test"}]

        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            servers = await client.list_servers()

            assert len(servers) == 1
            assert servers[0]["name"] == "test_server"

            # Verify the correct URL was called (base_url + custom path)
            call_args = mock_request.call_args
            url = call_args.args[1]
            assert url == "https://test-mcp-server.com/custom/discover"

        await client.close()

    @pytest.mark.asyncio
    async def test_custom_discovery_endpoint_absolute_url(self, token_manager):
        """Test MCPClient uses absolute URL for discovery endpoint."""
        client = MCPClient(
            base_url="https://test-mcp-server.com",  # This should be ignored
            token_manager=token_manager,
            discovery_endpoint="https://other-discovery-server.com/api/discover",
        )

        mock_response = [{"name": "external_server", "path": "/external"}]

        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            servers = await client.list_servers()

            assert len(servers) == 1
            assert servers[0]["name"] == "external_server"

            # Verify absolute URL was used (not base_url)
            call_args = mock_request.call_args
            url = call_args.args[1]
            assert url == "https://other-discovery-server.com/api/discover"

        await client.close()

    def test_invalid_discovery_endpoint_format(self, token_manager):
        """Test MCPClient raises ValueError for invalid discovery endpoint format."""
        with pytest.raises(ValueError, match="Invalid discovery endpoint"):
            MCPClient(
                base_url="https://test-mcp-server.com",
                token_manager=token_manager,
                discovery_endpoint="invalid-endpoint",  # Missing leading slash or protocol
            )

    def test_discovery_endpoint_logged_on_init(self, token_manager):
        """Test that discovery endpoint is logged during initialization."""
        with patch('app.services.mcp_client.logger') as mock_logger:
            client = MCPClient(
                base_url="https://test-mcp-server.com",
                token_manager=token_manager,
                discovery_endpoint="/custom/discover",
            )

            # Verify logger.info was called with discovery_endpoint
            mock_logger.info.assert_called_once()
            call_kwargs = mock_logger.info.call_args.kwargs
            assert call_kwargs["discovery_endpoint"] == "/custom/discover"
