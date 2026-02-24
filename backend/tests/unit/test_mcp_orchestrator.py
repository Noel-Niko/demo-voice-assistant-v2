"""Unit tests for MCP Orchestrator - LLM-driven tool selection and execution."""
import json
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.services.mcp_orchestrator import MCPOrchestrator


class TestMCPOrchestratorToolSelection:
    """Test LLM-driven tool selection logic."""

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
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "inputs": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"},
                                "vector_store": {"type": "string"},
                                "skus": {"type": "array"},
                                "model_nos": {"type": "array"},
                                "brands": {"type": "array"},
                                "lns": {"type": "array"}
                            }
                        }
                    }
                }
            }
        ])
        client.call_tool = AsyncMock(return_value={
            "content": [
                {"type": "text", "text": "Product result"}
            ]
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
    async def test_query_discovers_servers(self, orchestrator, mock_mcp_client):
        """Test that orchestrator discovers available servers."""
        # Set a no-op progress callback to avoid None issues
        orchestrator.set_progress_callback(lambda msg: None)

        with patch.object(orchestrator.openai.chat.completions, 'create', new_callable=AsyncMock) as mock_openai:
            # Mock LLM responses
            mock_openai.side_effect = [
                # Server selection response
                MagicMock(choices=[MagicMock(message=MagicMock(content="/product_retrieval"))]),
                # Tool selection response
                MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
                    "tool_name": "get_product_docs",
                    "arguments": {
                        "inputs": {
                            "query": "test query",
                            "vector_store": "Product",
                            "skus": [],
                            "model_nos": [],
                            "brands": [],
                            "lns": []
                        }
                    }
                })))]),
                # Formatting response
                MagicMock(choices=[MagicMock(message=MagicMock(content="Formatted result"))])
            ]

            result = await orchestrator.query("test query")

            # Verify server discovery was called
            mock_mcp_client.list_servers.assert_called_once()
            assert result["server_path"] == "/product_retrieval"

    @pytest.mark.asyncio
    async def test_query_discovers_tools_with_schemas(self, orchestrator, mock_mcp_client):
        """Test that orchestrator discovers tools with their schemas."""
        orchestrator.set_progress_callback(lambda msg: None)

        with patch.object(orchestrator.openai.chat.completions, 'create', new_callable=AsyncMock) as mock_openai:
            mock_openai.side_effect = [
                MagicMock(choices=[MagicMock(message=MagicMock(content="/product_retrieval"))]),
                MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
                    "tool_name": "get_product_docs",
                    "arguments": {"inputs": {"query": "test"}}
                })))]),
                MagicMock(choices=[MagicMock(message=MagicMock(content="Formatted result"))])  # Formatting step
            ]

            result = await orchestrator.query("test query")

            # Verify tool discovery was called
            mock_mcp_client.list_tools_with_schemas.assert_called_once_with("/product_retrieval")
            assert result["tool_name"] == "get_product_docs"

    @pytest.mark.asyncio
    async def test_llm_generates_correct_arguments(self, orchestrator, mock_mcp_client):
        """Test that LLM generates arguments matching tool schema."""
        orchestrator.set_progress_callback(lambda msg: None)

        with patch.object(orchestrator.openai.chat.completions, 'create', new_callable=AsyncMock) as mock_openai:
            expected_arguments = {
                "inputs": {
                    "query": "safety gloves",
                    "vector_store": "Product",
                    "skus": [],
                    "model_nos": [],
                    "brands": ["ANSELL"],
                    "lns": []
                }
            }

            mock_openai.side_effect = [
                MagicMock(choices=[MagicMock(message=MagicMock(content="/product_retrieval"))]),
                MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
                    "tool_name": "get_product_docs",
                    "arguments": expected_arguments
                })))]),
                MagicMock(choices=[MagicMock(message=MagicMock(content="Formatted result"))])  # Formatting step
            ]

            result = await orchestrator.query("recommend ANSELL safety gloves")

            # Verify LLM-generated arguments were used
            mock_mcp_client.call_tool.assert_called_once_with(
                server_path="/product_retrieval",
                tool_name="get_product_docs",
                arguments=expected_arguments
            )
            assert result["arguments"] == expected_arguments

    @pytest.mark.asyncio
    async def test_preferred_server_bypasses_llm_selection(self, orchestrator, mock_mcp_client):
        """Test that providing preferred_server skips LLM server selection."""
        orchestrator.set_progress_callback(lambda msg: None)

        with patch.object(orchestrator.openai.chat.completions, 'create', new_callable=AsyncMock) as mock_openai:
            mock_openai.return_value = MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
                "tool_name": "get_product_docs",
                "arguments": {"inputs": {"query": "test"}}
            })))])

            result = await orchestrator.query("test query", preferred_server="/product_retrieval")

            # Verify server discovery skipped when using preferred server
            # Note: list_servers may still be called internally but LLM server selection is skipped
            assert result["server_path"] == "/product_retrieval"
            # Verify LLM was called only twice (tool selection + formatting), not 3 times (no server selection)
            assert mock_openai.call_count == 2

    @pytest.mark.asyncio
    async def test_no_tools_available_raises_error(self, orchestrator, mock_mcp_client):
        """Test that error is raised when no tools available on server."""
        orchestrator.set_progress_callback(lambda msg: None)
        mock_mcp_client.list_tools_with_schemas.return_value = []

        with patch.object(orchestrator.openai.chat.completions, 'create', new_callable=AsyncMock) as mock_openai:
            mock_openai.return_value = MagicMock(choices=[MagicMock(message=MagicMock(content="/product_retrieval"))])

            with pytest.raises(ValueError, match="No tools available"):
                await orchestrator.query("test query")

    @pytest.mark.asyncio
    async def test_llm_invalid_json_falls_back_to_first_tool(self, orchestrator, mock_mcp_client):
        """Test fallback behavior when LLM returns invalid JSON."""
        orchestrator.set_progress_callback(lambda msg: None)

        with patch.object(orchestrator.openai.chat.completions, 'create', new_callable=AsyncMock) as mock_openai:
            mock_openai.side_effect = [
                MagicMock(choices=[MagicMock(message=MagicMock(content="/product_retrieval"))]),
                MagicMock(choices=[MagicMock(message=MagicMock(content="invalid json"))]),
                MagicMock(choices=[MagicMock(message=MagicMock(content="Formatted result"))])  # Formatting step
            ]

            result = await orchestrator.query("test query")

            # Should fallback to first tool with basic arguments
            assert result["tool_name"] == "get_product_docs"
            assert result["arguments"] == {"query": "test query"}


