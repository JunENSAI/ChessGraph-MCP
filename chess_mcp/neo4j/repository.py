"""Read-only Neo4j repository for the curated chess graph queries (schema v2)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from neo4j import READ_ACCESS, Driver, GraphDatabase

from chess_mcp.chess import SEVERITY_MIN_CP, clamp_limit, normalize_fen
from chess_mcp.config import MAX_PATH_DEPTH, Neo4jSettings

from .models import (
    EndgameContext,
    GameBlunders,
    GamesThroughPosition,
    PositionContext,
    PositionMoves,
    RecurringBlunders,
    StyleContext,
    TheoryExits,
    TranspositionResult,
)

MAX_RESULTS = 100
MOVE_FILTERS = ("all", "theory", "owner", "opponent")
EXIT_FILTERS = ("all", "owner", "opponent")


def _position(var: str) -> str:
    """Map projection of a Position node."""
    return (
        f"{var} {{ .fen_norm, .turn_color, .piece_count, .material_sig, .phase, .is_theory, "
        f".eval_cp, .eval_samples, .best_move_uci, .best_move_san, "
        f"visit_games: coalesce({var}.visit_games, 0) }}"
    )


def _game(var: str) -> str:
    """Map projection of a Game node. Neo4j dates become ISO strings."""
    return (
        f"{var} {{ .game_id, .game_type, played_date: toString({var}.played_date), .user_color, "
        f".user_elo, .opponent_elo, .rating_band, .user_outcome, .result, .termination, "
        f".time_control, .eco_code, .opening_name, .total_plies }}"
    )


OPENING_FIELDS = ".epd_norm, .opening_id, .eco_volume, .eco_code, .opening_name, .family, .pgn_line, .uci_line"
PATTERN_FIELDS = ".endgame_type, .piece_count, .benchmark_positions, .avg_player_elo, .sample_fen, .sample_human_move"
MOVE_FIELDS = (
    ".uci_move, .san_move, .by, .moved_piece, .from_square, .to_square, .promotion, .is_capture, "
    ".is_check, .eco_codes, .games, .times, .wins, .draws, .losses, .score_pct, .avg_cp_loss, "
    ".avg_eval_after, .inaccuracies, .mistakes, .blunders, .is_engine_best"
)

POSITION_CONTEXT_CYPHER = f"""
MATCH (p:Position {{fen_norm: $fen_norm}})
OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(o:Opening)
WITH p, collect(DISTINCT o {{{OPENING_FIELDS}}}) AS openings
OPTIONAL MATCH (p)-[:IN_OPENING]->(line:Opening)
WITH p, openings, collect(DISTINCT line.family)[0..10] AS families, count(DISTINCT line) AS theory_lines
OPTIONAL MATCH (p)-[:HAS_ENDGAME_TYPE]->(e:EndgamePattern)
WITH p, openings, families, theory_lines, collect(DISTINCT e {{{PATTERN_FIELDS}}}) AS patterns
OPTIONAL MATCH (p)-[best:ENGINE_BEST]->(next:Position)
RETURN {_position("p")} AS position,
       openings,
       families AS opening_families,
       theory_lines,
       patterns AS endgame_patterns,
       CASE WHEN best IS NULL THEN null
            ELSE {{uci: best.uci, san: best.san, target: {_position("next")}}} END AS engine_best
"""

POSITION_MOVES_CYPHER = f"""
MATCH (p:Position {{fen_norm: $fen_norm}})
OPTIONAL MATCH (p)-[best:ENGINE_BEST]->(next:Position)
CALL (p) {{
  OPTIONAL MATCH (p)-[r:PLAYED_MOVE|THEORY_MOVE]->(target:Position)
  WHERE $by = 'all'
     OR ($by = 'theory' AND type(r) = 'THEORY_MOVE')
     OR (type(r) = 'PLAYED_MOVE' AND r.by = $by)
  WITH r, target
  // Most-played first; book moves (no games) follow, the ones more ECO lines use first.
  // Use $by to select one kind.
  ORDER BY coalesce(r.games, 0) DESC, CASE type(r) WHEN 'THEORY_MOVE' THEN 0 ELSE 1 END,
           size(coalesce(r.eco_codes, [])) DESC, r.san_move, r.uci_move
  LIMIT $limit
  RETURN [item IN collect(CASE WHEN r IS NULL THEN null ELSE {{
      relationship: type(r),
      move: r {{{MOVE_FIELDS}}},
      target: {_position("target")}
  }} END) WHERE item IS NOT NULL] AS moves
}}
RETURN {_position("p")} AS position,
       CASE WHEN best IS NULL THEN null
            ELSE {{uci: best.uci, san: best.san, target: {_position("next")}}} END AS engine_best,
       moves
