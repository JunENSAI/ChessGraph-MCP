"""Structured results returned by the Neo4j MCP tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GraphModel(BaseModel):
    """Base model for stable, forward-compatible graph responses."""

    model_config = ConfigDict(extra="ignore")


class Position(GraphModel):
    fen_norm: str
    turn_color: str | None = None
    piece_count: int | None = None
    material_sig: str | None = None
    last_moved_piece: str | None = None
    last_move_san: str | None = None
    eval_cp: int | None = None
    best_move_uci: str | None = None
    visit_count: int = 0


class Opening(GraphModel):
    epd_norm: str
    opening_id: int | None = None
    eco_volume: str | None = None
    eco_code: str | None = None
    opening_name: str | None = None
    pgn_line: str | None = None
    uci_line: str | None = None


class EndgamePattern(GraphModel):
    endgame_type: str
    piece_count: int | None = None
    benchmark_positions: int | None = None
    avg_player_elo: int | None = None
    sample_fen: str | None = None
    sample_human_move: str | None = None


class PositionContext(GraphModel):
    position: Position
    openings: list[Opening] = Field(default_factory=list)
    endgame_patterns: list[EndgamePattern] = Field(default_factory=list)


class PositionMove(GraphModel):
    relationship: Literal["PLAYED_MOVE", "THEORY_MOVE"]
    uci_move: str
    san_move: str | None = None
    moved_piece: str | None = None
    from_square: str | None = None
    to_square: str | None = None
    is_capture: bool | None = None
    target: Position
    eco_code: str | None = None
    total_games: int | None = None
    wins: int | None = None
    losses: int | None = None
    draws: int | None = None
    win_rate_pct: float | None = None
    avg_cp_loss: int | None = None
    avg_clock_sec: float | None = None
    best_move_uci: str | None = None


class PositionMoves(GraphModel):
    fen_norm: str
    moves: list[PositionMove] = Field(default_factory=list)


class TranspositionStep(GraphModel):
    relationship: Literal["PLAYED_MOVE", "THEORY_MOVE"]
    uci_move: str
    san_move: str | None = None


class TranspositionPath(GraphModel):
    source_fen: str
    target_fen: str
    depth: int
    moves: list[TranspositionStep] = Field(default_factory=list)


class TranspositionResult(GraphModel):
    fen_norm: str
    max_depth: int
    paths: list[TranspositionPath] = Field(default_factory=list)


class Game(GraphModel):
    game_id: int
    game_type: str | None = None
    played_date: str | None = None
    user_color: str | None = None
    user_elo: int | None = None
    opponent_elo: int | None = None
    user_outcome: str | None = None
    result: str | None = None
    eco_code: str | None = None
    opening_name: str | None = None
    total_plies: int | None = None


class Blunder(GraphModel):
    position: Position
    game: Game
    ply_number: int
    played_san: str | None = None
    played_uci: str | None = None
    moved_piece: str | None = None
    best_move_uci: str | None = None
    cp_loss: int | None = None
    clock_rem_sec: float | None = None


class GameBlunders(GraphModel):
    game_id: int
    blunders: list[Blunder] = Field(default_factory=list)


class RecurringBlunderPosition(GraphModel):
    position: Position
    occurrences: int
    games: int
    average_cp_loss: float | None = None
    max_cp_loss: int | None = None
    game_ids: list[int] = Field(default_factory=list)


class RecurringBlunders(GraphModel):
    min_occurrences: int
    positions: list[RecurringBlunderPosition] = Field(default_factory=list)


class EndgameBenchmark(GraphModel):
    position: Position
    benchmark_move_uci: str | None = None
    elo_tier: str | None = None
    player_elo: int | None = None


class EndgameContext(GraphModel):
    position: Position
    patterns: list[EndgamePattern] = Field(default_factory=list)
    benchmarks: list[EndgameBenchmark] = Field(default_factory=list)