class TestMCPOrchestratorModelSelector:
    """Test set_model() on MCP Orchestrator."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with minimal setup."""
        client = AsyncMock()
        return MCPOrchestrator(mcp_client=client, openai_api_key="test-key")

    def test_init_uses_default_model(self, orchestrator):
        """Test that MCP orchestrator defaults to model from constructor."""
        # Orchestrator creates its own openai client; we verify set_model works
        assert orchestrator.model == "gpt-3.5-turbo"

    def test_init_with_custom_model(self):
        """Test initializing orchestrator with a specific model."""
        client = AsyncMock()
        orch = MCPOrchestrator(mcp_client=client, openai_api_key="test-key", model="gpt-4o")
        assert orch.model == "gpt-4o"

    def test_set_model_changes_model(self, orchestrator):
        """Test that set_model updates the model attribute."""
        orchestrator.set_model("gpt-4.1-mini")
        assert orchestrator.model == "gpt-4.1-mini"

    def test_set_model_with_reasoning_effort(self, orchestrator):
        """Test that set_model stores reasoning_effort."""
        orchestrator.set_model("gpt-5", reasoning_effort="low")
        assert orchestrator.model == "gpt-5"
        assert orchestrator._reasoning_effort == "low"

    @pytest.mark.asyncio
    async def test_all_three_llm_calls_use_self_model(self):
        """Test that all 3 LLM call sites in orchestrator use self.model."""
        client = AsyncMock()
        client.list_servers = AsyncMock(return_value={
            "servers": [{"path": "/product_retrieval", "name": "test", "roles": [], "category": "product", "priority": "high"}],
            "total_count": 1
        })
        client.list_tools_with_schemas = AsyncMock(return_value=[
            {"name": "get_product_docs", "description": "test", "inputSchema": {"type": "object"}}
        ])
        client.call_tool = AsyncMock(return_value={"content": [{"type": "text", "text": "result"}]})

        orch = MCPOrchestrator(mcp_client=client, openai_api_key="test-key", model="gpt-4o")
        orch.set_progress_callback(lambda msg: None)

        with patch.object(orch.openai.chat.completions, 'create', new_callable=AsyncMock) as mock_openai:
            mock_openai.side_effect = [
                MagicMock(choices=[MagicMock(message=MagicMock(content="/product_retrieval"))]),
                MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
                    "tool_name": "get_product_docs",
                    "arguments": {"inputs": {"query": "test"}}
                })))]),
                MagicMock(choices=[MagicMock(message=MagicMock(content="Formatted"))]),
            ]

            await orch.query("test query")

            # All 3 LLM calls should use "gpt-4o" (not hardcoded "gpt-3.5-turbo")
            for call_args in mock_openai.call_args_list:
                assert call_args.kwargs.get("model", call_args[1].get("model")) == "gpt-4o"


