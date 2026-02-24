"""MCP Client - JSON-RPC 2.0 client with SSE response handling.

Implements JSON-RPC 2.0 protocol for MCP server communication.
Features:
- Auto-retry on 401 with token refresh
- Connection pooling (20 keepalive, 100 max connections)
- SSE response parsing to JSON
- Proper error handling
- Exponential backoff for 503 errors (Databricks transient overload)

Reference: code_examples/MCP_CLIENT_IMPLEMENTATION_GUIDE.md
"""
import json
import uuid
from typing import Any, Dict, List

import httpx
import structlog

from app.services.mcp_token_manager import MCPTokenManager

logger = structlog.get_logger(__name__)


class MCPClient:
    """MCP client for communicating with grainger-mcp-servers using JSON-RPC 2.0."""

    def __init__(
        self,
        base_url: str,
        token_manager: MCPTokenManager,
        timeout: float = 90.0,
    ):
        """Initialize MCP client with connection pooling.

        Args:
            base_url: MCP server base URL
            token_manager: Token manager for JWT authentication
            timeout: Request timeout in seconds (default: 90, increased for Databricks)
        """
        self.base_url = base_url.rstrip("/")
        self.token_manager = token_manager

        # Connection pooling with retry transport for 503 errors
        limits = httpx.Limits(
            max_keepalive_connections=20,
            max_connections=100,
            keepalive_expiry=30.0,
        )

        # Custom transport with retry logic for transient 503 errors
        # Databricks vector search can return 503 under load - retry with exponential backoff
        transport = httpx.AsyncHTTPTransport(
            limits=limits,
            retries=3,  # Retry up to 3 times on connection/503 errors
        )

        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            transport=transport,
            http2=True,
        )

        logger.info(
            "mcp_client_initialized",
            base_url=self.base_url,
            timeout=timeout,
        )

    async def list_servers(self) -> List[Dict[str, Any]]:
        """List all available MCP servers using discovery endpoint.

        Returns:
            List of server objects with metadata including:
            - name: Server name
            - path: Server path (includes leading slash, e.g., "/product_retrieval")
            - roles: List of capabilities (e.g., ["product_search", "semantic"])
            - category: Server category (e.g., "product", "orders")
            - priority: Server priority (e.g., "high", "medium", "low")

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        response = await self._make_request(
            "GET",
            f"{self.base_url}/tools/discovery",
        )
        return response

    async def list_tools_with_schemas(self, server_path: str) -> List[Dict[str, Any]]:
        """List tools with their schemas from an MCP server.

        Uses MCP protocol to request tool schemas via tools/list method.

        Args:
            server_path: Server path (e.g., "/product_retrieval", "/semantic_search")
                        Should include leading slash as returned by list_servers()

        Returns:
            List of tool objects with schemas including:
            - name: Tool name
            - description: What the tool does
            - inputSchema: JSON schema for arguments (MCP standard)

        Raises:
            httpx.HTTPStatusError: If request fails

        Note:
            This uses JSON-RPC 2.0 protocol with method "tools/list" to get
            tool schemas dynamically from the MCP server.
        """
        # Ensure server_path starts with / (normalize if user passes without it)
        if not server_path.startswith("/"):
            server_path = f"/{server_path}"

        # Build JSON-RPC 2.0 request for tools/list
        request_id = str(uuid.uuid4())
        rpc_request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/list",
            "params": {}
        }

        try:
            response_text = await self._make_request(
                "POST",
                f"{self.base_url}{server_path}/mcp",
                json_data=rpc_request,
            )

            # Parse SSE response to get tools list
            result = self._parse_sse_response(response_text)

            # Extract tools array from result
            if isinstance(result, dict) and "tools" in result:
                tools = result["tools"]
                logger.info(
                    "mcp_tools_listed_with_schemas",
                    server_path=server_path,
                    tool_count=len(tools) if isinstance(tools, list) else 0
                )
                return tools
            else:
                logger.warning(
                    "mcp_unexpected_tools_response",
                    server_path=server_path,
                    result_type=type(result).__name__
                )
                return []

        except Exception as e:
            logger.error(
                "mcp_tools_list_failed",
                server_path=server_path,
                error=str(e),
                exc_info=True
            )
            return []  # Return empty list on error

    async def call_tool(
        self,
        server_path: str,
        tool_name: str,
        arguments: Dict[str, Any],
        retry_count: int = 0,
    ) -> Any:
        """Call an MCP tool using JSON-RPC 2.0 protocol.

        Auto-retries once on 401 (token refresh).

        Args:
            server_path: Server path (e.g., "/product_retrieval", "/semantic_search")
                        Should include leading slash as returned by list_servers()
            tool_name: Tool name (e.g., "get_alternate_docs", "search")
            arguments: Tool arguments as dict
            retry_count: Internal retry counter

        Returns:
            Tool response (parsed from SSE)

        Raises:
            httpx.HTTPStatusError: If request fails after retry
            ValueError: If response format is invalid

        Note:
            URL format: {base_url}{server_path}/mcp
            Example: https://.../product_retrieval/mcp
        """
        # Ensure server_path starts with / (normalize if user passes without it)
        if not server_path.startswith("/"):
            server_path = f"/{server_path}"

        # Build JSON-RPC 2.0 request
        request_id = str(uuid.uuid4())
        rpc_request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        try:
            response_text = await self._make_request(
                "POST",
                f"{self.base_url}{server_path}/mcp",
                json_data=rpc_request,
            )

            # Parse SSE response to JSON
            # SSE format: "data: {json}\n\ndata: [DONE]\n\n"
            result = self._parse_sse_response(response_text)

            logger.info(
                "mcp_tool_called",
                server_path=server_path,
                tool_name=tool_name,
                request_id=request_id,
            )

            return result

        except httpx.HTTPStatusError as e:
            # Auto-retry once on 401 (expired token)
            if e.response.status_code == 401 and retry_count == 0:
                logger.warning(
                    "mcp_token_expired_retrying",
                    server_path=server_path,
                    tool_name=tool_name,
                )

                # Force refresh token
                self.token_manager._refresh_token()

                # Retry once
                return await self.call_tool(
                    server_path, tool_name, arguments, retry_count=1
                )

            # Re-raise if not 401 or already retried
            logger.error(
                "mcp_tool_call_failed",
                server_path=server_path,
                tool_name=tool_name,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise

    async def _make_request(
        self,
        method: str,
        url: str,
        json_data: Dict[str, Any] | None = None,
        headers: Dict[str, str] | None = None,
    ) -> Any:
        """Make authenticated HTTP request to MCP server.

        Args:
            method: HTTP method (GET, POST)
            url: Full URL
            json_data: JSON body (for POST)
            headers: Additional headers

        Returns:
            Response (parsed JSON or text for SSE)

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        try:
            # Build headers with JWT auth
            request_headers = {
                "Authorization": f"Bearer {self.token_manager.get_valid_token()}",
                "Content-Type": "application/json",
                "Accept": "application/json,text/event-stream",  # MCP requires both
            }
            if headers:
                request_headers.update(headers)

            # Make request
            response = await self.client.request(
                method=method,
                url=url,
                json=json_data,
                headers=request_headers,
            )

            # Raise on HTTP error
            response.raise_for_status()

            # Return text for SSE, JSON for others
            content_type = response.headers.get("content-type", "")
            if "text/event-stream" in content_type:
                return response.text
            else:
                return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(
                "mcp_http_error",
                method=method,
                url=url,
                status_code=e.response.status_code,
                response_body=e.response.text[:500] if hasattr(e.response, 'text') else 'N/A',
            )
            raise
        except Exception as e:
            logger.error(
                "mcp_request_failed",
                method=method,
                url=url,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    def _parse_sse_response(self, sse_text: str) -> Any:
        """Parse SSE response to extract JSON-RPC result.

        SSE format:
            data: {"jsonrpc":"2.0","id":"123","result":{"content":[...]}}

            data: [DONE]

        Args:
            sse_text: Raw SSE text

        Returns:
            Parsed result from JSON-RPC response

        Raises:
            ValueError: If format is invalid
        """
        logger.debug("parsing_sse_response", response_preview=sse_text[:200])

        lines = sse_text.strip().split("\n")

        for line in lines:
            line = line.strip()

            # Skip empty lines and [DONE] marker
            if not line or line == "data: [DONE]":
                continue

            # Extract JSON from "data: {json}"
            if line.startswith("data: "):
                json_str = line[6:]  # Remove "data: " prefix

                try:
                    rpc_response = json.loads(json_str)

                    # Extract result from JSON-RPC 2.0 response
                    if "result" in rpc_response:
                        logger.info("sse_result_parsed", has_content="content" in rpc_response.get("result", {}))
                        return rpc_response["result"]
                    elif "error" in rpc_response:
                        error = rpc_response["error"]
                        error_msg = f"MCP tool error: {error.get('message', 'Unknown error')}"
                        logger.error("mcp_tool_error", error_message=error_msg, error_code=error.get('code'))
                        raise ValueError(error_msg)

                except json.JSONDecodeError as e:
                    logger.error("sse_json_parse_failed", line=line[:200], error=str(e))
                    continue

        logger.error("no_valid_sse_result", sse_lines_count=len(lines), response_preview=sse_text[:500])
        raise ValueError(f"No valid JSON-RPC result found in SSE response. Received {len(lines)} lines.")

    async def close(self) -> None:
        """Close HTTP client and cleanup connections."""
        await self.client.aclose()
        logger.info("mcp_client_closed")
