"""MCP Token Manager - JWT Token Generation with Background Refresh.

Implements enterprise background refresh pattern used by Envoy, Istio, Kong, and Google Auth Library.

Key Features:
- Thread-safe token generation using threading.Lock
- Background refresh task using asyncio.create_task()
- 24-hour token expiration with 3-hour refresh buffer
- Zero overhead on token access (instant return)

Reference: code_examples/MCP_CLIENT_IMPLEMENTATION_GUIDE.md
"""
import asyncio
import threading
from datetime import datetime, timedelta, timezone

import jwt
import structlog

logger = structlog.get_logger(__name__)


class MCPTokenManager:
    """Manages JWT tokens for MCP authentication with automatic background refresh.

    Tokens are generated with 24-hour expiration and automatically refreshed
    when they reach 3 hours before expiration (at 21 hours).

    Background task checks every 60 seconds.
    """

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        """Initialize token manager and generate first token.

        Args:
            secret_key: JWT signing key (from MCP_SECRET_KEY env var)
            algorithm: JWT algorithm (default: HS256)
        """
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._lock = threading.Lock()
        self._current_token = self._generate_token()
        self._token_expiration = datetime.now(timezone.utc) + timedelta(hours=24)
        self._refresh_task: asyncio.Task | None = None

        logger.info(
            "mcp_token_manager_initialized",
            algorithm=algorithm,
            token_expiration=self._token_expiration.isoformat(),
        )

    def get_valid_token(self) -> str:
        """Get current valid token.

        This is instant (no blocking or async waits).
        Background task ensures token is always fresh.

        Returns:
            Current JWT token string
        """
        return self._current_token

    def _is_expiring_soon(self, buffer_hours: int = 3) -> bool:
        """Check if token will expire within buffer_hours.

        Args:
            buffer_hours: Hours before expiration to trigger refresh (default: 3)

        Returns:
            True if token expires within buffer_hours
        """
        time_until_expiry = self._token_expiration - datetime.now(timezone.utc)
        return time_until_expiry.total_seconds() < (buffer_hours * 3600)

    def _generate_token(self) -> str:
        """Generate new JWT token with thread safety.

        Returns:
            Encoded JWT token string
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            expiration = now + timedelta(hours=24)

            payload = {
                "sub": "mcp-client",
                "iat": now,
                "exp": expiration,
            }

            token = jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

            logger.debug(
                "mcp_token_generated",
                issued_at=now.isoformat(),
                expires_at=expiration.isoformat(),
            )

            return token

    def _refresh_token(self) -> None:
        """Refresh the current token (thread-safe)."""
        with self._lock:
            self._current_token = self._generate_token()
            self._token_expiration = datetime.now(timezone.utc) + timedelta(hours=24)

            logger.info(
                "mcp_token_refreshed",
                new_expiration=self._token_expiration.isoformat(),
            )

    async def start_refresh_loop(self) -> None:
        """Start background task that checks and refreshes token periodically.

        Checks every 60 seconds. Refreshes when token is within 3 hours of expiration.
        Runs until cancelled.
        """
        logger.info("mcp_token_refresh_loop_started")

        try:
            while True:
                await asyncio.sleep(60)  # Check every 60 seconds

                if self._is_expiring_soon():
                    self._refresh_token()
                    logger.info("mcp_token_automatically_refreshed")

        except asyncio.CancelledError:
            logger.info("mcp_token_refresh_loop_cancelled")
            raise

    def start_background_refresh(self) -> asyncio.Task:
        """Start background refresh task.

        Returns:
            asyncio.Task that can be awaited or cancelled
        """
        self._refresh_task = asyncio.create_task(self.start_refresh_loop())
        return self._refresh_task

    async def stop_background_refresh(self) -> None:
        """Stop background refresh task gracefully."""
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass

        logger.info("mcp_token_manager_stopped")
