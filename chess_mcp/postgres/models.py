"""Typed results returned by the PostgreSQL MCP tools."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


GameType = Literal["rapid", "blitz", "bullet", "daily", "bot"]
GameResult = Literal["1-0", "0-1", "1/2-1/2", "*"]
UserOutcome = Literal["win", "loss", "draw", "other"]


class PostgresModel(BaseModel):
    """Base model for immutable, strictly named database results."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class GameSummary(PostgresModel):
    game_id: int
    game_hash: str
    game_type: GameType
    played_date: date
    white_username: str
    black_username: str
    white_elo: int | None = None
    black_elo: int | None = None
    result: GameResult
    time_control_raw: str
    eco_code: str | None = None
    opening_name: str | None = None
    total_plies: int | None = None


class GameDetail(GameSummary):
    event: str | None = None
    site: str | None = None
    end_time_utc: time | None = None
    round: str | None = None
    user_color: Literal["white", "black"] | None = None
    user_elo: int | None = None
    opponent_elo: int | None = None
    user_outcome: UserOutcome | None = None
    base_time_sec: int | None = None
    increment_sec: int | None = None
    termination: str | None = None
    pgn_moves_raw: str
    created_at: datetime | None = None


class GameMove(PostgresModel):
    move_id: int
    game_id: int
    ply_number: int
    move_number: int
    turn_color: Literal["w", "b"]
    san_move: str
    uci_move: str
    fen_before_norm: str
    fen_after_norm: str
    clock_rem_sec: float | None = None
    eval_cp_before: int | None = None
    eval_cp_after: int | None = None
    cp_loss: int | None = None
    best_move_uci: str | None = None


class PlayerSummary(PostgresModel):
    username: str
    games_played: int
    wins: int
    losses: int
    draws: int
    unfinished: int
    average_rating: float | None = None
    average_opponent_rating: float | None = None
    earliest_game: date | None = None
    latest_game: date | None = None


class Blunder(PostgresModel):
    game_id: int
    played_date: date
    game_type: GameType
    white_username: str
    black_username: str
    ply_number: int
    move_number: int
    turn_color: Literal["w", "b"]
    san_move: str
    uci_move: str
    fen_before_norm: str
    fen_after_norm: str
    eval_cp_before: int | None = None
    eval_cp_after: int | None = None
    cp_loss: int
    best_move_uci: str | None = None


class PositionOccurrence(PostgresModel):
    game_id: int
    played_date: date
    game_type: GameType
    white_username: str
    black_username: str
    result: GameResult
    ply_number: int
    san_move: str
    matched_position: Literal["before", "after"]


class OpeningTheory(PostgresModel):
    opening_id: int
    eco_volume: str | None = None
    eco_code: str
    opening_name: str
    pgn_line: str
    uci_line: str | None = None
    epd_norm: str


class EndgamePosition(PostgresModel):
    endgame_id: int
    fen_full: str
    fen_norm: str
    human_move_uci: str
    endgame_type: str
    piece_count: int
    time_control: str | None = None
    player_elo: int | None = None
    opp_elo: int | None = None
    elo_tier: str | None = None


class OpeningLesson(PostgresModel):
    """One opening the player has used, with a theory line when one is stored."""

    opening_name: str
    eco_code: str | None = None
    games: int = Field(ge=0)
    uci_line: str | None = None
    pgn_line: str | None = None


class EndgameLesson(PostgresModel):
    """One technique position chosen for the player's rating tier."""

    endgame_type: str
    fen_full: str
    human_move_uci: str
    elo_tier: str | None = None
    piece_count: int = Field(ge=0)


class GamesResult(PostgresModel):
    games: list[GameSummary] = Field(default_factory=list)


class GameResultDetail(PostgresModel):
    game: GameDetail | None = None


class GameMovesResult(PostgresModel):
    game_id: int
    start_ply: int = Field(ge=1)
    moves: list[GameMove] = Field(default_factory=list)


class BlundersResult(PostgresModel):
    blunders: list[Blunder] = Field(default_factory=list)


class PositionOccurrencesResult(PostgresModel):
    normalized_fen: str
    occurrences: list[PositionOccurrence] = Field(default_factory=list)


class OpeningsResult(PostgresModel):
    normalized_fen: str
    openings: list[OpeningTheory] = Field(default_factory=list)


class EndgamePositionsResult(PostgresModel):
    normalized_fen: str | None = None
    positions: list[EndgamePosition] = Field(default_factory=list)


class CoachingLine(PostgresModel):
    """One opening family with finished-game results."""

    family: str
    games: int = Field(ge=0)
    wins: int = Field(ge=0)
    draws: int = Field(ge=0)
    losses: int = Field(ge=0)


class CoachingSplit(PostgresModel):
    """A move the player repeats, beside the stored engine move."""

    fen: str
    ply: int = Field(ge=1)
    played_san: str
    played_uci: str
    best_uci: str
    best_san: str
    times: int = Field(ge=1)
    average_cp_loss: int = Field(ge=0)
    mate: bool = False


class CoachingTarget(PostgresModel):
    """The opening family with the worst score, and where the player leaves the stored move."""

    family: str
    games: int = Field(ge=0)
    wins: int = Field(ge=0)
    draws: int = Field(ge=0)
    losses: int = Field(ge=0)
    splits: list[CoachingSplit] = Field(default_factory=list)


class TrainingTask(PostgresModel):
    """One drill: a stored line, or puzzle candidates still waiting for a mate search."""

    kind: Literal["opening", "defense", "endgame", "puzzle"]
    title: str
    reason: str
    start_fen: str
    uci_line: str = ""
    pgn_line: str = ""
    user_color: Literal["white", "black"]
    ready: bool = False
    puzzle_fens: list[str] = Field(default_factory=list)


class CoachingBrief(PostgresModel):
    """Strengths, one target opening, repeated mistakes, and four training tasks."""

    strengths: list[CoachingLine] = Field(default_factory=list)
    target: CoachingTarget | None = None
    calculation: list[CoachingSplit] = Field(default_factory=list)
    endgames: str
    tasks: list[TrainingTask] = Field(default_factory=list)
