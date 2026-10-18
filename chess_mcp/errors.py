"""Error conversion helpers that avoid leaking connection secrets."""

from __future__ import annotations

import logging

from mcp.server.mcpserver.exceptions import ToolError


def tool_failure(
    logger: logging.Logger,
    message: str,
    exc: Exception,
) -> ToolError:
    """Log the detailed exception to stderr and return a safe MCP tool error."""
    logger.exception("%s: %s", message, type(exc).__name__)
    return ToolError(message)