"""

GAME_BLUNDERS_CYPHER = f"""
MATCH (position:Position)-[m:MISTAKE_IN]->(game:Game {{game_id: $game_id}})
WHERE m.cp_loss >= $min_cp
RETURN {_position("position")} AS position,
       {_game("game")} AS game,
       m {{ .ply, .severity, .cp_loss, .mate_swing, .played_uci, .played_san, .best_uci }} AS mistake
ORDER BY m.ply
LIMIT $limit
"""

RECURRING_BLUNDERS_CYPHER = f"""
MATCH (position:Position)-[m:MISTAKE_IN]->(game:Game)
WHERE m.cp_loss >= $min_cp
WITH position,
     count(m) AS occurrences,
     count(DISTINCT game) AS games,
     avg(m.cp_loss) AS average_cp_loss,
     max(m.cp_loss) AS max_cp_loss,
     collect(DISTINCT m.played_san)[0..5] AS played_moves,
     collect(DISTINCT game.game_id)[0..10] AS game_ids
WHERE games >= $min_occurrences
RETURN {_position("position")} AS position,
       occurrences, games, average_cp_loss, max_cp_loss, played_moves, game_ids
ORDER BY games DESC, average_cp_loss DESC
LIMIT $limit
"""

ENDGAME_CONTEXT_CYPHER = f"""
MATCH (position:Position {{fen_norm: $fen_norm}})
OPTIONAL MATCH (position)-[:HAS_ENDGAME_TYPE]->(pattern:EndgamePattern)
WITH position,
     collect(DISTINCT pattern {{{PATTERN_FIELDS}}}) AS patterns,
     collect(DISTINCT pattern.endgame_type) AS pattern_types
OPTIONAL MATCH (benchmark:Position)-[link:HAS_ENDGAME_TYPE {{benchmark: true}}]->(matched:EndgamePattern)
WHERE matched.endgame_type IN pattern_types
RETURN {_position("position")} AS position,
       patterns,
       [item IN collect(DISTINCT CASE WHEN benchmark IS NULL THEN null ELSE {{
            position: {_position("benchmark")},
            benchmark_move_uci: link.benchmark_move_uci,
            elo_tier: link.elo_tier,
            player_elo: link.player_elo
       }} END) WHERE item IS NOT NULL][0..$limit] AS benchmarks
"""

GAMES_THROUGH_POSITION_CYPHER = f"""
MATCH (:Position {{fen_norm: $fen_norm}})<-[r:REACHED]-(game:Game)
// A game can reach one position twice (repetition): keep its first visit.
WITH game, min(r.ply) AS ply, head(collect(r.owner_to_move)) AS owner_to_move
ORDER BY game.played_date DESC, game.game_id DESC
WITH collect({{game: {_game("game")}, ply: ply, owner_to_move: owner_to_move}}) AS visits
RETURN size(visits) AS total_games,
       size([v IN visits WHERE v.game.user_outcome = 'win']) AS owner_wins,
       size([v IN visits WHERE v.game.user_outcome = 'draw']) AS owner_draws,
       size([v IN visits WHERE v.game.user_outcome = 'loss']) AS owner_losses,
       visits[0..$limit] AS games
"""

THEORY_EXITS_CYPHER = f"""
MATCH (game:Game)-[r:LEFT_THEORY_AT]->(p:Position)
WHERE $by = 'all' OR r.by = $by
WITH p, r.by AS by, r.played_uci AS played_uci, r.played_san AS played_san,
     min(r.ply) AS ply, collect(game.user_outcome) AS outcomes
WITH p, by, played_uci, played_san, ply, outcomes, size(outcomes) AS games
ORDER BY games DESC, ply, played_uci
LIMIT $limit
OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(exact:Opening)
OPTIONAL MATCH (p)-[:IN_OPENING]->(line:Opening)
OPTIONAL MATCH (p)-[book:THEORY_MOVE]->(:Position)
WITH p, by, played_uci, played_san, ply, outcomes, games,
     head(collect(DISTINCT exact.opening_name)) AS opening,
     collect(DISTINCT line.family)[0..3] AS families,
     collect(DISTINCT book.san_move) AS theory_moves
