"""Structured results returned by the Neo4j MCP tools (graph schema v2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Severity = Literal["inaccuracy", "mistake", "blunder"]
Mover = Literal["owner", "opponent"]
MoveFilter = Literal["all", "theory", "owner", "opponent"]


class GraphModel(BaseModel):
    """Base model for stable, forward-compatible graph responses."""

    model_config = ConfigDict(extra="ignore")


class Position(GraphModel):
    fen_norm: str
    turn_color: str | None = None
    piece_count: int | None = None
    material_sig: str | None = None
    phase: Literal["opening", "middlegame", "endgame"] | None = None
    is_theory: bool | None = None
    visit_games: int = 0
    eval_cp: int | None = Field(default=None, description="Average stored eval, side-to-move point of view.")
    eval_samples: int | None = None
    best_move_uci: str | None = None
    best_move_san: str | None = None


class Opening(GraphModel):
    epd_norm: str
    opening_id: int | None = None
    eco_volume: str | None = None
    eco_code: str | None = None
    opening_name: str | None = None
    family: str | None = None
    pgn_line: str | None = None
    uci_line: str | None = None


class EndgamePattern(GraphModel):
    endgame_type: str
    piece_count: int | None = None
    benchmark_positions: int | None = None
    avg_player_elo: int | None = None
    sample_fen: str | None = None
    sample_human_move: str | None = None


class EngineBest(GraphModel):
    uci: str
    san: str | None = None
    target: Position | None = None


class PositionContext(GraphModel):
    position: Position
    openings: list[Opening] = Field(default_factory=list)
    opening_families: list[str] = Field(default_factory=list)
    theory_lines: int = 0
    endgame_patterns: list[EndgamePattern] = Field(default_factory=list)
    engine_best: EngineBest | None = None


class PositionMove(GraphModel):
    relationship: Literal["PLAYED_MOVE", "THEORY_MOVE"]
    uci_move: str
    san_move: str | None = None
    by: Mover | None = Field(default=None, description="Who played it; null on theory moves.")
    moved_piece: str | None = None
    from_square: str | None = None
    to_square: str | None = None
    promotion: str | None = None
    is_capture: bool | None = None
    is_check: bool | None = None
    eco_codes: list[str] = Field(default_factory=list)
    games: int | None = None
    times: int | None = None
    wins: int | None = Field(default=None, description="Games the mover won after this move.")
    draws: int | None = None
    losses: int | None = None
    score_pct: float | None = Field(default=None, description="Mover's score, (wins + draws / 2) / games.")
    avg_cp_loss: int | None = None
    avg_eval_after: int | None = Field(default=None, description="Mover's point of view.")
    inaccuracies: int | None = None
    mistakes: int | None = None
    blunders: int | None = None
    is_engine_best: bool | None = None
    target: Position

    @field_validator("eco_codes", mode="before")
    @classmethod
    def _no_codes_is_empty(cls, value: object) -> object:
        # Only THEORY_MOVE edges carry eco_codes; Cypher projects it as null on PLAYED_MOVE.
        return [] if value is None else value


class PositionMoves(GraphModel):
    fen_norm: str
    by: MoveFilter = "all"
    position: Position | None = None
    engine_best: EngineBest | None = None
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
    rating_band: str | None = None
    user_outcome: str | None = None
    result: str | None = None
    termination: str | None = None
    time_control: str | None = None
    eco_code: str | None = None
    opening_name: str | None = None
    total_plies: int | None = None


class Blunder(GraphModel):
    """One of the owner's moves with a centipawn loss of at least 50."""

    position: Position
    ply: int
    severity: Severity
    cp_loss: int
    mate_swing: bool = False
    played_uci: str | None = None
    played_san: str | None = None
    best_uci: str | None = None


class GameBlunders(GraphModel):
    game_id: int
    min_severity: Severity
    game: Game | None = None
    blunders: list[Blunder] = Field(default_factory=list)


class RecurringBlunderPosition(GraphModel):
    position: Position
    occurrences: int
    games: int
    average_cp_loss: float | None = None
    max_cp_loss: int | None = None
    played_moves: list[str] = Field(default_factory=list)
    game_ids: list[int] = Field(default_factory=list)


class RecurringBlunders(GraphModel):
    min_occurrences: int
    min_severity: Severity
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


class GameVisit(GraphModel):
    game: Game
    ply: int
    owner_to_move: bool | None = None


class GamesThroughPosition(GraphModel):
    fen_norm: str
    total_games: int = 0
    owner_wins: int = 0
    owner_draws: int = 0
    owner_losses: int = 0
    games: list[GameVisit] = Field(default_factory=list)


class TheoryExit(GraphModel):
    position: Position
    by: Mover
    played_uci: str
    played_san: str | None = None
    ply: int | None = None
    games: int
    owner_wins: int = 0
    owner_draws: int = 0
    owner_losses: int = 0
    opening: str | None = Field(default=None, description="Exact opening name of the exit position, if it has one.")
    opening_families: list[str] = Field(default_factory=list)
    theory_moves: list[str] = Field(default_factory=list, description="Book moves (SAN) from the exit position.")
    book_ended: bool = Field(
        default=False,
        description="True when the opening data has no move from this position: the line ended rather than being left.",
    )


class TheoryExits(GraphModel):
    by: Literal["all", "owner", "opponent"]
    exits: list[TheoryExit] = Field(default_factory=list)