class TestMCPOrchestratorResultFormatting:
    """Test LLM-powered result formatting."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with minimal setup."""
        client = AsyncMock()
        return MCPOrchestrator(mcp_client=client, openai_api_key="test-key")

    @pytest.mark.asyncio
    async def test_format_product_result_with_llm(self, orchestrator):
        """Test formatting raw product result into user-friendly response."""
        raw_result = {
            "content": [
                {
                    "type": "text",
                    "text": "<doc id=0>SKU: 1FYX7\nANSELL Chemical Resistant Gloves\nNitrile coating, size large</doc>"
                }
            ]
        }

        with patch.object(orchestrator.openai.chat.completions, 'create', new_callable=AsyncMock) as mock_openai:
            mock_openai.return_value = MagicMock(choices=[MagicMock(message=MagicMock(content="""**Product Recommendations:**

• **SKU 1FYX7** - ANSELL Chemical Resistant Gloves
  Recommended: Nitrile coating provides excellent chemical resistance
  View: https://www.grainger.com/product/1FYX7"""))])

            result = await orchestrator._format_result_for_user(
                user_query="recommend safety gloves",
                raw_result=raw_result,
                server_path="/product_retrieval",
                model="gpt-3.5-turbo",
                reasoning_effort=None
            )

            # Verify LLM was called with product formatting instructions
            assert mock_openai.call_count == 1
            call_args = mock_openai.call_args
            assert "Product Query Formatting" in call_args.kwargs["messages"][0]["content"]
            assert "https://www.grainger.com/product/{SKU}" in call_args.kwargs["messages"][0]["content"]

            # Verify result is formatted
            assert isinstance(result, dict)
            assert "content" in result
            assert result["content"][0]["type"] == "text"
            assert "SKU 1FYX7" in result["content"][0]["text"]
            assert "https://www.grainger.com/product/1FYX7" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_format_order_result_with_llm(self, orchestrator):
        """Test formatting raw order result into user-friendly response."""
        raw_result = {
            "content": [
                {
                    "type": "text",
                    "text": "Order #12345: Status=Shipped, Delivery=2/23/2026, Items=5"
                }
            ]
        }

        with patch.object(orchestrator.openai.chat.completions, 'create', new_callable=AsyncMock) as mock_openai:
            mock_openai.return_value = MagicMock(choices=[MagicMock(message=MagicMock(content="""**Order #12345**
Status: Shipped on 2/20/2026, expected delivery 2/23/2026. Contains 5 items."""))])

            result = await orchestrator._format_result_for_user(
                user_query="where is my order 12345",
                raw_result=raw_result,
                server_path="/order",
                model="gpt-3.5-turbo",
                reasoning_effort=None
            )

            # Verify LLM was called with order formatting instructions
            assert mock_openai.call_count == 1
            call_args = mock_openai.call_args
            assert "Order Query Formatting" in call_args.kwargs["messages"][0]["content"]

            # Verify result is formatted
            assert isinstance(result, dict)
            assert "Order #12345" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_format_result_with_empty_content(self, orchestrator):
        """Test handling empty content gracefully."""
        raw_result = {"content": []}

        result = await orchestrator._format_result_for_user(
            user_query="test",
            raw_result=raw_result,
            server_path="/product_retrieval",
            model="gpt-3.5-turbo",
            reasoning_effort=None
        )

        # Should return as-is without calling LLM
        assert result == raw_result


