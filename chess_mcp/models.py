"""Models shared by MCP server responses."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class ResponseModel(BaseModel):
    """Strict base model suitable for MCP structured output."""

    model_config = ConfigDict(extra="forbid")


class QueryMetadata(ResponseModel):
    source: str
    returned: int = Field(ge=0)
    truncated: bool = False
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PositionKey(ResponseModel):
    fen_norm: str
    turn: str
