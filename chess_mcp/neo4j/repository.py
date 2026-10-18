"""Read-only Neo4j repository for the curated chess graph queries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from neo4j import GraphDatabase, READ_ACCESS
from neo4j import Driver

from chess_mcp.chess import clamp_limit, normalize_fen
from chess_mcp.config import Neo4jSettings

from .models import (
    EndgameContext,
    GameBlunders,
    PositionContext,
    PositionMoves,
    RecurringBlunders,
    TranspositionResult,
)


MAX_RESULTS = 100
MAX_PATH_DEPTH = 4

POSITION_CONTEXT_CYPHER = """
MATCH (p:Position {fen_norm: $fen_norm})
OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(o:Opening)
OPTIONAL MATCH (p)-[:HAS_ENDGAME_TYPE]->(e:EndgamePattern)
RETURN p {
    .fen_norm, .turn_color, .piece_count, .material_sig,
    .last_moved_piece, .last_move_san, .eval_cp, .best_move_uci,
    visit_count: coalesce(p.visit_count, 0)
} AS position,
[item IN collect(DISTINCT o {
    .epd_norm, .opening_id, .eco_volume, .eco_code, .opening_name,
    .pgn_line, .uci_line
}) WHERE item IS NOT NULL] AS openings,
[item IN collect(DISTINCT e {
    .endgame_type, .piece_count, .benchmark_positions, .avg_player_elo,
    .sample_fen, .sample_human_move
}) WHERE item IS NOT NULL] AS endgame_patterns
"""

POSITION_MOVES_CYPHER = """
MATCH (:Position {fen_norm: $fen_norm})-[r:PLAYED_MOVE|THEORY_MOVE]->(target:Position)
RETURN type(r) AS relationship,
r {
    .uci_move, .san_move, .moved_piece, .from_square, .to_square,
    .is_capture, .eco_code, .total_games, .wins, .losses, .draws,
    .win_rate_pct, .avg_cp_loss, .avg_clock_sec, .best_move_uci
} AS move,
target {
    .fen_norm, .turn_color, .piece_count, .material_sig,
    .last_moved_piece, .last_move_san, .eval_cp, .best_move_uci,
    visit_count: coalesce(target.visit_count, 0)
} AS target
ORDER BY coalesce(r.total_games, 0) DESC, r.san_move, r.uci_move
LIMIT $limit
"""

GAME_BLUNDERS_CYPHER = """
MATCH (position:Position)-[b:BLUNDERED_IN]->(game:Game {game_id: $game_id})
RETURN position {
    .fen_norm, .turn_color, .piece_count, .material_sig,
    .last_moved_piece, .last_move_san, .eval_cp, .best_move_uci,
    visit_count: coalesce(position.visit_count, 0)
} AS position,
game {
    .game_id, .game_type, .played_date, .user_color, .user_elo,
    .opponent_elo, .user_outcome, .result, .eco_code, .opening_name,
    .total_plies
} AS game,
b {
    .ply_number, .played_san, .played_uci, .moved_piece,
    .best_move_uci, .cp_loss, .clock_rem_sec
} AS blunder
ORDER BY b.ply_number
LIMIT $limit
"""

RECURRING_BLUNDERS_CYPHER = """
MATCH (position:Position)-[b:BLUNDERED_IN]->(game:Game)
WITH position, count(b) AS occurrences, count(DISTINCT game) AS games,
     avg(b.cp_loss) AS average_cp_loss, max(b.cp_loss) AS max_cp_loss,
     collect(DISTINCT game.game_id)[0..$limit] AS game_ids
WHERE occurrences >= $min_occurrences
RETURN position {
    .fen_norm, .turn_color, .piece_count, .material_sig,
    .last_moved_piece, .last_move_san, .eval_cp, .best_move_uci,
    visit_count: coalesce(position.visit_count, 0)
} AS position,
occurrences, games, average_cp_loss, max_cp_loss, game_ids
ORDER BY occurrences DESC, average_cp_loss DESC
LIMIT $limit
"""

ENDGAME_CONTEXT_CYPHER = """
MATCH (position:Position {fen_norm: $fen_norm})
OPTIONAL MATCH (position)-[:HAS_ENDGAME_TYPE]->(pattern:EndgamePattern)
WITH position,
     [item IN collect(DISTINCT pattern {
         .endgame_type, .piece_count, .benchmark_positions, .avg_player_elo,
         .sample_fen, .sample_human_move
     }) WHERE item IS NOT NULL] AS patterns,
     [kind IN collect(DISTINCT pattern.endgame_type) WHERE kind IS NOT NULL]
         AS pattern_types