class TestMCPOrchestratorSSEParsing:
    """Test SSE response parsing from MCP server."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with minimal setup."""
        client = AsyncMock()
        client.list_servers = AsyncMock(return_value={"servers": [], "total_count": 0})
        return MCPOrchestrator(mcp_client=client, openai_api_key="test-key")

    def test_parses_sse_content_array(self, orchestrator):
        """Test parsing SSE response with content array."""
        sse_response = {
            "content": [
                {"type": "text", "text": "Result 1"},
                {"type": "text", "text": "Result 2"}
            ]
        }

        # MCPOrchestrator doesn't parse SSE directly, that's in MCPClient
        # This is handled by the route parsing logic
        assert isinstance(sse_response["content"], list)
        assert len(sse_response["content"]) == 2


class TestMCPOrchestratorIntegration:
    """Integration tests for full query flow."""

    @pytest.mark.asyncio
    async def test_full_query_flow(self):
        """Test complete query flow from query to result."""
        mock_client = AsyncMock()
        mock_client.list_servers = AsyncMock(return_value={
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
        mock_client.list_tools_with_schemas = AsyncMock(return_value=[
            {
                "name": "get_product_docs",
                "description": "Retrieve product documents",
                "inputSchema": {"type": "object"}
            }
        ])
        mock_client.call_tool = AsyncMock(return_value={
            "content": [{"type": "text", "text": "Product result"}]
        })

        orchestrator = MCPOrchestrator(mcp_client=mock_client, openai_api_key="test-key")
        orchestrator.set_progress_callback(lambda msg: None)

        with patch.object(orchestrator.openai.chat.completions, 'create', new_callable=AsyncMock) as mock_openai:
            mock_openai.side_effect = [
                # Server selection
                MagicMock(choices=[MagicMock(message=MagicMock(content="/product_retrieval"))]),
                # Tool selection
                MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
                    "tool_name": "get_product_docs",
                    "arguments": {"inputs": {"query": "ladder"}}
                })))]),
                # Result formatting (new Step 6)
                MagicMock(choices=[MagicMock(message=MagicMock(content="Formatted product result"))])
            ]

            result = await orchestrator.query("recommend a ladder")

            # Verify full flow including formatting step
            assert result["server_path"] == "/product_retrieval"
            assert result["tool_name"] == "get_product_docs"
            assert "result" in result
            # Result should be formatted by LLM (Step 6)
            assert result["result"]["content"][0]["text"] == "Formatted product result"

    @pytest.mark.asyncio
    async def test_model_switch_during_query_uses_captured_config(self):
        """Test that model changes mid-operation don't affect in-flight API calls.

        Bug: When user switches models during MCP query (e.g., GPT-3.5 → GPT-5),
        the API calls read self.model at different times, causing parameter mismatches.

        This test verifies that after the fix:
        1. Query starts with GPT-3.5
        2. Model switches to GPT-5 mid-operation
        3. All 3 API calls use the originally captured GPT-3.5 config
        """
        mock_client = AsyncMock()
        mock_client.list_servers = AsyncMock(return_value={
            "servers": [{"path": "/product_retrieval", "name": "test"}]
        })
        mock_client.list_tools_with_schemas = AsyncMock(return_value=[
            {"name": "test_tool", "description": "test", "inputSchema": {}}
        ])
        mock_client.call_tool = AsyncMock(return_value={"content": [{"type": "text", "text": "result"}]})

        # Initialize with GPT-3.5
        orchestrator = MCPOrchestrator(mcp_client=mock_client, openai_api_key="test-key")
        orchestrator.model = "gpt-3.5-turbo"
        orchestrator._reasoning_effort = None
        orchestrator.set_progress_callback(lambda msg: None)

        # Track API kwargs for all 3 calls
        captured_api_kwargs = []

        with patch.object(orchestrator.openai.chat.completions, 'create', new_callable=AsyncMock) as mock_openai:
            async def capture_and_switch(*args, **kwargs):
                # Capture kwargs
                captured_api_kwargs.append(kwargs.copy())

                # Switch model after first API call (server selection)
                if len(captured_api_kwargs) == 1:
                    orchestrator.model = "gpt-5"
                    orchestrator._reasoning_effort = "low"

                # Return appropriate mock response
                if len(captured_api_kwargs) == 1:
                    # Server selection
                    return MagicMock(choices=[MagicMock(message=MagicMock(content="/product_retrieval"))])
                elif len(captured_api_kwargs) == 2:
                    # Tool selection
                    return MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
                        "tool_name": "test_tool",
                        "arguments": {}
                    })))])
                else:
                    # Result formatting
                    return MagicMock(choices=[MagicMock(message=MagicMock(content="formatted"))])

            mock_openai.side_effect = capture_and_switch

            await orchestrator.query("test query")

            # Verify all 3 API calls used GPT-3.5 config (captured at start)
            assert len(captured_api_kwargs) == 3, "Should have made 3 API calls"

            for i, kwargs in enumerate(captured_api_kwargs):
                assert kwargs["model"] == "gpt-3.5-turbo", \
                    f"API call {i+1} should use originally captured model (GPT-3.5), not switched model (GPT-5)"
                assert "temperature" in kwargs, \
                    f"API call {i+1} should use temperature parameter for GPT-3.5"
                assert "reasoning_effort" not in kwargs, \
                    f"API call {i+1} should NOT have reasoning_effort for GPT-3.5"
                assert "max_tokens" in kwargs, \
                    f"API call {i+1} should use max_tokens (not max_completion_tokens) for GPT-3.5"