RETURN {_position("p")} AS position,
       by, played_uci, played_san, ply, games,
       size([o IN outcomes WHERE o = 'win']) AS owner_wins,
       size([o IN outcomes WHERE o = 'draw']) AS owner_draws,
       size([o IN outcomes WHERE o = 'loss']) AS owner_losses,
       opening, families AS opening_families, theory_moves,
       size(theory_moves) = 0 AS book_ended
ORDER BY games DESC, ply, played_uci
"""


def _moves_subquery(alias: str, where: str, order: str) -> str:
    """Moves leaving ``p`` that match ``where``, as PositionMove maps, first ``$limit`` by ``order``."""
    return f"""
CALL (p) {{
  OPTIONAL MATCH (p)-[r:PLAYED_MOVE|THEORY_MOVE]->(target:Position)
  WHERE {where}
  WITH r, target ORDER BY {order} LIMIT $limit
  RETURN [item IN collect(CASE WHEN r IS NULL THEN null ELSE {{
      relationship: type(r), move: r {{{MOVE_FIELDS}}}, target: {_position("target")}
  }} END) WHERE item IS NOT NULL] AS {alias}
}}"""


def style_context_cypher(depth: int) -> str:
    """One read for the owner's record around a position.

    ``depth`` is spliced into the variable-length pattern (Cypher takes no
    parameter there), so it must already be a validated integer 1..4.
    """
    if depth not in range(1, MAX_PATH_DEPTH + 1):
        raise ValueError("depth must be an integer from 1 through 4")
    return f"""
MATCH (p:Position {{fen_norm: $fen_norm}})
OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(exact:Opening)
OPTIONAL MATCH (p)-[:IN_OPENING]->(line:Opening)
WITH p, head(collect(DISTINCT exact.opening_name)) AS opening, collect(DISTINCT line.family)[0..3] AS opening_families
{_moves_subquery("owner_moves", "type(r) = 'PLAYED_MOVE' AND r.by = 'owner'", "r.games DESC, r.uci_move")}
{_moves_subquery("opponent_moves", "type(r) = 'PLAYED_MOVE' AND r.by = 'opponent'", "r.games DESC, r.uci_move")}
{_moves_subquery("theory_moves", "type(r) = 'THEORY_MOVE'", "size(coalesce(r.eco_codes, [])) DESC, r.uci_move")}
CALL (p) {{
  OPTIONAL MATCH (p)<-[reach:REACHED]-(game:Game)
  // A game can reach one position twice (repetition): keep its first visit.
  WITH game, min(reach.ply) AS ply, head(collect(reach.owner_to_move)) AS owner_to_move
  ORDER BY game.played_date DESC, game.game_id DESC
  WITH [visit IN collect(CASE WHEN game IS NULL THEN null ELSE
          {{game: {_game("game")}, ply: ply, owner_to_move: owner_to_move}} END)
        WHERE visit IS NOT NULL] AS visits
  RETURN size(visits) AS total_games,
         size([v IN visits WHERE v.game.user_outcome = 'win']) AS owner_wins,
         size([v IN visits WHERE v.game.user_outcome = 'draw']) AS owner_draws,
         size([v IN visits WHERE v.game.user_outcome = 'loss']) AS owner_losses,
         visits[0..$limit] AS recent_games
}}
CALL (p) {{
  OPTIONAL MATCH path = (p)-[:PLAYED_MOVE*0..{depth}]->(near:Position)
  WITH near, min(length(path)) AS distance
  MATCH (near)-[m:MISTAKE_IN]->(game:Game)
  WITH near, distance,
       count(DISTINCT game) AS games,
       avg(m.cp_loss) AS average_cp_loss,
       max(m.cp_loss) AS max_cp_loss,
       collect(DISTINCT m.played_san)[0..3] AS played_moves,
       collect(DISTINCT m.best_uci)[0..3] AS best_moves
  ORDER BY games DESC, distance, average_cp_loss DESC
  LIMIT $limit
  RETURN collect({{position: {_position("near")}, distance: distance, games: games,
                  average_cp_loss: average_cp_loss, max_cp_loss: max_cp_loss,
                  played_moves: played_moves, best_moves: best_moves}}) AS nearby_mistakes
}}
RETURN {_position("p")} AS position, opening, opening_families,
       owner_moves, opponent_moves, theory_moves,
       total_games, owner_wins, owner_draws, owner_losses, recent_games, nearby_mistakes
