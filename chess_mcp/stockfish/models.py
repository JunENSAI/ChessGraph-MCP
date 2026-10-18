"""Typed request-independent models returned by the Stockfish MCP tools."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from chess_mcp.models import ResponseModel


LimitType = Literal["depth", "nodes", "time"]


class SearchLimit(ResponseModel):
    """The bounded search budget supplied to Stockfish."""

    type: LimitType
    value: int = Field(ge=1)
    unit: Literal["plies", "nodes", "milliseconds"]


class EvaluationScore(ResponseModel):
    """An engine score from the root player's point of view."""

    type: Literal["cp", "mate"]
    value: int


class WDL(ResponseModel):
    """Stockfish win/draw/loss permille values from the root player's POV."""

    wins: int = Field(ge=0)
    draws: int = Field(ge=0)
    losses: int = Field(ge=0)


class PrincipalVariation(ResponseModel):
    """A principal variation represented in both UCI and SAN notation."""

    uci: list[str]
    san: list[str]


class EngineProvenance(ResponseModel):
    """Engine identity and statistics for one completed search."""

    name: str
    author: str | None = None
    threads: int | None = Field(default=None, ge=1)
    hash_mb: int | None = Field(default=None, ge=1)
    show_wdl: bool | None = None
    depth: int | None = Field(default=None, ge=0)
    seldepth: int | None = Field(default=None, ge=0)
    nodes: int | None = Field(default=None, ge=0)
    time_ms: int | None = Field(default=None, ge=0)


class AnalysisLine(ResponseModel):
    """One ranked engine candidate."""

    rank: int = Field(ge=1)
    move_uci: str | None = None
    move_san: str | None = None
    score: EvaluationScore
    wdl: WDL | None = None
    pv: PrincipalVariation
    engine: EngineProvenance


class PositionAnalysis(ResponseModel):
    """MultiPV analysis for a single root position."""

    fen: str
    root_player: Literal["white", "black"]
    limit: SearchLimit
    multipv: int = Field(ge=1)
    lines: list[AnalysisLine]


class MoveComparison(ResponseModel):
    """Best-move and restricted played-move searches from the same root."""

    fen: str
    root_player: Literal["white", "black"]
    played_move_uci: str
    played_move_san: str
    limit: SearchLimit
    best: AnalysisLine
    played: AnalysisLine
    centipawn_loss: int | None = Field(default=None, ge=0)


class ValidatedMove(ResponseModel):
    """One legal move in a validated line."""

    ply: int = Field(ge=1)
    uci: str
    san: str
    fen_after: str


class ValidatedLine(ResponseModel):
    """A legally replayed UCI line."""

    initial_fen: str
    moves: list[ValidatedMove]
    final_fen: str
