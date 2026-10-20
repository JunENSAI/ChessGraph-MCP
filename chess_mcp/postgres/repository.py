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
    CoachingBrief,
    EndgameLesson,
    EndgamePosition,
    GameDetail,
    GameMove,
    GameSummary,
    GameType,
    OpeningLesson,
    OpeningTheory,
    PlayerSummary,
    PositionOccurrence,
    UserOutcome,
)
from .recap import (
    BAND_SQL,
    MIN_CALCULATION_LOSS,
    MIN_CALCULATION_TIMES,
    MIN_SPLIT_TIMES,
    OPENING_PLY,
    RecapPayload,
    build_coaching_brief,
    build_recap,
)


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
        offset: int = 0,
    ) -> list[GameSummary]:
        if offset < 0:
            raise ValueError("offset must not be negative")
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
                OFFSET :offset
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
                "offset": offset,
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

    def list_opening_lessons(
        self,
        *,
        player: str,
        color: str,
        limit: int = 5,
    ) -> list[OpeningLesson]:
        """Top opening names for one color, with one stored theory line when it exists."""
        if color not in ("white", "black"):
            raise ValueError("color must be white or black")
        rows = self._fetch_all(
            text(
                """
                WITH played AS (
                    SELECT
                        btrim(opening_name) AS opening_name,
                        count(*) AS games,
                        mode() WITHIN GROUP (ORDER BY eco_code) AS eco_code
                    FROM games
                    WHERE user_color = :color
                      AND (
                          lower(white_username) = lower(:player)
                          OR lower(black_username) = lower(:player)
                      )
                      AND opening_name IS NOT NULL
                      AND btrim(opening_name) <> ''
                    GROUP BY btrim(opening_name)
                    ORDER BY count(*) DESC, btrim(opening_name)
                    LIMIT :limit
                )
                SELECT
                    p.opening_name,
                    p.games,
                    p.eco_code,
                    theory.uci_line,
                    theory.pgn_line
                FROM played AS p
                LEFT JOIN LATERAL (
                    SELECT o.uci_line, o.pgn_line
                    FROM opening_theory AS o
                    WHERE o.opening_name = p.opening_name
                    ORDER BY
                        CASE
                            WHEN p.eco_code IS NOT NULL AND o.eco_code = p.eco_code THEN 0
                            ELSE 1
                        END,
                        o.opening_id
                    LIMIT 1
                ) AS theory ON true
                ORDER BY p.games DESC, p.opening_name
                """
            ),
            {"player": player, "color": color, "limit": self._limit(limit)},
        )
        return [OpeningLesson.model_validate(row) for row in rows]

    def list_endgame_lessons(
        self,
        *,
        average_rating: float | None,
        limit: int = 5,
    ) -> tuple[str | None, list[EndgameLesson]]:
        """Technique positions from the elo tier nearest ``average_rating``.

        With no rating, the tier that holds the most positions is used.
        Each type contributes one position, the one with the fewest pieces.
        """
        rows = self._fetch_all(
            text(
                """
                WITH tier_stats AS (
                    SELECT
                        elo_tier,
                        count(*) AS positions,
                        avg(player_elo) AS average_elo
                    FROM endgame_theory
                    WHERE elo_tier IS NOT NULL AND btrim(elo_tier) <> ''
                    GROUP BY elo_tier
                ),
                chosen AS (
                    SELECT elo_tier
                    FROM tier_stats
                    ORDER BY
                        CASE
                            WHEN CAST(:rating AS double precision) IS NULL THEN -positions
                            ELSE abs(average_elo - CAST(:rating AS double precision))
                        END,
                        positions DESC,
                        elo_tier
                    LIMIT 1
                ),
                ranked_types AS (
                    SELECT e.endgame_type, count(*) AS positions
                    FROM endgame_theory AS e
                    JOIN chosen AS c ON e.elo_tier = c.elo_tier
                    GROUP BY e.endgame_type
                    ORDER BY count(*) DESC, e.endgame_type
                    LIMIT :limit
                )
                SELECT DISTINCT ON (e.endgame_type)
                    e.endgame_type,
                    e.fen_full,
                    e.human_move_uci,
                    e.elo_tier,
                    e.piece_count,
                    r.positions
                FROM endgame_theory AS e
                JOIN chosen AS c ON e.elo_tier = c.elo_tier
                JOIN ranked_types AS r ON r.endgame_type = e.endgame_type
                ORDER BY e.endgame_type, e.piece_count, e.endgame_id
                """
            ),
            {"rating": average_rating, "limit": self._limit(limit)},
        )
        rows.sort(key=lambda row: (-int(row["positions"]), row["endgame_type"]))
        lessons = [
            EndgameLesson.model_validate(
                {key: value for key, value in row.items() if key != "positions"}
            )
            for row in rows
        ]
        tier = lessons[0].elo_tier if lessons else None
        return tier, lessons

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
        clock_rows = [
            (
                row["band"],
                row["game_type"],
                _round_elo(row["average_opponent_elo"]),
                _round_elo(row["average_elo_when_win"]),
                _round_elo(row["average_elo_when_loss"]),
            )
            for row in self._fetch_all(
                text(
                    f"""
                    SELECT
                        {BAND_SQL} AS band,
                        game_type::text AS game_type,
                        avg(opponent_elo) AS average_opponent_elo,
                        avg(user_elo) FILTER (WHERE user_outcome = 'win') AS average_elo_when_win,
                        avg(user_elo) FILTER (WHERE user_outcome = 'loss') AS average_elo_when_loss
                    FROM games
                    WHERE user_color IN ('white', 'black')
                      AND user_outcome IN ('win', 'loss', 'draw')
                    GROUP BY 1, 2
                    """
                ),
                {},
            )
        ]
        return build_recap(opening_rows, time_rows, clock_rows)

    def get_coaching_brief(self, player: str) -> CoachingBrief:
        """Strengths, the weakest opening split, and repeated later mistakes."""
        if not player.strip():
            raise ValueError("player is required")
        owner = """
            (
                lower(g.white_username) = lower(:player)
                OR lower(g.black_username) = lower(:player)
            )
            AND (
                (g.user_color = 'white' AND m.turn_color = 'w')
                OR (g.user_color = 'black' AND m.turn_color = 'b')
            )
        """
        family_rows = [
            (row["opening_name"], row["user_color"], row["user_outcome"], int(row["amount"]))
            for row in self._fetch_all(
                text(
                    """
                    SELECT
                        btrim(opening_name) AS opening_name,
                        user_color,
                        user_outcome,
                        count(*) AS amount
                    FROM games
                    WHERE (
                        lower(white_username) = lower(:player)
                        OR lower(black_username) = lower(:player)
                    )
                      AND user_color IN ('white', 'black')
                      AND user_outcome IN ('win', 'loss', 'draw')
                      AND opening_name IS NOT NULL
                      AND btrim(opening_name) <> ''
                    GROUP BY btrim(opening_name), user_color, user_outcome
                    """
                ),
                {"player": player},
            )
        ]
        split_rows = [
            (
                row["opening_name"],
                row["fen_before_norm"],
                int(row["ply_number"]),
                row["san_move"],
                row["uci_move"],
                row["best_move_uci"],
                int(row["times"]),
                row["average_cp_loss"],
            )
            for row in self._fetch_all(
                text(
                    f"""
                    SELECT
                        btrim(g.opening_name) AS opening_name,
                        m.fen_before_norm,
                        min(m.ply_number) AS ply_number,
                        m.san_move,
                        m.uci_move,
                        m.best_move_uci,
                        count(*) AS times,
                        avg(m.cp_loss) AS average_cp_loss
                    FROM game_moves AS m
                    JOIN games AS g ON g.game_id = m.game_id
                    WHERE {owner}
                      AND g.opening_name IS NOT NULL
                      AND btrim(g.opening_name) <> ''
                      AND m.ply_number <= :opening_ply
                      AND m.best_move_uci IS NOT NULL
                      AND m.uci_move <> m.best_move_uci
                    GROUP BY btrim(g.opening_name), m.fen_before_norm, m.san_move, m.uci_move, m.best_move_uci
                    HAVING count(*) >= :min_times
                    """
                ),
                {"player": player, "opening_ply": OPENING_PLY, "min_times": MIN_SPLIT_TIMES},
            )
        ]
        calculation_rows = [
            (
                row["fen_before_norm"],
                int(row["ply_number"]),
                row["san_move"],
                row["uci_move"],
                row["best_move_uci"],
                int(row["times"]),
                row["average_cp_loss"],
            )
            for row in self._fetch_all(
                text(
                    f"""
                    SELECT
                        m.fen_before_norm,
                        min(m.ply_number) AS ply_number,
                        m.san_move,
                        m.uci_move,
                        m.best_move_uci,
                        count(*) AS times,
                        avg(m.cp_loss) AS average_cp_loss
                    FROM game_moves AS m
                    JOIN games AS g ON g.game_id = m.game_id
                    WHERE {owner}
                      AND m.ply_number > :opening_ply
                      AND m.cp_loss >= :min_cp_loss
                      AND m.best_move_uci IS NOT NULL
                      AND m.uci_move <> m.best_move_uci
                    GROUP BY m.fen_before_norm, m.san_move, m.uci_move, m.best_move_uci
                    HAVING count(*) >= :min_times
                    """
                ),
                {
                    "player": player,
                    "opening_ply": OPENING_PLY,
                    "min_cp_loss": MIN_CALCULATION_LOSS,
                    "min_times": MIN_CALCULATION_TIMES,
                },
            )
        ]
        puzzle_fens = [
            str(row["fen_before_norm"])
            for row in self._fetch_all(
                text(
                    f"""
                    SELECT m.fen_before_norm
                    FROM game_moves AS m
                    JOIN games AS g ON g.game_id = m.game_id
                    WHERE {owner}
                      AND m.cp_loss IS NOT NULL
                    GROUP BY m.fen_before_norm
                    ORDER BY max(m.cp_loss) DESC
                    LIMIT 4
                    """
                ),
                {"player": player},
            )
        ]
        theory_rows = [
            (row["opening_name"], row["uci_line"], row["pgn_line"])
            for row in self._fetch_all(
                text(
                    """
                    SELECT DISTINCT ON (btrim(opening_name))
                        btrim(opening_name) AS opening_name,
                        uci_line,
                        pgn_line
                    FROM opening_theory
                    WHERE btrim(opening_name) ILIKE :french
                       OR btrim(opening_name) ILIKE :sicilian
                       OR btrim(opening_name) ILIKE :caro
                    ORDER BY btrim(opening_name), opening_id
                    """
                ),
                {
                    "french": "French Defense%",
                    "sicilian": "Sicilian Defense%",
                    "caro": "Caro-Kann Defense%",
                },
            )
        ]
        theory_rows.extend(
            (row["opening_name"], row["uci_line"], row["pgn_line"])
            for row in self._fetch_all(
                text(
                    """
                    SELECT DISTINCT ON (btrim(opening_name))
                        btrim(opening_name) AS opening_name,
                        uci_line,
                        pgn_line
                    FROM opening_theory
                    WHERE btrim(opening_name) NOT ILIKE '%Defense%'
                      AND btrim(opening_name) NOT ILIKE '%Defence%'
                    ORDER BY btrim(opening_name), opening_id
                    LIMIT 80
                    """
                ),
                {},
            )
        )
        rating_rows = self._fetch_all(
            text(
                """
                SELECT avg(user_elo) AS average_rating
                FROM games
                WHERE (
                    lower(white_username) = lower(:player)
                    OR lower(black_username) = lower(:player)
                )
                  AND user_elo IS NOT NULL
                """
            ),
            {"player": player},
        )
        average = rating_rows[0]["average_rating"] if rating_rows else None
        _tier, endgame_lessons = self.list_endgame_lessons(
            average_rating=float(average) if average is not None else None,
            limit=40,
        )
        endgame_rows = [
            (lesson.endgame_type, lesson.fen_full, lesson.human_move_uci, lesson.elo_tier)
            for lesson in endgame_lessons
        ]
        return build_coaching_brief(
            family_rows,
            split_rows,
            calculation_rows,
            theory_rows,
            endgame_rows,
            puzzle_fens,
        )


def _round_elo(value: Any) -> int | None:
    if value is None:
        return None
    return int(round(float(value)))