"""


def _record_data(record: Any) -> dict[str, Any]:
    if hasattr(record, "data"):
        return dict(record.data())
    return dict(record)


def _min_cp(min_severity: str) -> int:
    if min_severity not in SEVERITY_MIN_CP:
        raise ValueError(f"min_severity must be one of {', '.join(SEVERITY_MIN_CP)}")
    return SEVERITY_MIN_CP[min_severity]


class Neo4jRepository:
    """Execute only bounded, parameterized read transactions."""

    def __init__(self, driver: Driver, settings: Neo4jSettings) -> None:
        self._driver = driver
        self._database = settings.database
        self.max_results = min(settings.max_results, MAX_RESULTS)
        self.max_path_depth = min(settings.max_path_depth, MAX_PATH_DEPTH)

    @classmethod
    def from_settings(cls, settings: Neo4jSettings) -> Neo4jRepository:
        driver = GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password))
        return cls(driver, settings)

    def close(self) -> None:
        self._driver.close()

    def _read(self, query: str, parameters: Mapping[str, Any]) -> list[dict[str, Any]]:
        def run(tx: Any) -> list[dict[str, Any]]:
            return [_record_data(record) for record in tx.run(query, dict(parameters))]

        with self._driver.session(database=self._database, default_access_mode=READ_ACCESS) as session:
            return session.execute_read(run)

    def get_position_context(self, fen: str) -> PositionContext:
        fen_norm = normalize_fen(fen)
        rows = self._read(POSITION_CONTEXT_CYPHER, {"fen_norm": fen_norm})
        if not rows:
            raise LookupError(f"Position is not present in the graph: {fen_norm}")
        return PositionContext.model_validate(rows[0])

    def get_position_moves(self, fen: str, limit: int = 20, by: str = "all") -> PositionMoves:
        fen_norm = normalize_fen(fen)
        if by not in MOVE_FILTERS:
            raise ValueError(f"by must be one of {', '.join(MOVE_FILTERS)}")
        bounded_limit = clamp_limit(limit, self.max_results)
        rows = self._read(POSITION_MOVES_CYPHER, {"fen_norm": fen_norm, "limit": bounded_limit, "by": by})
        if not rows:
            return PositionMoves(fen_norm=fen_norm, by=by)  # type: ignore[arg-type]
        row = rows[0]
        moves = [{"relationship": item["relationship"], **item["move"], "target": item["target"]} for item in row["moves"]]
        return PositionMoves.model_validate(
            {"fen_norm": fen_norm, "by": by, "position": row["position"], "engine_best": row["engine_best"], "moves": moves}
        )

    def find_transpositions(self, fen: str, max_depth: int = 3, limit: int = 20) -> TranspositionResult:
        fen_norm = normalize_fen(fen)
        if max_depth < 1:
            raise ValueError("max_depth must be at least 1")
        bounded_depth = min(max_depth, self.max_path_depth)
        bounded_limit = clamp_limit(limit, self.max_results)

        # Cypher does not allow a parameter for variable-length pattern bounds.
        # bounded_depth is validated and clamped to the integer whitelist 1..4.
        if bounded_depth not in range(1, MAX_PATH_DEPTH + 1):
            raise ValueError("max_depth must resolve to an integer from 1 through 4")
        # PLAYED_MOVE has one edge per mover (owner, opponent), so the same move
        # sequence can appear as several paths: keep one per sequence. A target
        # is convergent when at least two distinct positions lead to it.
        query = f"""
MATCH path = (source:Position {{fen_norm: $fen_norm}})
             -[:PLAYED_MOVE|THEORY_MOVE*1..{bounded_depth}]->
             (target:Position)
WHERE source <> target
  AND COUNT {{ MATCH (prev:Position)-[:PLAYED_MOVE|THEORY_MOVE]->(target) RETURN DISTINCT prev }} > 1