OPTIONAL MATCH (benchmark:Position)-[link:HAS_ENDGAME_TYPE]->(matched:EndgamePattern)
WHERE matched.endgame_type IN pattern_types
RETURN position {
    .fen_norm, .turn_color, .piece_count, .material_sig,
    .last_moved_piece, .last_move_san, .eval_cp, .best_move_uci,
    visit_count: coalesce(position.visit_count, 0)
} AS position,
patterns,
[item IN collect(DISTINCT CASE
    WHEN benchmark IS NULL THEN null
    ELSE {
        position: benchmark {
            .fen_norm, .turn_color, .piece_count, .material_sig,
            .last_moved_piece, .last_move_san, .eval_cp, .best_move_uci,
            visit_count: coalesce(benchmark.visit_count, 0)
        },
        benchmark_move_uci: link.benchmark_move_uci,
        elo_tier: link.elo_tier,
        player_elo: link.player_elo
    }
END) WHERE item IS NOT NULL][0..$limit] AS benchmarks
"""


def _record_data(record: Any) -> dict[str, Any]:
    if hasattr(record, "data"):
        return dict(record.data())
    if isinstance(record, Mapping):
        return dict(record)
    return dict(record)


class Neo4jRepository:
    """Execute only bounded, parameterized read transactions."""

    def __init__(self, driver: Driver, settings: Neo4jSettings) -> None:
        self._driver = driver
        self._database = settings.database
        self.max_results = min(settings.max_results, MAX_RESULTS)
        self.max_path_depth = min(settings.max_path_depth, MAX_PATH_DEPTH)

    @classmethod
    def from_settings(cls, settings: Neo4jSettings) -> Neo4jRepository:
        driver = GraphDatabase.driver(
            settings.uri,
            auth=(settings.user, settings.password),
        )
        return cls(driver, settings)

    def close(self) -> None:
        self._driver.close()

    def _read(self, query: str, parameters: Mapping[str, Any]) -> list[dict[str, Any]]:
        def run(tx: Any) -> list[dict[str, Any]]:
            return [_record_data(record) for record in tx.run(query, dict(parameters))]

        with self._driver.session(
            database=self._database,
            default_access_mode=READ_ACCESS,
        ) as session:
            return session.execute_read(run)

    def get_position_context(self, fen: str) -> PositionContext:
        fen_norm = normalize_fen(fen)
        rows = self._read(POSITION_CONTEXT_CYPHER, {"fen_norm": fen_norm})
        if not rows:
            raise LookupError(f"Position is not present in the graph: {fen_norm}")
        return PositionContext.model_validate(rows[0])

    def get_position_moves(self, fen: str, limit: int = 20) -> PositionMoves:
        fen_norm = normalize_fen(fen)
        bounded_limit = clamp_limit(limit, self.max_results)
        rows = self._read(
            POSITION_MOVES_CYPHER,
            {"fen_norm": fen_norm, "limit": bounded_limit},
        )
        moves = [
            {
                "relationship": row["relationship"],
                **row["move"],
                "target": row["target"],
            }
            for row in rows
        ]
        return PositionMoves(fen_norm=fen_norm, moves=moves)

    def find_transpositions(
        self,
        fen: str,
        max_depth: int = 3,
        limit: int = 20,
    ) -> TranspositionResult:
        fen_norm = normalize_fen(fen)
        if max_depth < 1:
            raise ValueError("max_depth must be at least 1")
        bounded_depth = min(max_depth, self.max_path_depth)
        bounded_limit = clamp_limit(limit, self.max_results)

        # Cypher does not allow a parameter for variable-length pattern bounds.
        # bounded_depth is validated and clamped to the integer whitelist 1..4.
        if bounded_depth not in range(1, MAX_PATH_DEPTH + 1):
            raise ValueError("max_depth must resolve to an integer from 1 through 4")
        query = f"""
MATCH path = (source:Position {{fen_norm: $fen_norm}})
             -[:PLAYED_MOVE|THEORY_MOVE*1..{bounded_depth}]->
             (target:Position)
WHERE source <> target
  AND COUNT {{ (target)<-[:PLAYED_MOVE|THEORY_MOVE]-(:Position) }} > 1
RETURN source.fen_norm AS source_fen,
       target.fen_norm AS target_fen,
       length(path) AS depth,
       [rel IN relationships(path) | {{
           relationship: type(rel),
           uci_move: rel.uci_move,
           san_move: rel.san_move
       }}] AS moves
ORDER BY depth, source_fen
LIMIT $limit
"""
        rows = self._read(
            query,
            {"fen_norm": fen_norm, "limit": bounded_limit},
        )
        return TranspositionResult(
            fen_norm=fen_norm,
            max_depth=bounded_depth,
            paths=rows,
        )

    def get_game_blunders(self, game_id: int, limit: int = 100) -> GameBlunders:
        bounded_limit = clamp_limit(limit, self.max_results)
        rows = self._read(
            GAME_BLUNDERS_CYPHER,
            {"game_id": game_id, "limit": bounded_limit},
        )
        blunders = [
            {
                "position": row["position"],
                "game": row["game"],
                **row["blunder"],
            }
            for row in rows
        ]
        return GameBlunders(game_id=game_id, blunders=blunders)

    def get_recurring_blunder_positions(
        self,
        min_occurrences: int = 2,
        limit: int = 20,
    ) -> RecurringBlunders:
        if min_occurrences < 2:
            raise ValueError("min_occurrences must be at least 2")
        bounded_limit = clamp_limit(limit, self.max_results)
        rows = self._read(
            RECURRING_BLUNDERS_CYPHER,
            {
                "min_occurrences": min_occurrences,
                "limit": bounded_limit,
            },
        )
        return RecurringBlunders(
            min_occurrences=min_occurrences,
            positions=rows,
        )

    def get_endgame_context(
        self,
        fen: str,
        limit: int = 20,
    ) -> EndgameContext:
        fen_norm = normalize_fen(fen)
        bounded_limit = clamp_limit(limit, self.max_results)
        rows = self._read(
            ENDGAME_CONTEXT_CYPHER,
            {"fen_norm": fen_norm, "limit": bounded_limit},
        )
        if not rows:
            raise LookupError(f"Position is not present in the graph: {fen_norm}")
        return EndgameContext.model_validate(rows[0])
