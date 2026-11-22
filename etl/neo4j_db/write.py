"""Write a ``GraphPayload`` (see ``transform.py``) into Neo4j.

The Neo4j database is shared with other projects, so every statement here
names a chess label. ``reset_chess_graph`` deletes only ``CHESS_LABELS``;
``label_counts`` lets the loader prove the other labels did not change.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from neo4j import Driver, ManagedTransaction

from etl.neo4j_db.transform import GraphPayload

logger = logging.getLogger(__name__)

CHESS_LABELS = ("Position", "Game", "Opening", "OpeningFamily", "EndgamePattern", "Player", "ChessGraphMeta")
DEFAULT_BATCH = 5_000

SCHEMA = (
    "CREATE CONSTRAINT position_fen_unique IF NOT EXISTS FOR (p:Position) REQUIRE p.fen_norm IS UNIQUE",
    "CREATE CONSTRAINT opening_epd_unique IF NOT EXISTS FOR (o:Opening) REQUIRE o.epd_norm IS UNIQUE",
    "CREATE CONSTRAINT endgame_type_unique IF NOT EXISTS FOR (e:EndgamePattern) REQUIRE e.endgame_type IS UNIQUE",
    "CREATE CONSTRAINT game_id_unique IF NOT EXISTS FOR (g:Game) REQUIRE g.game_id IS UNIQUE",
    "CREATE CONSTRAINT player_username_unique IF NOT EXISTS FOR (p:Player) REQUIRE p.username IS UNIQUE",
    "CREATE CONSTRAINT opening_family_unique IF NOT EXISTS FOR (f:OpeningFamily) REQUIRE f.name IS UNIQUE",
    "CREATE INDEX position_piece_count_idx IF NOT EXISTS FOR (p:Position) ON (p.piece_count)",
    "CREATE INDEX position_material_idx IF NOT EXISTS FOR (p:Position) ON (p.material_sig)",
    "CREATE INDEX position_phase_idx IF NOT EXISTS FOR (p:Position) ON (p.phase)",
    "CREATE INDEX opening_eco_idx IF NOT EXISTS FOR (o:Opening) ON (o.eco_code)",
    "CREATE INDEX game_type_idx IF NOT EXISTS FOR (g:Game) ON (g.game_type)",
    "CREATE INDEX game_played_date_idx IF NOT EXISTS FOR (g:Game) ON (g.played_date)",
    "CREATE INDEX played_move_by_idx IF NOT EXISTS FOR ()-[r:PLAYED_MOVE]-() ON (r.by)",
)

POSITIONS = """
UNWIND $rows AS row
MERGE (p:Position {fen_norm: row.fen_norm})
SET p += row
"""

OPENINGS = """
UNWIND $rows AS row
MERGE (o:Opening {epd_norm: row.epd_norm})
SET o += row {.opening_id, .eco_volume, .eco_code, .opening_name, .family, .pgn_line, .uci_line}
FOREACH (_ IN CASE WHEN row.family IS NULL THEN [] ELSE [1] END |
  MERGE (f:OpeningFamily {name: row.family})
  MERGE (o)-[:IN_FAMILY]->(f)
)
WITH o, row
MATCH (p:Position {fen_norm: row.epd_norm})
MERGE (p)-[:CLASSIFIED_AS]->(o)
"""

THEORY_MOVES = """
UNWIND $rows AS row
MATCH (a:Position {fen_norm: row.fen_before})
MATCH (b:Position {fen_norm: row.fen_after})
MERGE (a)-[r:THEORY_MOVE {uci_move: row.uci_move}]->(b)
SET r += row {.san_move, .moved_piece, .from_square, .to_square, .promotion, .is_capture, .is_check, .eco_codes}
"""

IN_OPENING = """
UNWIND $rows AS row
MATCH (p:Position {fen_norm: row.fen_norm})
MATCH (o:Opening {epd_norm: row.epd_norm})
MERGE (p)-[r:IN_OPENING]->(o)
SET r.ply = row.ply
"""

ENDGAME_PATTERNS = """
UNWIND $rows AS row
MERGE (e:EndgamePattern {endgame_type: row.endgame_type})
SET e += row
"""

ENDGAME_BENCHMARKS = """
UNWIND $rows AS row
MATCH (p:Position {fen_norm: row.fen_norm})
MATCH (e:EndgamePattern {endgame_type: row.endgame_type})
MERGE (p)-[r:HAS_ENDGAME_TYPE]->(e)
SET r.benchmark = true,
    r.benchmark_move_uci = row.benchmark_move_uci,
    r.elo_tier = row.elo_tier,
    r.player_elo = row.player_elo
