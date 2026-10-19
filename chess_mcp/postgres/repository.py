"""Read-only SQLAlchemy repository for the ChessGraph PostgreSQL schema."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.sql.elements import TextClause

from chess_mcp.chess import clamp_limit, normalize_fen
from chess_mcp.config import PostgresSettings

from .models import (
    Blunder,
    EndgamePosition,
    GameDetail,
    GameMove,
    GameSummary,
    GameType,
    OpeningTheory,
    PlayerSummary,
    PositionOccurrence,
    UserOutcome,
)
from .recap import BAND_SQL, RecapPayload, build_recap


_SET_TIMEOUT = text(
    "SELECT set_config('statement_timeout', :statement_timeout_ms, true)"
)

_GAME_SUMMARY_COLUMNS = """
    g.game_id,
    g.game_hash,
    g.game_type::text AS game_type,
    g.played_date,
    g.white_username,
    g.black_username,
    g.white_elo,
    g.black_elo,
    g.result::text AS result,
    g.time_control_raw,
    g.eco_code,
    g.opening_name,
    g.total_plies
"""


class PostgresRepository:
    """Execute only the fixed SELECT statements exposed by the MCP server."""

    def __init__(
        self,
        engine: Engine,
        *,
        statement_timeout_ms: int,
        max_results: int,
    ) -> None:
        if statement_timeout_ms < 1:
            raise ValueError("statement_timeout_ms must be positive")
        if max_results < 1:
            raise ValueError("max_results must be positive")
        self._engine = engine
        self._statement_timeout_ms = statement_timeout_ms
        self.max_results = min(max_results, 100)

    @classmethod
    def from_settings(cls, settings: PostgresSettings) -> PostgresRepository:
        engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
        )
        return cls(
            engine,
            statement_timeout_ms=settings.statement_timeout_ms,
            max_results=settings.max_results,
        )

    def close(self) -> None:
        self._engine.dispose()

    def _limit(self, requested: int) -> int:
        return clamp_limit(requested, self.max_results)

    def _fetch_all(
        self,
        statement: TextClause,
        parameters: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        # psycopg2 maps this SQLAlchemy execution option to the driver's
        # transaction-level readonly flag before BEGIN.
        with self._engine.connect().execution_options(
            postgresql_readonly=True
        ) as connection:
            with connection.begin():
                connection.execute(
                    _SET_TIMEOUT,
                    {"statement_timeout_ms": str(self._statement_timeout_ms)},
                )
                result = connection.execute(statement, dict(parameters))
                return [dict(row) for row in result.mappings().all()]

    def list_games(
        self,
        *,
        player: str | None = None,
        game_type: GameType | None = None,
        user_outcome: UserOutcome | None = None,
        eco_code: str | None = None,
        played_from: date | None = None,
        played_to: date | None = None,
        limit: int = 20,
    ) -> list[GameSummary]:
        rows = self._fetch_all(
            text(
                f"""
                SELECT {_GAME_SUMMARY_COLUMNS}
                FROM games AS g
                WHERE (
                    :player IS NULL
                    OR lower(g.white_username) = lower(:player)
                    OR lower(g.black_username) = lower(:player)
                )
                AND (
                    :game_type IS NULL
                    OR g.game_type = CAST(:game_type AS game_category)
                )
                AND (:user_outcome IS NULL OR g.user_outcome = :user_outcome)
                AND (:eco_code IS NULL OR g.eco_code = :eco_code)
                AND (:played_from IS NULL OR g.played_date >= :played_from)
                AND (:played_to IS NULL OR g.played_date <= :played_to)
                ORDER BY g.played_date DESC, g.game_id DESC
                LIMIT :limit
                """
            ),
            {
                "player": player,
                "game_type": game_type,
                "user_outcome": user_outcome,
                "eco_code": eco_code,
                "played_from": played_from,
                "played_to": played_to,
                "limit": self._limit(limit),
            },
        )
        return [GameSummary.model_validate(row) for row in rows]

    def get_game(self, game_id: int) -> GameDetail | None:
        rows = self._fetch_all(
            text(
                """
                SELECT
                    g.game_id,
                    g.game_hash,
                    g.game_type::text AS game_type,
                    g.played_date,
                    g.white_username,
                    g.black_username,
                    g.white_elo,
                    g.black_elo,
                    g.result::text AS result,
                    g.time_control_raw,
                    g.eco_code,
                    g.opening_name,
                    g.total_plies,
                    g.event,
                    g.site,
                    g.end_time_utc,
                    g.round,
                    g.user_color,
                    g.user_elo,
                    g.opponent_elo,
                    g.user_outcome,
                    g.base_time_sec,
                    g.increment_sec,
                    g.termination,
                    g.pgn_moves_raw,
                    g.created_at
                FROM games AS g
                WHERE g.game_id = :game_id
                LIMIT 1
                """
            ),
            {"game_id": game_id},
        )
        return GameDetail.model_validate(rows[0]) if rows else None

    def get_game_moves(
        self,
        game_id: int,
        *,
        start_ply: int = 1,
        limit: int = 100,
    ) -> list[GameMove]:
        if start_ply < 1:
            raise ValueError("start_ply must be positive")
        rows = self._fetch_all(
            text(
                """
                SELECT
                    m.move_id,
                    m.game_id,
                    m.ply_number,
                    m.move_number,
                    m.turn_color,
                    m.san_move,
                    m.uci_move,
                    m.fen_before_norm,
                    m.fen_after_norm,
                    m.clock_rem_sec,
                    m.eval_cp_before,
                    m.eval_cp_after,
                    m.cp_loss,
                    m.best_move_uci
                FROM game_moves AS m
                WHERE m.game_id = :game_id
                  AND m.ply_number >= :start_ply
                ORDER BY m.ply_number
                LIMIT :limit
                """
            ),
            {
                "game_id": game_id,
                "start_ply": start_ply,
                "limit": self._limit(limit),
            },
        )
        return [GameMove.model_validate(row) for row in rows]

    def get_player_summary(
        self,
        username: str,
        *,
        game_type: GameType | None = None,
    ) -> PlayerSummary:
        rows = self._fetch_all(
            text(
                """
                WITH player_games AS (
                    SELECT
                        g.played_date,
                        g.white_elo AS player_rating,
                        g.black_elo AS opponent_rating,
                        CASE
                            WHEN g.result = '1-0' THEN 'win'
                            WHEN g.result = '0-1' THEN 'loss'
                            WHEN g.result = '1/2-1/2' THEN 'draw'
                            ELSE 'unfinished'
                        END AS outcome
                    FROM games AS g
                    WHERE lower(g.white_username) = lower(:username)
                      AND (
                          :game_type IS NULL
                          OR g.game_type = CAST(:game_type AS game_category)
                      )
                    UNION ALL
                    SELECT
                        g.played_date,
                        g.black_elo AS player_rating,
                        g.white_elo AS opponent_rating,
                        CASE
                            WHEN g.result = '0-1' THEN 'win'
                            WHEN g.result = '1-0' THEN 'loss'
                            WHEN g.result = '1/2-1/2' THEN 'draw'
                            ELSE 'unfinished'
                        END AS outcome
                    FROM games AS g
                    WHERE lower(g.black_username) = lower(:username)
                      AND (
                          :game_type IS NULL
                          OR g.game_type = CAST(:game_type AS game_category)
                      )
                )
                SELECT
                    :username AS username,
                    count(*) AS games_played,
                    count(*) FILTER (WHERE outcome = 'win') AS wins,
                    count(*) FILTER (WHERE outcome = 'loss') AS losses,
                    count(*) FILTER (WHERE outcome = 'draw') AS draws,
                    count(*) FILTER (WHERE outcome = 'unfinished') AS unfinished,
                    avg(player_rating) AS average_rating,
                    avg(opponent_rating) AS average_opponent_rating,
                    min(played_date) AS earliest_game,
                    max(played_date) AS latest_game
                FROM player_games
                """
            ),
            {"username": username, "game_type": game_type},
        )
        return PlayerSummary.model_validate(rows[0])

    def get_blunders(
        self,
        *,
        player: str | None = None,
        game_id: int | None = None,
        minimum_cp_loss: int = 100,
        limit: int = 20,
    ) -> list[Blunder]:
        if minimum_cp_loss < 0:
            raise ValueError("minimum_cp_loss must not be negative")
        rows = self._fetch_all(
            text(
                """
                SELECT
                    g.game_id,
                    g.played_date,
                    g.game_type::text AS game_type,
                    g.white_username,
                    g.black_username,
                    m.ply_number,
                    m.move_number,
                    m.turn_color,
                    m.san_move,
                    m.uci_move,
                    m.fen_before_norm,
                    m.fen_after_norm,
                    m.eval_cp_before,
                    m.eval_cp_after,
                    m.cp_loss,
                    m.best_move_uci
                FROM game_moves AS m
                JOIN games AS g ON g.game_id = m.game_id
                WHERE m.cp_loss >= :minimum_cp_loss
                  AND (:game_id IS NULL OR g.game_id = :game_id)
                  AND (
                      (
                          :player IS NULL
                          AND (
                              (g.user_color = 'white' AND m.turn_color = 'w')
                              OR (g.user_color = 'black' AND m.turn_color = 'b')
                          )
                      )
                      OR (
                          m.turn_color = 'w'
                          AND lower(g.white_username) = lower(:player)
                      )
                      OR (
                          m.turn_color = 'b'
                          AND lower(g.black_username) = lower(:player)
                      )
                  )
                ORDER BY m.cp_loss DESC, g.played_date DESC, m.ply_number
                LIMIT :limit
                """
            ),
            {
                "player": player,
                "game_id": game_id,
                "minimum_cp_loss": minimum_cp_loss,
                "limit": self._limit(limit),
            },
        )
        return [Blunder.model_validate(row) for row in rows]

    def find_position_occurrences(
        self,
        fen: str,
        *,
        limit: int = 20,
    ) -> tuple[str, list[PositionOccurrence]]:
        normalized_fen = normalize_fen(fen)
        rows = self._fetch_all(
            text(
                """
                SELECT
                    g.game_id,
                    g.played_date,
                    g.game_type::text AS game_type,
                    g.white_username,
                    g.black_username,
                    g.result::text AS result,
                    m.ply_number,
                    m.san_move,
                    CASE
                        WHEN m.fen_before_norm = :fen THEN 'before'
                        ELSE 'after'
                    END AS matched_position
                FROM game_moves AS m
                JOIN games AS g ON g.game_id = m.game_id
                WHERE m.fen_before_norm = :fen OR m.fen_after_norm = :fen
                ORDER BY g.played_date DESC, g.game_id DESC, m.ply_number
                LIMIT :limit
                """
            ),
            {"fen": normalized_fen, "limit": self._limit(limit)},
        )
        return normalized_fen, [
            PositionOccurrence.model_validate(row) for row in rows
        ]

    def lookup_opening(
        self,
        fen: str,
        *,
        limit: int = 20,
    ) -> tuple[str, list[OpeningTheory]]:
        normalized_fen = normalize_fen(fen)
        rows = self._fetch_all(
            text(
                """
                SELECT
                    o.opening_id,
                    o.eco_volume,
                    o.eco_code,
                    o.opening_name,
                    o.pgn_line,
                    o.uci_line,
                    o.epd_norm
                FROM opening_theory AS o
                WHERE o.epd_norm = :fen
                ORDER BY o.eco_code, o.opening_name, o.opening_id
                LIMIT :limit
                """
            ),
            {"fen": normalized_fen, "limit": self._limit(limit)},
        )
        return normalized_fen, [OpeningTheory.model_validate(row) for row in rows]

    def lookup_endgame_positions(
        self,
        *,
        fen: str | None = None,
        endgame_type: str | None = None,
        piece_count: int | None = None,
        elo_tier: str | None = None,
        limit: int = 20,
    ) -> tuple[str | None, list[EndgamePosition]]:
        if piece_count is not None and piece_count < 2:
            raise ValueError("piece_count must be at least 2")
        normalized_fen = normalize_fen(fen) if fen is not None else None
        rows = self._fetch_all(
            text(
                """
                SELECT
                    e.endgame_id,
                    e.fen_full,
                    e.fen_norm,
                    e.human_move_uci,
                    e.endgame_type,
                    e.piece_count,
                    e.time_control,
                    e.player_elo,
                    e.opp_elo,
                    e.elo_tier
                FROM endgame_theory AS e
                WHERE (:fen IS NULL OR e.fen_norm = :fen)
                  AND (:endgame_type IS NULL OR e.endgame_type = :endgame_type)
                  AND (:piece_count IS NULL OR e.piece_count = :piece_count)
                  AND (:elo_tier IS NULL OR e.elo_tier = :elo_tier)
                ORDER BY e.piece_count, e.endgame_type, e.endgame_id
                LIMIT :limit
                """
            ),
            {
                "fen": normalized_fen,
                "endgame_type": endgame_type,
                "piece_count": piece_count,
                "elo_tier": elo_tier,
                "limit": self._limit(limit),
            },
        )
        return normalized_fen, [EndgamePosition.model_validate(row) for row in rows]

    def get_rating_recap(self) -> RecapPayload:
        """Count stored games by rating band, color, opening line, and clock."""
        opening_rows = [
            (
                row["band"],
                row["user_color"],
                row["opening_name"],
                row["eco_code"],
                row["user_outcome"],
                row["amount"],
            )
            for row in self._fetch_all(
                text(
                    f"""
                    SELECT
                        {BAND_SQL} AS band,
                        user_color,
                        COALESCE(NULLIF(opening_name, ''), 'Unclassified') AS opening_name,
                        COALESCE(NULLIF(eco_code, ''), '—') AS eco_code,
                        user_outcome,
                        count(*) AS amount
                    FROM games
                    WHERE user_color IN ('white', 'black')
                      AND user_outcome IN ('win', 'loss', 'draw')
                    GROUP BY 1, 2, 3, 4, 5
                    """
                ),
                {},
            )
        ]
        time_rows = [
            (row["band"], row["game_type"], row["user_outcome"], row["amount"])
            for row in self._fetch_all(
                text(
                    f"""
                    SELECT
                        {BAND_SQL} AS band,
                        game_type::text AS game_type,
                        user_outcome,
                        count(*) AS amount
                    FROM games
                    WHERE user_color IN ('white', 'black')
                      AND user_outcome IN ('win', 'loss', 'draw')
                    GROUP BY 1, 2, 3
                    """
                ),
                {},
            )
        ]
        return build_recap(opening_rows, time_rows)
