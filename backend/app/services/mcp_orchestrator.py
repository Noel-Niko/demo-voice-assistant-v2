"""MCP Orchestrator - LLM-driven dynamic tool discovery and execution.

Uses OpenAI to intelligently select tools and format arguments based on:
1. User query intent
2. Available tools and their schemas
3. Dynamic argument generation

This is the proper MCP (Model Context Protocol) pattern.
"""
import asyncio
import json
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

import structlog
from openai import AsyncOpenAI

from app.services.mcp_client import MCPClient

logger = structlog.get_logger(__name__)


class MCPOrchestrator:
    """Orchestrates LLM-driven MCP tool discovery and execution."""

    def __init__(self, mcp_client: MCPClient, openai_api_key: str, model: str = "gpt-3.5-turbo"):
        """Initialize orchestrator.

        Args:
            mcp_client: MCP client for tool discovery and execution
            openai_api_key: OpenAI API key for LLM reasoning
            model: OpenAI model name for LLM calls
        """
        self.mcp_client = mcp_client
        self.openai = AsyncOpenAI(api_key=openai_api_key, timeout=60.0)  # 60 second timeout
        self.model = model
        self._reasoning_effort: str | None = None
        self._progress_callback: Optional[Callable[[str], None]] = None

    def set_progress_callback(self, callback: Callable[[str], None]):
        """Set callback for progress updates.

        Args:
            callback: Function to call with progress messages
        """
        self._progress_callback = callback

    async def _emit_progress(self, message: str):
        """Emit progress update if callback is set.

        Args:
            message: Progress message to emit
        """
        if self._progress_callback:
            self._progress_callback(message)
        logger.info("mcp_progress", message=message)

    def set_model(self, model: str, reasoning_effort: str | None = None) -> None:
        """Update the LLM model used for MCP orchestration.

        Args:
            model: OpenAI model name
            reasoning_effort: Optional reasoning effort level
        """
        self.model = model
        self._reasoning_effort = reasoning_effort
        logger.info(
            "mcp_orchestrator_model_updated",
            model=model,
            reasoning_effort=reasoning_effort,
        )

    def _get_current_model_config(self) -> tuple[str, str | None]:
        """Get current model config atomically.

        Returns model and reasoning_effort as a tuple to avoid race conditions
        when model is changed mid-operation.

        Returns:
            Tuple of (model, reasoning_effort)
        """
        return (self.model, self._reasoning_effort)

    # Reasoning models (GPT-5, o1-*) share max_completion_tokens between
    # internal reasoning and visible output. Without a multiplier, the model
    # exhausts its budget on reasoning and produces empty output.
    REASONING_TOKEN_MULTIPLIER = 4

    def _build_api_kwargs(self, base_temp: float, base_max_tokens: int, model: str, reasoning_effort: str | None) -> dict:
        """Build API kwargs based on model type.

        o1-family models have different parameter requirements:
        - Use reasoning_effort instead of temperature
        - Use max_completion_tokens instead of max_tokens
        - max_completion_tokens is multiplied by REASONING_TOKEN_MULTIPLIER
          because reasoning tokens consume part of the budget

        Args:
            base_temp: Default temperature for non-o1 models
            base_max_tokens: Max tokens for response
            model: Model name to use (captured atomically)
            reasoning_effort: Reasoning effort level (captured atomically)

        Returns:
            Dict of API kwargs compatible with the current model
        """
        is_o1_model = model.startswith("o1-") or model == "gpt-5"

        kwargs = {
            "model": model,
        }

        if is_o1_model:
            kwargs["max_completion_tokens"] = base_max_tokens * self.REASONING_TOKEN_MULTIPLIER
            if reasoning_effort is not None:
                kwargs["reasoning_effort"] = reasoning_effort
        else:
            kwargs["max_tokens"] = base_max_tokens
            kwargs["temperature"] = base_temp

        return kwargs

    async def query(self, user_query: str, preferred_server: str | None = None) -> Dict[str, Any]:
        """Process user query using LLM-driven tool selection and execution.

        Args:
            user_query: User's natural language query
            preferred_server: Optional preferred server path (e.g., "/product_retrieval")

        Returns:
            Dict containing:
            - result: Tool execution result
            - server_path: Server that was used
            - tool_name: Tool that was called
            - arguments: Arguments that were generated

        Raises:
            ValueError: If no suitable tool found or LLM fails
        """
        # Capture model config atomically at the start to avoid race conditions
        # when model changes mid-operation
        model, reasoning_effort = self._get_current_model_config()

        logger.info("mcp_orchestrator_query_start", query=user_query[:100])

        # Step 1: Discover available servers
        await self._emit_progress("🔍 Discovering available servers...")
        discovery = await self.mcp_client.list_servers()
        servers = discovery.get("servers", [])

        # Step 2: Select appropriate server (prefer user's choice or use LLM)
        if preferred_server:
            server_path = preferred_server
            await self._emit_progress(f"📍 Using preferred server: {server_path}")
            logger.info("mcp_using_preferred_server", server_path=server_path)
        else:
            await self._emit_progress("🤖 AI selecting best server for your query...")
            server_path = await self._select_server(user_query, servers, model, reasoning_effort)
            await self._emit_progress(f"✓ Selected server: {server_path}")
            logger.info("mcp_llm_selected_server", server_path=server_path)

        # Step 3: Get tools and schemas for selected server
        await self._emit_progress("🔧 Discovering available tools...")
        tools = await self.mcp_client.list_tools_with_schemas(server_path)

        if not tools:
            raise ValueError(f"No tools available on server '{server_path}'")

        logger.info("mcp_tools_discovered", server_path=server_path, tool_count=len(tools))
        await self._emit_progress(f"✓ Found {len(tools)} available tools")

        # Step 4: Use LLM to select tool and generate arguments
        await self._emit_progress("🧠 Analyzing query and selecting best tool...")
        tool_call = await self._select_tool_and_generate_args(user_query, tools, model, reasoning_effort)

        logger.info(
            "mcp_llm_generated_tool_call",
            tool_name=tool_call["tool_name"],
            args_preview=str(tool_call["arguments"])[:200]
        )
        await self._emit_progress(f"✓ Selected tool: {tool_call['tool_name']}")

        # Step 5: Execute tool call
        await self._emit_progress(f"⚡ Calling tool: {tool_call['tool_name']}...")
        result = await self.mcp_client.call_tool(
            server_path=server_path,
            tool_name=tool_call["tool_name"],
            arguments=tool_call["arguments"]
        )

        logger.info("mcp_orchestrator_query_complete", tool_name=tool_call["tool_name"])
        await self._emit_progress("✓ Received response from server")

        # Step 6: Use LLM to format raw result into user-friendly response
        await self._emit_progress("✨ Formatting response for you...")
        formatted_result = await self._format_result_for_user(
            user_query=user_query,
            raw_result=result,
            server_path=server_path,
            model=model,
            reasoning_effort=reasoning_effort
        )
        await self._emit_progress("✅ Complete!")

        return {
            "result": formatted_result,
            "server_path": server_path,
            "tool_name": tool_call["tool_name"],
            "arguments": tool_call["arguments"]
        }

    async def _select_server(self, user_query: str, servers: List[Dict[str, Any]], model: str, reasoning_effort: str | None) -> str:
        """Use LLM to select the most appropriate server for the query.

        Args:
            user_query: User's query
            servers: Available servers from discovery
            model: Model name to use (captured atomically)
            reasoning_effort: Reasoning effort level (captured atomically)

        Returns:
            Server path (e.g., "/product_retrieval")
        """
        # Build server descriptions for LLM
        server_descriptions = []
        for server in servers:
            server_descriptions.append({
                "path": server.get("path"),
                "name": server.get("name"),
                "roles": server.get("roles", []),
                "category": server.get("category"),
                "priority": server.get("priority")
            })

        prompt = f"""You are an MCP server routing assistant. Select the most appropriate MCP server for the user's query.

User Query: {user_query}

Available Servers:
{json.dumps(server_descriptions, indent=2)}

Server Selection Guidelines:
- /order: Use for order tracking, order status, order history queries
  Example: "track my order 12345", "where is order ABC123"

- /pricing: Use for price checks, cost inquiries, quote requests
  Example: "how much does SKU 1FYX7 cost", "price for safety gloves"

- /availability: Use for stock checks, inventory inquiries
  Example: "is SKU 1FYX7 in stock", "availability of safety gloves"

- /product_retrieval (HIGH priority): Use for general product searches, recommendations, alternatives
  Example: "recommend a ladder", "find safety gloves", "alternatives to SKU 1FYX7"

- /semantic_search: Use for conceptual/semantic product searches
  Example: "products for fall protection", "items similar to hard hats"

- /solr: Use for exact keyword/SKU searches
  Example: "search SKU 1FYX7", "find product by keyword"

- /parse_query: Use for understanding/parsing complex queries
  Example: "break down this query", "parse search intent"

- /assortment_api: Use for category browsing, product URLs, filter info
  Example: "categories for safety equipment", "product URL for SKU"

Prefer high-priority servers when multiple servers could work.
For product-related queries without specific intent (pricing/orders/availability), use /product_retrieval.

Respond with ONLY the server path (e.g., "/product_retrieval"). No explanation."""

        # Use captured model config to prevent race conditions
        api_kwargs = self._build_api_kwargs(
            base_temp=0,
            base_max_tokens=50,
            model=model,
            reasoning_effort=reasoning_effort
        )

        try:
            response = await self.openai.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                **api_kwargs
            )
        except Exception as e:
            logger.error(
                "mcp_server_selection_api_error",
                error=str(e),
                model=model,
                reasoning_effort=reasoning_effort,
                exc_info=True
            )
            # Fallback to product_retrieval on error
            logger.warning("mcp_server_selection_failed_using_fallback", fallback="/product_retrieval")
            return "/product_retrieval"

        server_path = response.choices[0].message.content.strip()

        # Validate it's a known server
        valid_paths = [s.get("path") for s in servers]
        if server_path not in valid_paths:
            # Fallback to product_retrieval (high priority)
            logger.warning("mcp_llm_invalid_server", selected=server_path, falling_back_to="/product_retrieval")
            return "/product_retrieval"

        return server_path

    async def _select_tool_and_generate_args(
        self,
        user_query: str,
        tools: List[Dict[str, Any]],
        model: str,
        reasoning_effort: str | None
    ) -> Dict[str, Any]:
        """Use LLM to select tool and generate arguments based on schemas.

        Args:
            user_query: User's query
            tools: Available tools with inputSchemas
            model: Model name to use (captured atomically)
            reasoning_effort: Reasoning effort level (captured atomically)

        Returns:
            Dict with:
            - tool_name: Selected tool name
            - arguments: Generated arguments (dict)
        """
        # Build tool descriptions with schemas for LLM
        tool_descriptions = []
        for tool in tools:
            tool_descriptions.append({
                "name": tool.get("name"),
                "description": tool.get("description"),
                "inputSchema": tool.get("inputSchema", {})
            })

        prompt = f"""You are an MCP (Model Context Protocol) tool calling assistant.

User Query: {user_query}

Available Tools:
{json.dumps(tool_descriptions, indent=2)}

Your task:
1. Select the most appropriate tool for this query
2. Generate the correct arguments based on the tool's inputSchema

Respond with ONLY valid JSON in this exact format:
{{
  "tool_name": "selected_tool_name",
  "arguments": {{...}}
}}

IMPORTANT:
- Follow the inputSchema exactly
- Extract relevant information from the user query to populate arguments
- For product queries, use the query text in the appropriate field
- Return ONLY JSON, no explanation"""

        # Use captured model config to prevent race conditions
        api_kwargs = self._build_api_kwargs(
            base_temp=0,
            base_max_tokens=500,
            model=model,
            reasoning_effort=reasoning_effort
        )

        try:
            response = await self.openai.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                **api_kwargs
            )
        except Exception as e:
            logger.error(
                "mcp_tool_selection_api_error",
                error=str(e),
                model=model,
                reasoning_effort=reasoning_effort,
                exc_info=True
            )
            # Fallback to first tool with basic arguments
            return {
                "tool_name": tools[0].get("name"),
                "arguments": {"query": user_query}
            }

        # Parse LLM response
        try:
            tool_call = json.loads(response.choices[0].message.content.strip())
            return tool_call
        except json.JSONDecodeError as e:
            logger.error("mcp_llm_invalid_json", response=response.choices[0].message.content, error=str(e))
            # Fallback to first tool with basic arguments
            return {
                "tool_name": tools[0].get("name"),
                "arguments": {"query": user_query}
            }

    async def _format_result_for_user(
        self,
        user_query: str,
        raw_result: Dict[str, Any],
        server_path: str,
        model: str,
        reasoning_effort: str | None
    ) -> Dict[str, Any]:
        """Use LLM to format raw MCP result into concise, user-friendly response.

        Args:
            user_query: Original user query
            raw_result: Raw result from MCP tool
            server_path: Server that was used (for context)
            model: Model name to use (captured atomically)
            reasoning_effort: Reasoning effort level (captured atomically)

        Returns:
            Formatted result with user-friendly text
        """
        # Extract content from MCP result
        content_text = ""
        if isinstance(raw_result, dict) and "content" in raw_result:
            for item in raw_result.get("content", []):
                if isinstance(item, dict) and item.get("type") == "text":
                    content_text += item.get("text", "")

        # If no content, return as-is
        if not content_text:
            return raw_result

        # Determine server type for specialized formatting instructions
        is_product_query = "product" in server_path.lower() or "semantic" in server_path.lower()
        is_order_query = "order" in server_path.lower()

        # Build formatting prompt
        prompt = f"""You are formatting search results for a CUSTOMER SERVICE AGENT who is on a live call.
The agent is looking at this on their screen while talking to the customer.

CRITICAL RULES:
- Write FOR THE AGENT viewing this on their screen during a live call
- NEVER say "contact customer service" or "reach out to support"
- Present ONLY factual information from the search results
- Be VERY CONCISE (max 2-3 sentences per result, space is limited)
- Use clear, scannable formatting

User Query: {user_query}

Raw Search Results:
{content_text[:3000]}

"""

        if is_product_query:
            prompt += """Product Query Formatting:
- List up to 3 MOST RELEVANT products only
- For each product:
  • SKU and product name
  • Brief reason why it matches the query (1 sentence)
  • Product URL: https://www.example.com/product/{SKU}
- If no products found, state this clearly and factually

Example format:
**Product Recommendations:**

• **SKU 1FYX7** - ANSELL Chemical Resistant Gloves
  Nitrile coating, excellent chemical resistance for industrial use
  View: https://www.example.com/product/1FYX7

Example no-results format:
**No matching products found for this query.**
"""
        elif is_order_query:
            prompt += """Order Query Formatting:
- State the order number clearly
- Answer the specific question (status, delivery date, items, etc.)
- Keep it under 3 sentences
- If tracking info available, include it
- If no order data found, state this clearly

Example format:
**Order #12345**
Shipped 2/20/2026, expected delivery 2/23/2026. 5 items including safety gloves. Tracking: 1Z999AA10123456784

Example no-results format:
**Order #12345** — No order data found in system.
"""
        else:
            prompt += """General Query Formatting:
- Directly answer the query with factual information
- Keep it under 3 sentences
- Include any relevant numbers/codes/identifiers
- If no useful data found, state this clearly
"""

        prompt += "\n\nNow format the search results above concisely for the agent's screen:"

        # Call LLM for formatting - use captured model config to prevent race conditions
        api_kwargs = self._build_api_kwargs(
            base_temp=0.3,
            base_max_tokens=400,
            model=model,
            reasoning_effort=reasoning_effort
        )

        try:
            response = await self.openai.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                **api_kwargs
            )
            formatted_text = response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(
                "mcp_result_formatting_api_error",
                error=str(e),
                model=model,
                reasoning_effort=reasoning_effort,
                exc_info=True
            )
            # Fallback to returning raw result without formatting
            logger.warning("mcp_formatting_failed_using_raw_result")
            return raw_result

        # Return formatted result in same structure as raw result
        return {
            "content": [
                {
                    "type": "text",
                    "text": formatted_text
                }
            ]
        }
