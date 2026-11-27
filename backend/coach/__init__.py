"""In-app coach: Claude (Claude Code login) over the ChessGraph repositories, with an offline mode."""

from __future__ import annotations

from chess_mcp.config import get_setting

from .prompt import CoachRequest
from .providers import DEFAULT_MODEL, ClaudeProvider, CoachProvider, OfflineProvider
from .tools import ToolContext

__all__ = [
    "CoachRequest",
    "CoachProvider",
    "ClaudeProvider",
    "OfflineProvider",
    "ToolContext",
    "provider_from_settings",
]

EFFORTS = {"low", "medium", "high", "xhigh", "max"}


def provider_from_settings() -> CoachProvider:
    """Pick the provider from .env.

    ``COACH_MODE`` is ``claude`` (default: Claude through the local Claude Code
    login, no API key) or ``offline`` (the evidence template, no model).
    """
    if get_setting("COACH_MODE", "claude").lower() == "offline":
        return OfflineProvider()
    effort = get_setting("CLAUDE_EFFORT", "low").lower()
    return ClaudeProvider(
        model=get_setting("CLAUDE_MODEL", DEFAULT_MODEL),
        effort=effort if effort in EFFORTS else "low",
    )
