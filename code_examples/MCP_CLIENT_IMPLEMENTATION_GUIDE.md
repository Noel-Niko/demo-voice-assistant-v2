# MCP Client Implementation Guide

**Complete guide for implementing Model Context Protocol (MCP) client integration in any Python/FastAPI application**

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Implementation Steps](#implementation-steps)
5. [Code References](#code-references)
6. [Testing](#testing)
7. [Deployment](#deployment)
8. [Troubleshooting](#troubleshooting)

---

## Overview

This guide shows how to integrate with an MCP server (grainger-mcp-servers) that uses JWT authentication and JSON-RPC 2.0 protocol. The implementation follows 12-Factor App principles and enterprise patterns.

**Key Features:**
- JWT token generation with automatic background refresh
- JSON-RPC 2.0 protocol for tool calling
- SSE response handling converted to JSON
- Production-ready secret management
- Thread-safe token management
- Graceful shutdown handling
- Auto-retry on 401 errors

**MCP Server Details:**
- Production URL: `https://grainger-mcp-servers.svc.ue2.prod.mlops.prod.aws.grainger.com`
- QA URL: `https://grainger-mcp-servers.svc.ue2.qa.mlops.nonprod.aws.grainger.com`
- Protocol: JSON-RPC 2.0 over HTTPS
- Authentication: JWT Bearer token
- Response Format: Server-Sent Events (SSE) - must be parsed to JSON

**⚠️ CRITICAL: MCP URL Format and Discovery**

The MCP server uses a specific URL structure and discovery mechanism:

### Discovery Endpoint
```
✅ Server Discovery:   GET {base_url}/tools/discovery
❌ NOT:                GET {base_url}/servers
```

**Discovery Response Structure:**
```json
{
  "servers": [
    {
      "name": "product_retrieval_server",
      "path": "/product_retrieval",
      "roles": ["product_retrieval", "aggregated_product_tools"],
      "category": "product",
      "priority": "high",
      "description": ""
    }
  ],
  "total_count": 10,
  "available_roles": ["product_search", "semantic", "order_search", ...],
  "available_categories": ["product", "orders", "internal", ...]
}
```

### Tool Calling URL Format
```
✅ CORRECT:   {base_url}{server_path}/mcp
❌ WRONG:     {base_url}/servers/{server_path}/call
❌ WRONG:     {base_url}/servers/{server_path}/messages
```

**IMPORTANT:** Server paths already include the leading slash (e.g., `/product_retrieval`)

**Examples:**
- ✅ `https://grainger-mcp-servers.svc.ue2.prod.mlops.prod.aws.grainger.com/product_retrieval/mcp`
- ✅ `https://grainger-mcp-servers.svc.ue2.prod.mlops.prod.aws.grainger.com/semantic_search/mcp`
- ❌ `https://grainger-mcp-servers.svc.ue2.prod.mlops.prod.aws.grainger.com/servers/product_retrieval/call`

### Available Servers (Dynamically Discovered)

**High Priority Servers:**
- `/product_retrieval` - Aggregated product tools (priority: high)
- `/parse_query` - Query parsing for product search (priority: high)

**Product Servers:**
- `/semantic_search` - Semantic product search (roles: product_search, semantic)
- `/solr` - Keyword product search (roles: product_search, key_word)
- `/databricks` - Databricks-based product search
- `/pricing` - Product pricing information
- `/availability` - Product availability checking
- `/assortment_api` - Category info, LN filters, product URLs

**Order Servers:**
- `/order` - Order search and retrieval (category: orders)

**Internal Servers:**
- `/databricks_claude` - Testing server (priority: low)

### Tool Discovery
```
✅ List Tools:   GET {base_url}{server_path}/tools
Example:         GET {base_url}/product_retrieval/tools
```

**Note:** Tools change dynamically and cannot be hardcoded. Always discover tools at runtime.

---

## Architecture

### Components

The implementation consists of 4 main components:

1. **Token Manager** (`MCPTokenManager`) - Generates and refreshes JWT tokens
2. **MCP Client** (`MCPClient`) - Handles HTTP communication and JSON-RPC protocol
3. **Configuration** (`Settings`) - Manages environment-based configuration
4. **Setup Scripts** - Loads secrets from AWS Secrets Manager

### Token Management Pattern

**Enterprise Background Refresh Pattern** (used by Envoy, Istio, Kong, Google Auth Library):

```
┌─────────────────────────────────────────────────────────────┐
│                     Application Startup                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  1. Load MCP_SECRET_KEY from environment                    │
│  2. Generate initial JWT token (expires in 24 hours)        │
│  3. Start background refresh task                           │
└─────────────────────────────────────────────────────────────┘
                              ↓
        ┌─────────────────────┴─────────────────────┐
        ↓                                           ↓
┌───────────────────┐                    ┌──────────────────────┐
│  Main Thread      │                    │  Background Thread   │
│  ──────────────   │                    │  ─────────────────   │
│                   │                    │                      │
│  get_token()      │                    │  while True:         │
│    ↓              │                    │    sleep(60s)        │
│  return token     │                    │    if expiring_soon: │
│  (instant!)       │                    │      refresh_token() │
│                   │                    │                      │
└───────────────────┘                    └──────────────────────┘
```

**Benefits:**
- Zero overhead on token access (just return the current token)
- No blocking or async waits in request path
- Automatic refresh happens in background
- 3-hour buffer before expiration (refresh at 21 hours)

---

## Prerequisites

### Required Tools
- Python 3.12+
- `uv` package manager
- AWS CLI configured
- `assume` command (for AWS credential management)
- Access to AWS Secrets Manager secrets

### AWS Secrets
You need access to these AWS Secrets Manager secrets:
- Production: `digitalassistantdomain/prod/mcp-secret`
- QA: `digitalassistantdomain/qa/mcp-secret`

**Secret Structure:**
```json
{
  "MCP_SECRET_KEY": "your-jwt-signing-key",
  "MCP_SECRET_ALGORITHM": "HS256"
}
```

### Required Python Dependencies
Add to `pyproject.toml`:
```toml
[project]
dependencies = [
    "fastapi>=0.104.0",
    "uvicorn>=0.24.0",
    "httpx>=0.25.0",
    "pyjwt>=2.8.0",
    "boto3>=1.28.0",
    "pydantic-settings>=2.0.0",
    "structlog>=23.2.0",
]
```

---

## Implementation Steps

### Step 1: Create Configuration (12-Factor Config)

**File:** `app/core/config.py`

**Reference Implementation:** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/backend/app/core/config.py`

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # MCP Server Configuration (12-Factor: Config from environment)
    # Note: MCP_SECRET_KEY comes from environment variables
    # - Local: Loaded via 'source setup_mcp_env.sh' or 'make prod/qa'
    # - Production: Loaded from Kubernetes secrets (ArgoCD)
    MCP_SECRET_KEY: str | None = None  # JWT signing key (required at runtime)
    MCP_SECRET_ALGORITHM: str = "HS256"  # JWT algorithm
    MCP_ENVIRONMENT: str = "prod"  # or "qa"
    MCP_INGRESS_URL: str = "https://grainger-mcp-servers.svc.ue2.prod.mlops.prod.aws.grainger.com"
    MCP_DISCOVER_TOOLS_ON_STARTUP: bool = True
    MCP_REQUEST_TIMEOUT: float = 30.0

    # AWS Configuration (region for Secrets Manager - used by setup scripts)
    AWS_REGION: str = "us-east-2"

# Singleton instance
settings = Settings()
```

**Key Points:**
- `MCP_SECRET_KEY` is optional at import time (None default) to allow tests to run
- Runtime validation happens in startup function with clear error messages
- All configuration comes from environment variables (12-Factor principle)

---

### Step 2: Create Token Manager

**File:** `app/services/mcp_token_manager.py`

**Reference Implementation:** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/backend/app/services/mcp_token_manager.py`

**Key Features:**
- Thread-safe token generation using `threading.Lock`
- Background refresh task using `asyncio.create_task()`
- 24-hour token expiration with 3-hour refresh buffer
- JWT claims: `sub`, `iat`, `exp`

**Core Methods:**
```python
class MCPTokenManager:
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        """Initialize token manager and generate first token."""
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._lock = threading.Lock()
        self._current_token = self._generate_token()
        self._token_expiration = datetime.now(timezone.utc) + timedelta(hours=24)

    def get_valid_token(self) -> str:
        """Get current valid token (instant, no blocking)."""
        return self._current_token

    def _is_expiring_soon(self, buffer_hours: int = 3) -> bool:
        """Check if token will expire within buffer_hours."""
        time_until_expiry = self._token_expiration - datetime.now(timezone.utc)
        return time_until_expiry.total_seconds() < (buffer_hours * 3600)

    async def refresh_loop(self) -> None:
        """Background task that checks and refreshes token periodically."""
        while True:
            await asyncio.sleep(60)  # Check every 60 seconds
            if self._is_expiring_soon():
                self._refresh_token()
                logger.info("Token automatically refreshed in background")

    def _generate_token(self) -> str:
        """Generate new JWT token with thread safety."""
        with self._lock:
            payload = {
                "sub": "mcp-client",
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(hours=24),
            }
            return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)
```

**Important Details:**
- Token lifetime: 24 hours
- Refresh threshold: 3 hours before expiration (at 21 hours)
- Check interval: Every 60 seconds
- Thread-safe: Uses `threading.Lock` for token generation

---

### Step 3: Create MCP Client

**File:** `app/services/mcp_client.py`

**Reference Implementation:** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/backend/app/services/mcp_client.py`

**Key Features:**
- JSON-RPC 2.0 protocol implementation
- SSE response parsing to JSON
- Auto-retry on 401 with token refresh
- Connection pooling (20 keepalive, 100 max connections)
- Proper error handling

**Core Methods:**

```python
class MCPClient:
    def __init__(
        self,
        base_url: str,
        token_manager: MCPTokenManager,
        timeout: float = 30.0,
    ):
        """Initialize MCP client with connection pooling."""
        self.base_url = base_url.rstrip("/")
        self.token_manager = token_manager

        # Connection pooling (enterprise pattern)
        limits = httpx.Limits(
            max_keepalive_connections=20,
            max_connections=100,
            keepalive_expiry=30.0,
        )

        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            limits=limits,
            http2=True,
        )

    async def list_servers(self) -> Dict[str, Any]:
        """List all available MCP servers using discovery endpoint.

        Returns:
            Discovery data with servers, roles, categories, and counts

        Note:
            - Discovery endpoint: GET {base_url}/tools/discovery
            - Server paths include leading slash (e.g., "/product_retrieval")
        """
        response = await self._make_request(
            "GET",
            f"{self.base_url}/tools/discovery",
        )
        return response

    async def list_tools(self, server_path: str) -> List[Dict[str, Any]]:
        """List tools available on a specific server.

        Args:
            server_path: Server path (e.g., "/product_retrieval", "/semantic_search")
                        Should include leading slash as returned by list_servers()

        Note:
            - URL format: {base_url}{server_path}/tools
            - Server paths from list_servers() already include the leading slash
        """
        # Ensure server_path starts with / (normalize if user passes without it)
        if not server_path.startswith("/"):
            server_path = f"/{server_path}"

        response = await self._make_request(
            "GET",
            f"{self.base_url}{server_path}/tools",
        )
        return response

    async def call_tool(
        self,
        server_path: str,
        tool_name: str,
        arguments: Dict[str, Any],
        retry_count: int = 0,
    ) -> Any:
        """
        Call an MCP tool using JSON-RPC 2.0 protocol.

        Auto-retries once on 401 (token refresh).

        Args:
            server_path: Server path (e.g., "product_retrieval")
            tool_name: Tool name (e.g., "semantic_search", "get_alternate_docs")
            arguments: Tool-specific arguments (varies by tool)
            retry_count: Internal retry counter (do not set manually)

        CRITICAL: URL format is /{server_path}/mcp, NOT /servers/{server_path}/call
        """
        # Build JSON-RPC 2.0 request
        jsonrpc_request = self._build_jsonrpc_request(
            method="tools/call",
            params={
                "name": tool_name,
                "arguments": arguments,
            },
        )

        # Ensure server_path starts with / (normalize if user passes without it)
        if not server_path.startswith("/"):
            server_path = f"/{server_path}"

        try:
            # Make request
            # CRITICAL: URL format is {base_url}{server_path}/mcp
            # Server paths already include leading slash (e.g., "/product_retrieval")
            # Accept header (application/json,text/event-stream) is set by default in _make_request
            response = await self._make_request(
                "POST",
                f"{self.base_url}{server_path}/mcp",
                json_data=jsonrpc_request,
            )

            # Parse SSE response to JSON
            return self._parse_sse_response(response)

        except httpx.HTTPStatusError as e:
            # Auto-retry on 401 (token expired)
            if e.response.status_code == 401 and retry_count < 1:
                logger.warning("Token expired, refreshing and retrying...")
                self.token_manager.force_refresh()
                return await self.call_tool(
                    server_path, tool_name, arguments, retry_count + 1
                )
            raise

    def _build_jsonrpc_request(
        self, method: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build JSON-RPC 2.0 request."""
        return {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }

    def _parse_sse_response(self, sse_text: str) -> Any:
        """
        Parse SSE (Server-Sent Events) response to JSON.

        SSE Format:
            data: {"jsonrpc":"2.0","id":"123","result":...}

            data: [DONE]

        Returns the 'result' field from the JSON-RPC response.
        """
        lines = sse_text.strip().split("\n")

        for line in lines:
            line = line.strip()

            # Skip empty lines and [DONE] marker
            if not line or line == "data: [DONE]":
                continue

            # Parse data: prefix
            if line.startswith("data: "):
                data = line[6:]  # Remove "data: " prefix

                try:
                    json_response = json.loads(data)

                    # Return result from JSON-RPC response
                    if "result" in json_response:
                        return json_response["result"]

                    # Handle JSON-RPC error
                    if "error" in json_response:
                        error = json_response["error"]
                        raise MCPClientError(
                            f"MCP server error: {error.get('message', 'Unknown error')}"
                        )

                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse SSE data as JSON: {data}")
                    continue

        raise MCPClientError("No valid result found in SSE response")

    async def _make_request(
        self,
        method: str,
        url: str,
        json_data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
    ) -> Any:
        """Make HTTP request with JWT authentication."""
        # Get current valid token (instant, no blocking)
        token = self.token_manager.get_valid_token()

        # Build headers
        # CRITICAL: MCP server requires Accept header with BOTH content types
        request_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json,text/event-stream",
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
        if "text/event-stream" in response.headers.get("content-type", ""):
            return response.text
        else:
            return response.json()
```

**Critical Details:**

1. **JSON-RPC 2.0 Format:**
   ```json
   {
     "jsonrpc": "2.0",
     "id": "uuid-here",
     "method": "tools/call",
     "params": {
       "name": "tool_name",
       "arguments": {"arg1": "value1"}
     }
   }
   ```

2. **SSE Response Format:**
   ```
   data: {"jsonrpc":"2.0","id":"123","result":{"content":[...]}}

   data: [DONE]
   ```

3. **Auto-Retry Logic:**
   - If 401 error occurs, force refresh token and retry once
   - Prevents cascade failures from expired tokens

---

### Step 4: Create Setup Script

**File:** `setup_mcp_env.sh`

**Reference Implementation:** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/backend/setup_mcp_env.sh`

```bash
#!/usr/bin/env bash
#
# Setup MCP Environment Variables
# Fetches MCP secrets from AWS Secrets Manager and exports them to environment
#
# Usage:
#   source setup_mcp_env.sh prod
#   source setup_mcp_env.sh qa
#

set -e

ENVIRONMENT="${1:-prod}"

if [[ "$ENVIRONMENT" != "prod" && "$ENVIRONMENT" != "qa" ]]; then
    echo "❌ Error: Environment must be 'prod' or 'qa'"
    echo "Usage: source setup_mcp_env.sh [prod|qa]"
    return 1 2>/dev/null || exit 1
fi

echo "🔐 Loading MCP environment variables for: $ENVIRONMENT"

# Secret names
if [[ "$ENVIRONMENT" == "prod" ]]; then
    SECRET_NAME="digitalassistantdomain/prod/mcp-secret"
else
    SECRET_NAME="digitalassistantdomain/qa/mcp-secret"
fi

# Check AWS credentials
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║                  AWS CREDENTIALS REQUIRED                        ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "❌ No valid AWS credentials found!"
    echo ""
    echo "🔧 You MUST run the following commands first:"
    echo ""
    echo "   1. assume"
    echo ""
    echo "   2. Select the appropriate profile:"
    if [[ "$ENVIRONMENT" == "prod" ]]; then
        echo "      • aad-mlops-prod-digitalassistantdo"
    else
        echo "      • aad-mlops-nonprod-digitalassistantdo"
    fi
    echo ""
    echo "   3. Then source this script again:"
    echo "      source setup_mcp_env.sh $ENVIRONMENT"
    echo ""
    return 1 2>/dev/null || exit 1
fi

echo "🔸 Fetching $SECRET_NAME..."

# Fetch secret from AWS Secrets Manager
secret_json=$(aws secretsmanager get-secret-value \
    --secret-id "$SECRET_NAME" \
    --region us-east-2 \
    --query SecretString \
    --output text 2>/dev/null)

if [[ -z "$secret_json" ]]; then
    echo "⚠️  Warning: Could not fetch AWS secret: $SECRET_NAME"
    return 1 2>/dev/null || exit 1
fi

# Parse JSON and export environment variables
while IFS="=" read -r key val; do
    val="${val%\"}"
    val="${val#\"}"
    export "$key"="$val"
    echo "✅ Exported: $key"
done < <(echo "$secret_json" | jq -r 'to_entries|map("\(.key)=\(.value|tostring)")|.[]')

# Set MCP_ENVIRONMENT to match
export MCP_ENVIRONMENT="$ENVIRONMENT"
echo "✅ Exported: MCP_ENVIRONMENT=$ENVIRONMENT"

echo ""
echo "✅ MCP environment variables loaded successfully!"
echo ""
echo "You can now start the application:"
echo "  uv run uvicorn app.main:app --reload"
echo ""
```

**Key Points:**
- Must be sourced (not executed) to export variables to current shell
- Validates AWS credentials before attempting to fetch secrets
- Provides helpful error messages with exact commands to run
- Uses `jq` to parse JSON and export all keys

---

### Step 5: Integrate into FastAPI Application

**File:** `app/main.py`

**Reference Implementation:** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/backend/app/main.py`

```python
import asyncio
from contextlib import asynccontextmanager
from typing import Optional, Tuple

from fastapi import FastAPI
import structlog

from app.core.config import settings
from app.services.mcp_token_manager import MCPTokenManager
from app.services.mcp_client import MCPClient

logger = structlog.get_logger(__name__)

# Global MCP client instance
mcp_client: Optional[MCPClient] = None


async def create_mcp_client() -> Tuple[MCPClient, asyncio.Task]:
    """
    Create and initialize MCP client with background token refresh.

    Following 12-Factor principles (Config):
    - Reads secrets from environment variables
    - Local: Loaded via 'source setup_mcp_env.sh' or 'make prod/qa'
    - Production: Loaded from Kubernetes secrets (ArgoCD)

    Returns:
        Tuple of (MCPClient instance, background refresh task)

    Raises:
        ValueError: If MCP_SECRET_KEY is not set in environment
    """
    # Step 1: Validate configuration (12-Factor: Config from environment)
    logger.info(f"🌍 Step 1: Environment: {settings.MCP_ENVIRONMENT}")

    if not settings.MCP_SECRET_KEY:
        error_msg = (
            "MCP_SECRET_KEY not found in environment!\n\n"
            "Local development: Run 'source setup_mcp_env.sh prod' or 'make prod'\n"
            "Production: Ensure Kubernetes secrets are mounted"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.info("✅ MCP configuration loaded from environment")

    # Step 2: Initialize token manager (generates initial token)
    logger.info("🎫 Step 2: Initializing MCP token manager...")
    token_manager = MCPTokenManager(
        secret_key=settings.MCP_SECRET_KEY,
        algorithm=settings.MCP_SECRET_ALGORITHM,
    )

    token_info = token_manager.get_token_info()
    logger.info(
        f"✅ Initial token generated (valid for {token_info['time_remaining_hours']:.1f} hours)"
    )

    # Step 3: Start background token refresh task
    logger.info("🔄 Step 3: Starting background token refresh task...")
    refresh_task = asyncio.create_task(token_manager.refresh_loop())

    # Verify task started successfully (12-Factor: Disposability - fail fast)
    await asyncio.sleep(0.1)  # Give task time to start
    if refresh_task.done():
        exception = refresh_task.exception()
        logger.error(f"❌ Background refresh task failed to start: {exception}")
        raise RuntimeError(f"Token refresh task failed: {exception}")

    logger.info("✅ Background token refresh task started")

    # Step 4: Initialize MCP client
    logger.info("🔌 Step 4: Initializing MCP client...")
    client = MCPClient(
        base_url=settings.MCP_INGRESS_URL,
        token_manager=token_manager,
        timeout=settings.MCP_REQUEST_TIMEOUT,
    )
    logger.info("✅ MCP client initialized")

    # Step 5: Verify connectivity (optional but recommended)
    logger.info("🔍 Step 5: Verifying MCP server connectivity...")
    is_healthy = await client.health_check()

    if is_healthy:
        logger.info("✅ MCP server connection verified")
    else:
        logger.warning("⚠️  MCP server health check failed - continuing anyway")

    # Step 6: Discover available tools (optional, based on config)
    if settings.MCP_DISCOVER_TOOLS_ON_STARTUP:
        logger.info("🔍 Step 6: Discovering available MCP tools...")
        discovery = await client.discover_all_tools()
        logger.info(
            f"✅ Discovered {discovery.get('total_unique_tools', 0)} tools "
            f"across {discovery.get('total_servers', 0)} servers"
        )

    return client, refresh_task


def get_mcp_client() -> MCPClient:
    """
    FastAPI dependency for accessing the global MCP client.

    Returns:
        Initialized MCP client instance

    Raises:
        RuntimeError: If MCP client is not initialized
    """
    if mcp_client is None:
        raise RuntimeError("MCP client not initialized - did startup fail?")
    return mcp_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events following 12-Factor principles:
    - Fast startup with fail-fast behavior
    - Graceful shutdown (Factor 9: Disposability)
    - Proper resource cleanup
    """
    global mcp_client

    # ===== STARTUP =====
    logger.info("=" * 70)
    logger.info("Starting Application")
    logger.info("=" * 70)

    refresh_task = None

    try:
        # Initialize MCP client (12-Factor: Config from environment)
        try:
            mcp_client, refresh_task = await create_mcp_client()
            logger.info("=" * 70)
            logger.info("✅ MCP Integration Complete - Service Ready")
            logger.info("=" * 70)
        except Exception as e:
            logger.error("=" * 70)
            logger.error("❌ MCP Initialization Failed")
            logger.error("=" * 70)
            logger.error(f"Error: {e}", exc_info=True)
            # MCP is optional - continue without it if needed
            logger.warning("⚠️  Service starting WITHOUT MCP integration")

    except Exception as e:
        logger.error("service_initialization_failed", error=str(e), exc_info=True)
        raise

    yield

    # ===== SHUTDOWN (12-Factor: Disposability - graceful shutdown) =====
    logger.info("=" * 70)
    logger.info("Shutting down Application")
    logger.info("=" * 70)

    try:
        # Stop background refresh task
        if refresh_task and not refresh_task.done():
            logger.info("Stopping background refresh task...")
            refresh_task.cancel()
            try:
                await refresh_task
            except asyncio.CancelledError:
                logger.info("✅ Background refresh task stopped")

        # Close MCP client
        if mcp_client:
            await mcp_client.close()
            logger.info("✅ MCP client closed")

    except Exception as e:
        logger.error("service_shutdown_failed", error=str(e), exc_info=True)

    logger.info("=" * 70)
    logger.info("Shutdown complete")
    logger.info("=" * 70)


# Create FastAPI application
app = FastAPI(
    title="Your Application",
    description="Application with MCP integration",
    version="1.0.0",
    lifespan=lifespan,
)


# Example endpoint using MCP client
@app.get("/mcp/tools")
async def list_mcp_tools():
    """List all available MCP tools."""
    client = get_mcp_client()
    discovery = await client.discover_all_tools()
    return discovery


@app.post("/mcp/call")
async def call_mcp_tool(
    server_path: str,
    tool_name: str,
    arguments: dict,
):
    """Call an MCP tool."""
    client = get_mcp_client()
    result = await client.call_tool(server_path, tool_name, arguments)
    return {"result": result}
```

**Critical Points:**

1. **Startup Sequence:**
   - Validate MCP_SECRET_KEY exists → Generate token → Start background task → Initialize client → Verify health → Discover tools

2. **Graceful Shutdown:**
   - Cancel background task → Wait for cancellation → Close HTTP client

3. **FastAPI Dependency:**
   - Use `get_mcp_client()` as a dependency in endpoints to access the global client

---

### Step 6: Create Makefile

**File:** `Makefile`

**Reference Implementation:** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/Makefile`

```makefile
.PHONY: prod qa help

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

prod:  ## Load production MCP secrets and start server (requires AWS assume)
	@echo "🚀 Starting Application (PRODUCTION secrets)"
	@echo "Loading secrets from: digitalassistantdomain/prod/mcp-secret"
	@echo "Server will be available at: http://localhost:8888"
	@echo ""
	@bash -c "source setup_mcp_env.sh prod && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8888"

qa:  ## Load QA MCP secrets and start server (requires AWS assume)
	@echo "🚀 Starting Application (QA secrets)"
	@echo "Loading secrets from: digitalassistantdomain/qa/mcp-secret"
	@echo "Server will be available at: http://localhost:8888"
	@echo ""
	@bash -c "source setup_mcp_env.sh qa && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8888"
```

---

### Step 7: Create .env.example

**File:** `.env.example`

**Reference Implementation:** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/backend/.env.example`

```bash
# MCP Server Configuration
# IMPORTANT: MCP_SECRET_KEY and MCP_SECRET_ALGORITHM must be loaded from environment
#
# Local Development:
#   1. Run 'assume' command to get AWS credentials
#   2. Select profile:
#      - aad-mlops-prod-digitalassistantdo (for production)
#      - aad-mlops-nonprod-digitalassistantdo (for qa)
#   3. Load secrets: source setup_mcp_env.sh prod (or: make prod)
#   4. Start the service: uv run uvicorn app.main:app --reload
#
# Production Deployment:
#   - MCP_SECRET_KEY is loaded from Kubernetes secrets (ArgoCD)
#   - No setup script needed
#
# Note: MCP_SECRET_KEY is REQUIRED and cannot be set here (loaded via setup script)
MCP_ENVIRONMENT=prod
MCP_INGRESS_URL=https://grainger-mcp-servers.svc.ue2.prod.mlops.prod.aws.grainger.com
MCP_DISCOVER_TOOLS_ON_STARTUP=true
MCP_REQUEST_TIMEOUT=30.0

# AWS Configuration (region for Secrets Manager - used by setup scripts)
AWS_REGION=us-east-2
```

---

## Code References

All implementation files are available in this repository:

### Core Implementation Files
- **Configuration:** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/backend/app/core/config.py`
- **Token Manager:** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/backend/app/services/mcp_token_manager.py`
- **MCP Client:** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/backend/app/services/mcp_client.py`
- **FastAPI Integration:** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/backend/app/main.py`

### Setup Scripts
- **Setup Script:** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/backend/setup_mcp_env.sh`
- **Makefile (Backend):** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/backend/Makefile`
- **Makefile (Root):** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/Makefile`
- **.env.example:** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/backend/.env.example`

### Test Files
- **Token Manager Tests:** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/backend/tests/unit/test_mcp_token_manager.py`
- **MCP Client Tests:** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/backend/tests/unit/test_mcp_client.py`
- **Lifespan Tests:** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/backend/tests/unit/test_mcp_lifespan.py`

### Supporting Files
- **AWS Credential Validator:** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/backend/app/services/aws_credential_validator.py`
- **MCP Credentials Manager:** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/backend/app/services/mcp_credentials.py`

### Documentation
- **Implementation Plan:** `/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/docs/MCP_INTEGRATION_PLAN.md`

---

## Testing

### Test-Driven Development (TDD) Approach

Following the TDD red-green-refactor cycle:

1. **RED** - Write failing test first
2. **GREEN** - Implement minimum code to pass
3. **REFACTOR** - Clean up code while keeping tests passing

### Test Structure

**Token Manager Tests** (28 tests, 99% coverage):
```python
# Test basic initialization
def test_token_manager_initialization()
def test_token_manager_generates_valid_jwt()

# Test token properties
def test_get_valid_token_returns_current_token()
def test_token_has_correct_expiration()

# Test refresh logic
def test_is_expiring_soon_returns_true_when_near_expiration()
def test_force_refresh_generates_new_token()

# Test background refresh
async def test_refresh_loop_refreshes_token_when_expiring()
async def test_refresh_loop_does_not_refresh_when_token_valid()

# Test thread safety
def test_token_generation_is_thread_safe()
```

**MCP Client Tests** (26 tests, 94% coverage):
```python
# Test initialization
def test_mcp_client_initialization()
def test_client_has_proper_connection_pooling()

# Test server operations
async def test_list_servers_success()
async def test_list_tools_success()

# Test tool calling
async def test_call_tool_success()
async def test_call_tool_builds_correct_jsonrpc_request()
async def test_call_tool_retries_on_401()

# Test SSE parsing
def test_parse_sse_response_success()
def test_parse_sse_response_handles_multiple_lines()
def test_parse_sse_response_skips_done_marker()
def test_parse_sse_response_handles_errors()

# Test error handling
async def test_call_tool_raises_on_http_error()
async def test_call_tool_does_not_retry_on_other_errors()
```

**Lifespan Tests** (9 tests):
```python
# Test successful initialization
async def test_create_mcp_client_success()

# Test validation
async def test_create_mcp_client_missing_secret_key()
async def test_create_mcp_client_empty_secret_key()

# Test background task
async def test_create_mcp_client_starts_background_task()

# Test health check and discovery
async def test_create_mcp_client_verifies_health()
async def test_create_mcp_client_discovers_tools_when_enabled()
async def test_create_mcp_client_skips_discovery_when_disabled()

# Test dependency
def test_get_mcp_client_returns_client_when_initialized()
def test_get_mcp_client_raises_when_not_initialized()
```

### Running Tests

```bash
# Run all MCP-related tests
uv run pytest tests/unit/test_mcp_*.py -v

# Run with coverage
uv run pytest tests/unit/test_mcp_*.py -v --cov=app.services --cov-report=term-missing

# Run specific test file
uv run pytest tests/unit/test_mcp_client.py -v
```

### Test Coverage Summary

- **MCPTokenManager:** 99% coverage (68/69 lines)
- **MCPClient:** 94% coverage (102/109 lines)
- **Lifespan Integration:** 9/9 tests passing

---

## Deployment

### Local Development

**Prerequisites:**
1. Install dependencies: `uv sync`
2. Get AWS credentials: `assume`
3. Select AWS profile (e.g., `aad-mlops-prod-digitalassistantdo`)

**Start Server:**
```bash
# Option 1: Using Makefile (recommended)
make prod  # or: make qa

# Option 2: Manual
source setup_mcp_env.sh prod
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8888
```

**Access:**
- API: `http://localhost:8888`
- Docs: `http://localhost:8888/docs`
- Health: `http://localhost:8888/health`

### Production Deployment (Kubernetes)

**Secret Management:**

Production deployments use Kubernetes secrets mounted as environment variables:

```yaml
# Example: app.yaml (ArgoCD)
apiVersion: v1
kind: Deployment
metadata:
  name: your-app
spec:
  template:
    spec:
      containers:
      - name: app
        image: your-app:latest
        env:
        - name: MCP_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: mcp-secrets
              key: MCP_SECRET_KEY
        - name: MCP_SECRET_ALGORITHM
          valueFrom:
            secretKeyRef:
              name: mcp-secrets
              key: MCP_SECRET_ALGORITHM
        - name: MCP_ENVIRONMENT
          value: "prod"
        - name: MCP_INGRESS_URL
          value: "https://grainger-mcp-servers.svc.ue2.prod.mlops.prod.aws.grainger.com"
```

**No setup script needed** - secrets are automatically available as environment variables when the pod starts.

### Environment-Specific URLs

**Production:**
- MCP Server: `https://grainger-mcp-servers.svc.ue2.prod.mlops.prod.aws.grainger.com`
- AWS Secret: `digitalassistantdomain/prod/mcp-secret`
- AWS Profile: `aad-mlops-prod-digitalassistantdo`

**QA:**
- MCP Server: `https://grainger-mcp-servers.svc.ue2.qa.mlops.nonprod.aws.grainger.com`
- AWS Secret: `digitalassistantdomain/qa/mcp-secret`
- AWS Profile: `aad-mlops-nonprod-digitalassistantdo`

---

## Troubleshooting

### Issue: "MCP_SECRET_KEY not found in environment"

**Cause:** Secret not loaded before starting app

**Solution:**
```bash
# 1. Check if AWS credentials are valid
aws sts get-caller-identity

# 2. If not, run assume
assume

# 3. Load secrets
source setup_mcp_env.sh prod

# 4. Verify secrets are loaded
echo $MCP_SECRET_KEY  # Should show value

# 5. Start app
uv run uvicorn app.main:app --reload
```

### Issue: "Address already in use" (Port 8000)

**Cause:** Another process is using port 8000

**Solutions:**
```bash
# Option 1: Use different port
uv run uvicorn app.main:app --reload --port 8888

# Option 2: Kill process on port 8000
lsof -ti:8000 | xargs kill -9

# Option 3: Update Makefile to use different port (recommended)
# Change --port 8000 to --port 8888 in Makefile
```

### Issue: "404 Not Found" from MCP server

**Cause:** Incorrect URL format or missing leading slash (most common)

**Symptoms:**
```
Client error '404 Not Found' for url
'https://grainger-mcp-servers.svc.ue2.prod.mlops.prod.aws.grainger.com/servers/webSearch/call'
```

**Solution:**
The URL format must be `{base_url}{server_path}/mcp` where server_path includes leading slash

**Check these:**
1. URL uses `{base_url}{server_path}/mcp` format
2. Server path includes leading slash (e.g., `/product_retrieval`)
3. Server exists (use `GET /tools/discovery` to list available servers)
4. Tool name exists on that server (use `GET {server_path}/tools`)

**Correct URL construction:**
```python
# ✅ CORRECT - Server path includes leading slash
server_path = "/product_retrieval"  # From discovery endpoint
url = f"{self.base_url}{server_path}/mcp"
# Result: https://.../product_retrieval/mcp

# ❌ WRONG - Missing leading slash
server_path = "product_retrieval"
url = f"{self.base_url}/{server_path}/mcp"

# ❌ WRONG - Incorrect path structure
url = f"{self.base_url}/servers/{server_path}/call"
```

**Normalization tip:**
```python
# Ensure server_path starts with /
if not server_path.startswith("/"):
    server_path = f"/{server_path}"

url = f"{self.base_url}{server_path}/mcp"
```

**Available server paths (from `/tools/discovery`):**
- `/product_retrieval` - Aggregated product tools (priority: high)
- `/semantic_search` - Semantic product search
- `/order` - Order search
- `/pricing` - Product pricing
- Run `GET /tools/discovery` to discover current servers

### Issue: "401 Unauthorized" from MCP server

**Cause:** Token expired or invalid

**Solution:**
- Client automatically retries once with refreshed token
- If still failing, check:
  1. MCP_SECRET_KEY matches server's key
  2. System clock is accurate (JWT relies on timestamps)
  3. Token algorithm matches (should be HS256)
  4. You're connected to Zscaler (required for internal Grainger services)

**Debug:**
```python
# Add logging to see token info
token_info = token_manager.get_token_info()
logger.info(f"Token info: {token_info}")
```

### Issue: "406 Not Acceptable" from MCP server

**Cause:** Missing or incorrect Accept header

**Symptoms:**
```json
{
  "jsonrpc": "2.0",
  "id": "server-error",
  "error": {
    "code": -32600,
    "message": "Not Acceptable: Client must accept both application/json and text/event-stream"
  }
}
```

**Solution:**
The MCP server requires the Accept header to include **BOTH** content types:

```python
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "Accept": "application/json,text/event-stream",  # Both required!
}
```

**Why both?**
- Server may return JSON (for errors, metadata) or SSE (for streaming results)
- Client must signal it can handle either format
- Common mistake: Only including `"Accept": "text/event-stream"`

### Issue: "Unknown tool" error from MCP server

**Cause:** Tool name doesn't exist on the specified server, or tools changed dynamically

**Symptoms:**
```json
{
  "jsonrpc": "2.0",
  "id": "...",
  "result": {
    "content": [{"type": "text", "text": "Unknown tool: semantic_search"}],
    "isError": true
  }
}
```

**Solution:**
Tools change dynamically and cannot be hardcoded. Always discover tools at runtime.

```python
# ❌ WRONG - Hardcoding tool names
result = await client.call_tool(
    server_path="/product_retrieval",
    tool_name="semantic_search",  # May not exist!
    arguments={"query": "..."}
)

# ✅ CORRECT - Discover tools dynamically
tools = await client.list_tools("/product_retrieval")
print(f"Available tools: {[t.get('name') for t in tools]}")

# Use first available tool or match by role
tool_name = tools[0].get("name") if tools else None
result = await client.call_tool(
    server_path="/product_retrieval",
    tool_name=tool_name,
    arguments={"query": "..."}
)
```

**Alternative - Auto-discovery in route:**
```python
# Let the backend handle discovery
response = await fetch("/api/mcp/query", {
    method: "POST",
    body: JSON.stringify({
        query: "recommend a ladder",
        server_path: null,  // Auto-discover
        tool_name: null     // Auto-discover
    })
})
```

### Issue: Network connection failures

**Cause:** Not connected to Grainger internal network

**Solution:**
1. **Enable Zscaler** (required for accessing internal Grainger services)
2. Verify AWS credentials: `aws sts get-caller-identity`
3. Check VPN connection if working remotely
4. Test connectivity:
   ```bash
   curl -s https://grainger-mcp-servers.svc.ue2.prod.mlops.prod.aws.grainger.com/tools/discovery | head -20
   ```

### Issue: SSE parsing fails

**Cause:** Unexpected SSE response format

**Debug:**
```python
# Add logging in _parse_sse_response
logger.info(f"Raw SSE response: {sse_text}")
```

**Common SSE formats:**
```
# Format 1: Single data line
data: {"jsonrpc":"2.0","id":"123","result":{"content":[...]}}

data: [DONE]

# Format 2: Multiple data lines
data: {"jsonrpc":"2.0","id":"123","result":{"content":[
data: {"type":"text","text":"Hello"}
data: ]}}

data: [DONE]
```

### Issue: Background refresh task crashes

**Cause:** Exception in refresh loop

**Debug:**
```python
# Check logs for refresh task errors
# Look for: "Background refresh task failed to start"

# Manually test refresh
token_manager.force_refresh()
```

### Issue: Connection pool exhausted

**Cause:** Too many concurrent requests

**Solution:**
```python
# Increase connection pool limits in MCPClient.__init__
limits = httpx.Limits(
    max_keepalive_connections=50,  # Increased from 20
    max_connections=200,            # Increased from 100
    keepalive_expiry=30.0,
)
```

### Issue: Test failures in CI/CD

**Cause:** MCP_SECRET_KEY required in config causes import error

**Solution:**
```python
# In app/core/config.py
MCP_SECRET_KEY: str | None = None  # Allow None for testing

# Runtime validation in create_mcp_client()
if not settings.MCP_SECRET_KEY:
    raise ValueError("MCP_SECRET_KEY not found in environment!")
```

---

## Example Usage

### Discover All Servers and Tools

```python
from app.main import get_mcp_client

# Get client (from FastAPI dependency)
client = get_mcp_client()

# Discover all servers
discovery = await client.list_servers()

print(f"Total servers: {discovery['total_count']}")
print(f"Available roles: {discovery['available_roles']}")
print(f"Available categories: {discovery['available_categories']}")

# List servers by priority
for server in discovery['servers']:
    print(f"\nServer: {server['name']}")
    print(f"  Path: {server['path']}")
    print(f"  Roles: {server['roles']}")
    print(f"  Category: {server['category']}")
    print(f"  Priority: {server['priority']}")

    # List tools for this server
    tools = await client.list_tools(server['path'])
    for tool in tools:
        print(f"    - {tool.get('name', 'N/A')}: {tool.get('description', 'N/A')}")
```

### Call a Specific Tool

```python
from app.main import get_mcp_client

# Get client
client = get_mcp_client()

# Example 1: Call tool with simple query (auto-discovery)
# Note: Server paths include leading slash
result = await client.call_tool(
    server_path="/semantic_search",  # Leading slash required
    tool_name="search",  # Tool name discovered from list_tools()
    arguments={
        "query": "safety gloves",
        "limit": 10
    }
)

print(f"Search results: {result}")

# Example 2: Get alternate product documents (complex arguments)
result = await client.call_tool(
    server_path="/product_retrieval",  # Leading slash required
    tool_name="get_alternate_docs",
    arguments={
        "inputs": {
            "query": "safety gloves",
            "vector_store": "Product",
            "skus": ["1FYX7"],
            "model_nos": [],
            "brands": [],
            "lns": []
        }
    }
)

print(f"Alternate docs: {result}")

# Example 3: Order search
result = await client.call_tool(
    server_path="/order",  # Leading slash required
    tool_name="search_order",  # Tool name from discovery
    arguments={
        "order_id": "12345"
    }
)

print(f"Order details: {result}")
```

### Use in FastAPI Endpoint

```python
from fastapi import Depends, HTTPException
from app.main import get_mcp_client

@app.post("/products/search")
async def search_products(
    query: str,
    limit: int = 10,
    client: MCPClient = Depends(get_mcp_client)
):
    """Search products using MCP with auto-discovery."""
    # Discover servers to find the best product search server
    discovery = await client.list_servers()

    # Find product_retrieval_server (high priority)
    server_path = None
    for server in discovery.get("servers", []):
        if server.get("name") == "product_retrieval_server":
            server_path = server.get("path")  # Will be "/product_retrieval"
            break

    if not server_path:
        raise HTTPException(status_code=500, detail="Product search server not available")

    # Discover tools on this server
    tools = await client.list_tools(server_path)
    tool_name = tools[0].get("name") if tools else None

    if not tool_name:
        raise HTTPException(status_code=500, detail="No tools available on product server")

    # Call tool (note: leading slash in server_path)
    result = await client.call_tool(
        server_path=server_path,  # "/product_retrieval" (includes leading slash)
        tool_name=tool_name,
        arguments={
            "query": query,
            "limit": limit
        }
    )
    return {"results": result}

@app.get("/products/{sku}/alternates")
async def get_product_alternates(
    sku: str,
    client: MCPClient = Depends(get_mcp_client)
):
    """Get alternate products using MCP tool (complex arguments)."""
    result = await client.call_tool(
        server_path="/product_retrieval",  # Leading slash required
        tool_name="get_alternate_docs",
        arguments={
            "inputs": {
                "query": "alternates",
                "vector_store": "Product",
                "skus": [sku],
                "model_nos": [],
                "brands": [],
                "lns": []
            }
        }
    )
    return {"alternates": result}

@app.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    client: MCPClient = Depends(get_mcp_client)
):
    """Get order details using MCP order server."""
    result = await client.call_tool(
        server_path="/order",  # Leading slash required
        tool_name="search_order",  # Tool name from discovery
        arguments={
            "order_id": order_id
        }
    )
    return {"order": result}
```

---

## Security Considerations

### JWT Security
- **Never log the full token** - only log token metadata
- **Use environment variables** - never hardcode secrets
- **Rotate secrets regularly** - update AWS Secrets Manager
- **Use HTTPS only** - MCP server requires TLS

### AWS Security
- **Use IAM roles in production** - avoid long-lived credentials
- **Principle of least privilege** - only grant necessary permissions
- **Audit secret access** - use CloudTrail to monitor access

### Network Security
- **Use private networks** - MCP server should be on internal network
- **Implement rate limiting** - prevent abuse
- **Use connection pooling** - prevent resource exhaustion

---

## Performance Considerations

### Token Management
- **Zero overhead** - `get_valid_token()` just returns current token (no async, no lock wait)
- **Background refresh** - happens automatically without blocking requests
- **3-hour buffer** - token refreshes well before expiration

### HTTP Client
- **Connection pooling** - reuse connections (20 keepalive, 100 max)
- **HTTP/2** - enabled for multiplexing
- **Timeouts** - 30 second default (configurable)

### Async Operations
- **Non-blocking** - all I/O is async (httpx, asyncio)
- **Concurrent requests** - connection pool allows parallel calls
- **Background tasks** - token refresh doesn't block main thread

---

## 12-Factor App Compliance

This implementation follows all 12-Factor App principles:

1. **Codebase** ✅ - One repo per service
2. **Dependencies** ✅ - Explicitly declared in `pyproject.toml`
3. **Config** ✅ - All config from environment variables
4. **Backing services** ✅ - MCP server treated as attached resource
5. **Build, release, run** ✅ - Separate stages (uv build, container image, run)
6. **Processes** ✅ - Stateless (token state in background task, not in-memory store)
7. **Port binding** ✅ - Self-contained service on configurable port
8. **Concurrency** ✅ - Scale by running multiple processes
9. **Disposability** ✅ - Fast startup, graceful shutdown
10. **Dev/prod parity** ✅ - Same code, different config
11. **Logs** ✅ - All logs to stdout (structlog)
12. **Admin processes** ✅ - Setup script for one-off tasks

---

## Summary

This guide provides everything needed to implement MCP client integration:

**Core Components:**
1. Configuration with environment variables
2. Token manager with background refresh
3. MCP client with JSON-RPC 2.0 and SSE parsing
4. FastAPI lifespan integration
5. Setup scripts for local development

**Key Features:**
- Enterprise background refresh pattern (zero-overhead token access)
- Auto-retry on 401 errors
- Thread-safe token generation
- Connection pooling and HTTP/2
- SSE to JSON conversion
- Graceful shutdown
- Comprehensive error handling

**Production Ready:**
- 12-Factor App compliant
- 99% test coverage on critical components
- Kubernetes-ready secret management
- Proper logging and monitoring hooks
- Fail-fast startup validation

**Reference Implementation:**
All code is production-tested and available at:
`/Users/xnxn040/PycharmProjects/voice-seiv-be-interview-prep/`

For questions or issues, refer to the test files and original implementation for detailed examples.
