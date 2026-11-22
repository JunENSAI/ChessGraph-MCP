"""Models shared by MCP server responses."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ResponseModel(BaseModel):
    """Strict base model suitable for MCP structured output."""

    model_config = ConfigDict(extra="forbid")