WITH source, target, [rel IN relationships(path) | rel.uci_move] AS sequence, collect(path)[0] AS path
RETURN source.fen_norm AS source_fen,
       target.fen_norm AS target_fen,
       length(path) AS depth,
       [rel IN relationships(path) | {{
           relationship: type(rel),
           uci_move: rel.uci_move,
           san_move: rel.san_move
       }}] AS moves
ORDER BY depth, target_fen
LIMIT $limit
"""
        rows = self._read(query, {"fen_norm": fen_norm, "limit": bounded_limit})
        return TranspositionResult(fen_norm=fen_norm, max_depth=bounded_depth, paths=rows)  # type: ignore[arg-type]

    def get_game_blunders(self, game_id: int, limit: int = 100, min_severity: str = "mistake") -> GameBlunders:
        if game_id < 1:
            raise ValueError("game_id must be a positive integer")
        min_cp = _min_cp(min_severity)
        bounded_limit = clamp_limit(limit, self.max_results)
        rows = self._read(GAME_BLUNDERS_CYPHER, {"game_id": game_id, "limit": bounded_limit, "min_cp": min_cp})
        return GameBlunders.model_validate(
            {
                "game_id": game_id,
                "min_severity": min_severity,
                "game": rows[0]["game"] if rows else None,
                "blunders": [{"position": row["position"], **row["mistake"]} for row in rows],
            }
        )

    def get_recurring_blunder_positions(
        self,
        min_occurrences: int = 2,
        limit: int = 20,
        min_severity: str = "mistake",
    ) -> RecurringBlunders:
        if min_occurrences < 2:
            raise ValueError("min_occurrences must be at least 2")
        min_cp = _min_cp(min_severity)
        bounded_limit = clamp_limit(limit, self.max_results)
        rows = self._read(
            RECURRING_BLUNDERS_CYPHER,
            {"min_occurrences": min_occurrences, "limit": bounded_limit, "min_cp": min_cp},
        )
        return RecurringBlunders.model_validate(
            {"min_occurrences": min_occurrences, "min_severity": min_severity, "positions": rows}
        )

    def get_endgame_context(self, fen: str, limit: int = 20) -> EndgameContext:
        fen_norm = normalize_fen(fen)
        bounded_limit = clamp_limit(limit, self.max_results)
        rows = self._read(ENDGAME_CONTEXT_CYPHER, {"fen_norm": fen_norm, "limit": bounded_limit})
        if not rows:
            raise LookupError(f"Position is not present in the graph: {fen_norm}")
        return EndgameContext.model_validate(rows[0])

    def get_games_through_position(self, fen: str, limit: int = 20) -> GamesThroughPosition:
        fen_norm = normalize_fen(fen)
        bounded_limit = clamp_limit(limit, self.max_results)
        rows = self._read(GAMES_THROUGH_POSITION_CYPHER, {"fen_norm": fen_norm, "limit": bounded_limit})
        return GamesThroughPosition.model_validate({"fen_norm": fen_norm, **(rows[0] if rows else {})})

    def get_theory_exits(self, limit: int = 20, by: str = "owner") -> TheoryExits:
        if by not in EXIT_FILTERS:
            raise ValueError(f"by must be one of {', '.join(EXIT_FILTERS)}")
        bounded_limit = clamp_limit(limit, self.max_results)
        rows = self._read(THEORY_EXITS_CYPHER, {"limit": bounded_limit, "by": by})
        return TheoryExits.model_validate({"by": by, "exits": rows})

    def get_style_context(self, fen: str, depth: int = 2, limit: int = 5) -> StyleContext:
        """The owner's record around a position: moves by mover and book, results, nearby mistakes.

        A position missing from the graph gives an empty context, not an error.
        """
        fen_norm = normalize_fen(fen)
        if depth < 1:
            raise ValueError("depth must be at least 1")
        bounded_depth = min(depth, self.max_path_depth)
        bounded_limit = clamp_limit(limit, self.max_results)
        rows = self._read(style_context_cypher(bounded_depth), {"fen_norm": fen_norm, "limit": bounded_limit})
        base = {"fen_norm": fen_norm, "depth": bounded_depth}
        if not rows:
            return StyleContext.model_validate(base)
        row = rows[0]
        flat = {
            key: [{"relationship": item["relationship"], **item["move"], "target": item["target"]} for item in row[key]]
            for key in ("owner_moves", "opponent_moves", "theory_moves")
        }
        return StyleContext.model_validate({**base, **row, **flat})