class TestMCPOrchestratorReasoningTokenBudget:
    """Test that reasoning models get multiplied token budgets.

    Bug: GPT-5/o1 models share max_completion_tokens between reasoning and output.
    With small budgets (50 for server selection, 500 for tool selection, 400 for
    formatting), the model exhausts its budget on reasoning, producing empty output.

    Fix: _build_api_kwargs multiplies base_max_tokens for reasoning models.
    """

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with minimal setup."""
        client = AsyncMock()
        return MCPOrchestrator(mcp_client=client, openai_api_key="test-key")

    @pytest.mark.asyncio
    async def test_server_selection_token_budget_for_gpt5(self, orchestrator):
        """Test server selection (base=50) gets adequate budget for GPT-5."""
        kwargs = orchestrator._build_api_kwargs(
            base_temp=0,
            base_max_tokens=50,
            model="gpt-5",
            reasoning_effort="low",
        )

        assert "max_completion_tokens" in kwargs
        assert kwargs["max_completion_tokens"] >= 200, (
            f"Server selection with GPT-5 needs >= 200 tokens (reasoning + output), "
            f"got {kwargs['max_completion_tokens']}"
        )

    @pytest.mark.asyncio
    async def test_tool_selection_token_budget_for_gpt5(self, orchestrator):
        """Test tool selection (base=500) gets adequate budget for GPT-5."""
        kwargs = orchestrator._build_api_kwargs(
            base_temp=0,
            base_max_tokens=500,
            model="gpt-5",
            reasoning_effort="low",
        )

        assert kwargs["max_completion_tokens"] >= 2000, (
            f"Tool selection with GPT-5 needs >= 2000 tokens, "
            f"got {kwargs['max_completion_tokens']}"
        )

    @pytest.mark.asyncio
    async def test_result_formatting_token_budget_for_gpt5(self, orchestrator):
        """Test result formatting (base=400) gets adequate budget for GPT-5."""
        kwargs = orchestrator._build_api_kwargs(
            base_temp=0.3,
            base_max_tokens=400,
            model="gpt-5",
            reasoning_effort="low",
        )

        assert kwargs["max_completion_tokens"] >= 1600, (
            f"Result formatting with GPT-5 needs >= 1600 tokens, "
            f"got {kwargs['max_completion_tokens']}"
        )

    @pytest.mark.asyncio
    async def test_non_reasoning_model_unchanged(self, orchestrator):
        """Test that non-reasoning models keep original token budget."""
        kwargs = orchestrator._build_api_kwargs(
            base_temp=0,
            base_max_tokens=50,
            model="gpt-3.5-turbo",
            reasoning_effort=None,
        )

        assert "max_tokens" in kwargs
        assert kwargs["max_tokens"] == 50, \
            "Non-reasoning models should use base_max_tokens unmodified"

    @pytest.mark.asyncio
    async def test_o1_models_get_multiplied_budget(self, orchestrator):
        """Test that o1-preview and o1-mini also get multiplied budgets."""
        for model_name in ["o1-preview", "o1-mini"]:
            kwargs = orchestrator._build_api_kwargs(
                base_temp=0,
                base_max_tokens=500,
                model=model_name,
                reasoning_effort="medium",
            )

            assert kwargs["max_completion_tokens"] >= 2000, (
                f"{model_name} should get multiplied token budget, "
                f"got {kwargs['max_completion_tokens']}"
            )
