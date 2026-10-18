import logging
from typing import Any

from neo4j import Driver
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

MERGE_ENDGAME_PATTERNS_CYPHER = """
UNWIND $batch AS row
MERGE (e:EndgamePattern {endgame_type: row.endgame_type})
SET e.piece_count = row.piece_count,
    e.benchmark_positions = row.benchmark_positions,
    e.avg_player_elo = row.avg_player_elo,
    e.sample_fen = row.sample_fen,
    e.sample_human_move = row.sample_human_move
"""

MERGE_ENDGAME_SAMPLES_CYPHER = """
UNWIND $batch AS row
MATCH (e:EndgamePattern {endgame_type: row.endgame_type})
MERGE (p:Position {fen_norm: row.fen_norm})
ON CREATE SET p.turn_color = row.turn_color,
              p.piece_count = row.piece_count,
              p.material_sig = row.endgame_type,
              p.visit_count = 0
MERGE (p)-[r:HAS_ENDGAME_TYPE]->(e)
SET r.benchmark_move_uci = row.human_move_uci,
    r.elo_tier = row.elo_tier,
    r.player_elo = row.player_elo
"""


def load_endgame_graph(
    pg_engine: Engine,
    neo4j_driver: Driver,
    max_samples_per_type: int = 25,
    batch_size: int = 1000,
) -> tuple[int, int]:
    """
    Sync endgame_theory from PostgreSQL into Neo4j as (:EndgamePattern) hub nodes
    and connect representative benchmark (:Position) nodes.
    """
    pattern_summary_sql = text(
        """
        SELECT
            endgame_type,
            MIN(piece_count) AS piece_count,
            COUNT(*) AS benchmark_positions,
            ROUND(AVG(player_elo))::INTEGER AS avg_player_elo,
            MIN(fen_norm) AS sample_fen,
            MIN(human_move_uci) AS sample_human_move
        FROM endgame_theory
        GROUP BY endgame_type
        ORDER BY benchmark_positions DESC;
        """
    )

    sample_positions_sql = text(
        """
        WITH ranked_samples AS (
            SELECT
                fen_norm,
                human_move_uci,
                endgame_type,
                piece_count,
                player_elo,
                elo_tier,
                ROW_NUMBER() OVER (PARTITION BY endgame_type ORDER BY player_elo DESC NULLS LAST) AS rn
            FROM endgame_theory
        )
        SELECT fen_norm, human_move_uci, endgame_type, piece_count, player_elo, elo_tier
        FROM ranked_samples
        WHERE rn <= :max_samples;
        """
    )

    with pg_engine.connect() as conn:
        pattern_rows = conn.execute(pattern_summary_sql).mappings().all()
        sample_rows = conn.execute(
            sample_positions_sql, {"max_samples": max_samples_per_type}
        ).mappings().all()

    if not pattern_rows:
        logger.warning("No rows found in PostgreSQL endgame_theory table")
        return 0, 0

    pattern_records: list[dict[str, Any]] = [dict(r) for r in pattern_rows]
    sample_records: list[dict[str, Any]] = []

    for row in sample_rows:
        fen_parts = str(row["fen_norm"]).split(" ")
        turn_color = fen_parts[1] if len(fen_parts) >= 2 else "w"
        record = dict(row)
        record["turn_color"] = turn_color
        sample_records.append(record)

    with neo4j_driver.session() as session:
        for idx in range(0, len(pattern_records), batch_size):
            batch = pattern_records[idx : idx + batch_size]
            session.run(MERGE_ENDGAME_PATTERNS_CYPHER, batch=batch)

        for idx in range(0, len(sample_records), batch_size):
            batch = sample_records[idx : idx + batch_size]
            session.run(MERGE_ENDGAME_SAMPLES_CYPHER, batch=batch)

    logger.info(
        "Synced %d (:EndgamePattern) hubs and %d benchmark endgame positions into Neo4j",
        len(pattern_records),
        len(sample_records),
    )
    return len(pattern_records), len(sample_records)