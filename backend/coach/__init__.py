"""In-app coach: Claude tool loop over the ChessGraph repositories, with an offline mode."""

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

    ``COACH_MODE`` is ``auto`` (default), ``claude`` or ``offline``. In ``auto``,
    the Claude coach is used only when ``ANTHROPIC_API_KEY`` is set.
    """
    mode = get_setting("COACH_MODE", "auto").lower()
    key = get_setting("ANTHROPIC_API_KEY")
    if mode == "offline" or (mode == "auto" and not key):
        return OfflineProvider()

    import anthropic

    effort = get_setting("CLAUDE_EFFORT", "low").lower()
    return ClaudeProvider(
        anthropic.Anthropic(api_key=key or None),
        model=get_setting("CLAUDE_MODEL", DEFAULT_MODEL),
        effort=effort if effort in EFFORTS else "low",
        refusal_fallback=get_setting("CLAUDE_REFUSAL_FALLBACK", "default").lower() != "off",
    )