"""

ENDGAME_LINKS = """
UNWIND $rows AS row
MATCH (p:Position {fen_norm: row.fen_norm})
MATCH (e:EndgamePattern {endgame_type: row.endgame_type})
MERGE (p)-[r:HAS_ENDGAME_TYPE]->(e)
SET r.from_games = true
"""

PLAYERS = """
UNWIND $rows AS row
MERGE (p:Player {username: row.username})
SET p.is_owner = row.is_owner
"""

GAMES = """
UNWIND $rows AS row
MERGE (g:Game {game_id: row.game_id})
SET g += row
"""

PLAYED_AS = """
UNWIND $rows AS row
MATCH (p:Player {username: row.username})
MATCH (g:Game {game_id: row.game_id})
MERGE (p)-[r:PLAYED_AS {color: row.color}]->(g)
SET r.elo = row.elo
"""

PLAYED_MOVES = """
UNWIND $rows AS row
MATCH (a:Position {fen_norm: row.fen_before})
MATCH (b:Position {fen_norm: row.fen_after})
MERGE (a)-[r:PLAYED_MOVE {uci_move: row.uci_move, by: row.by}]->(b)
SET r += row {
  .san_move, .moved_piece, .from_square, .to_square, .promotion, .is_capture, .is_check,
  .games, .times, .wins, .draws, .losses, .score_pct, .avg_cp_loss, .avg_eval_after,
  .inaccuracies, .mistakes, .blunders, .is_engine_best
}
"""

REACHED = """
UNWIND $rows AS row
MATCH (g:Game {game_id: row.game_id})
MATCH (p:Position {fen_norm: row.fen_norm})
MERGE (g)-[r:REACHED {ply: row.ply}]->(p)
SET r.owner_to_move = row.owner_to_move
"""

OPENED_WITH = """
UNWIND $rows AS row
MATCH (g:Game {game_id: row.game_id})
MATCH (o:Opening {epd_norm: row.epd_norm})
MERGE (g)-[r:OPENED_WITH]->(o)
SET r.ply = row.ply
"""

LEFT_THEORY = """
UNWIND $rows AS row
MATCH (g:Game {game_id: row.game_id})
MATCH (p:Position {fen_norm: row.fen_norm})
MERGE (g)-[r:LEFT_THEORY_AT]->(p)
SET r += row {.ply, .played_uci, .played_san, .by}
"""

ENTERED_ENDGAME = """
UNWIND $rows AS row
MATCH (g:Game {game_id: row.game_id})
MATCH (p:Position {fen_norm: row.fen_norm})
MERGE (g)-[r:ENTERED_ENDGAME]->(p)
SET r += row {.ply, .material_sig}
"""

MISTAKES = """
UNWIND $rows AS row
MATCH (p:Position {fen_norm: row.fen_norm})
MATCH (g:Game {game_id: row.game_id})
MERGE (p)-[r:MISTAKE_IN {ply: row.ply}]->(g)
SET r += row {.severity, .cp_loss, .mate_swing, .played_uci, .played_san, .best_uci}
"""

ENGINE_BEST = """
UNWIND $rows AS row
MATCH (a:Position {fen_norm: row.fen_before})
MATCH (b:Position {fen_norm: row.fen_after})
MERGE (a)-[r:ENGINE_BEST]->(b)
SET r.uci = row.uci, r.san = row.san
"""

META = """
MERGE (m:ChessGraphMeta {name: 'chessgraph'})
SET m = $props
"""

# Order matters: nodes before the relationships that MATCH them.
STEPS: tuple[tuple[str, str], ...] = (
    ("positions", POSITIONS),
    ("openings", OPENINGS),
    ("theory_moves", THEORY_MOVES),
    ("in_opening", IN_OPENING),
    ("endgame_patterns", ENDGAME_PATTERNS),
    ("endgame_benchmarks", ENDGAME_BENCHMARKS),
    ("endgame_links", ENDGAME_LINKS),
    ("players", PLAYERS),
    ("games", GAMES),
    ("played_as", PLAYED_AS),
    ("played_moves", PLAYED_MOVES),
    ("reached", REACHED),
    ("opened_with", OPENED_WITH),
    ("left_theory", LEFT_THEORY),
    ("entered_endgame", ENTERED_ENDGAME),
    ("mistakes", MISTAKES),
    ("engine_best", ENGINE_BEST),
)


def batches(rows: Sequence[Any], size: int) -> list[Sequence[Any]]:
    return [rows[i : i + size] for i in range(0, len(rows), size)]


def meta_properties(payload: GraphPayload) -> dict[str, Any]:
    """Neo4j properties cannot be maps, so counts become ``count_<step>`` properties."""
    props: dict[str, Any] = {
        "name": "chessgraph",
        "schema_version": payload.meta["schema_version"],
        "loaded_at": payload.meta["loaded_at"],
    }
    props.update({f"count_{name}": value for name, value in payload.meta["counts"].items()})
    return props


def ensure_schema(driver: Driver) -> None:
    with driver.session() as session:
        for statement in SCHEMA:
            session.run(statement).consume()


def label_counts(driver: Driver) -> dict[str, int]:
    """Node count of every label in the database (chess or not)."""
    counts: dict[str, int] = {}
    with driver.session() as session:
        labels = [record["label"] for record in session.run("CALL db.labels() YIELD label RETURN label")]
        for label in labels:
            escaped = label.replace("`", "``")
            record = session.run(f"MATCH (n:`{escaped}`) RETURN count(n) AS c").single()
            counts[label] = record["c"] if record else 0
    return counts


def reset_chess_graph(driver: Driver, rows_per_tx: int = 10_000) -> dict[str, int]:
    """Detach-delete nodes of the chess labels only. Returns deleted counts per label."""
    deleted: dict[str, int] = {}
    with driver.session() as session:
        for label in CHESS_LABELS:
            # CALL ... IN TRANSACTIONS must run in an implicit (auto-commit) transaction.
            summary = session.run(
                f"MATCH (n:`{label}`) CALL (n) {{ DETACH DELETE n }} IN TRANSACTIONS OF {int(rows_per_tx)} ROWS"
            ).consume()
            deleted[label] = summary.counters.nodes_deleted
            logger.info("Deleted %d %s nodes", deleted[label], label)
    return deleted


def _write(tx: ManagedTransaction, query: str, rows: Sequence[Any]) -> None:
    tx.run(query, rows=list(rows)).consume()


def write_graph(
    driver: Driver,
    payload: GraphPayload,
    batch_size: int = DEFAULT_BATCH,
    progress: Callable[[str, int], None] | None = None,
) -> dict[str, int]:
    """Write every step in order. Returns the number of rows sent per step."""
    sent: dict[str, int] = {}
    with driver.session() as session:
        for name, query in STEPS:
            rows = getattr(payload, name)
            for chunk in batches(rows, batch_size):
                session.execute_write(_write, query, chunk)
            sent[name] = len(rows)
            if progress:
                progress(name, len(rows))
        session.execute_write(lambda tx: tx.run(META, props=meta_properties(payload)).consume())
    return sent
