"""Build the ChessGraph v2 graph in Neo4j from PostgreSQL.

    uv run python etl/neo4j_db/neo4j_load.py --dry-run   # transform only, print counts
    uv run python etl/neo4j_db/neo4j_load.py --reset     # delete chess labels, then load

The Neo4j database is shared with other projects. ``--reset`` deletes only the
chess labels in ``write.CHESS_LABELS``; the loader compares every other label's
node count before and after and exits non-zero if one changed.
"""

from __future__ import annotations

import argparse
import logging
from typing import Any

from neo4j import GraphDatabase
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from chess_mcp.config import get_chess_username, get_neo4j_settings, postgres_url
from etl.neo4j_db.transform import GraphPayload, build_graph
from etl.neo4j_db.write import CHESS_LABELS, ensure_schema, label_counts, reset_chess_graph, write_graph

logger = logging.getLogger("neo4j_load")

GAMES_SQL = text(
    """
    SELECT game_id, game_type::TEXT AS game_type, played_date,
           white_username, black_username, white_elo, black_elo,
           user_color, user_elo, opponent_elo, user_outcome, result::TEXT AS result,
           termination, time_control_raw, base_time_sec, increment_sec,
           eco_code, opening_name, total_plies
    FROM games
    ORDER BY game_id
    """
)

MOVES_SQL = text(
    """
    SELECT game_id, ply_number, turn_color, san_move, uci_move,
           fen_before_norm, fen_after_norm,
           eval_cp_before, eval_cp_after, cp_loss, best_move_uci
    FROM game_moves
    ORDER BY game_id, ply_number
    """
)

OPENINGS_SQL = text(
    "SELECT opening_id, eco_volume, eco_code, opening_name, pgn_line, uci_line, epd_norm "
    "FROM opening_theory ORDER BY opening_id"
)

ENDGAME_PATTERNS_SQL = text(
    """
    SELECT endgame_type,
           MIN(piece_count) AS piece_count,
           COUNT(*) AS benchmark_positions,
           ROUND(AVG(player_elo))::INTEGER AS avg_player_elo,
           MIN(fen_norm) AS sample_fen,
           MIN(human_move_uci) AS sample_human_move
    FROM endgame_theory
    GROUP BY endgame_type
    ORDER BY endgame_type
    """
)

ENDGAME_SAMPLES_SQL = text(
    """
    WITH ranked AS (
        SELECT fen_norm, human_move_uci, endgame_type, player_elo, elo_tier,
               ROW_NUMBER() OVER (
                   PARTITION BY endgame_type ORDER BY player_elo DESC NULLS LAST, fen_norm
               ) AS rn
        FROM endgame_theory
    )
    SELECT fen_norm, human_move_uci, endgame_type, player_elo, elo_tier
    FROM ranked
    WHERE rn <= :max_samples
    ORDER BY endgame_type, rn
    """
)


def fetch_rows(db: Engine, max_samples: int = 25) -> dict[str, list[Any]]:
    with db.connect() as conn:
        return {
            "games": list(conn.execute(GAMES_SQL).mappings()),
            "moves": list(conn.execute(MOVES_SQL).mappings()),
            "openings": list(conn.execute(OPENINGS_SQL).mappings()),
            "endgame_patterns": list(conn.execute(ENDGAME_PATTERNS_SQL).mappings()),
            "endgame_samples": list(conn.execute(ENDGAME_SAMPLES_SQL, {"max_samples": max_samples}).mappings()),
        }


def other_label_changes(before: dict[str, int], after: dict[str, int]) -> dict[str, tuple[int, int]]:
    """Non-chess labels whose node count differs between two snapshots."""
    labels = (set(before) | set(after)) - set(CHESS_LABELS)
    return {
        label: (before.get(label, 0), after.get(label, 0))
        for label in sorted(labels)
        if before.get(label, 0) != after.get(label, 0)
    }


def log_counts(payload: GraphPayload) -> None:
    for name, value in payload.counts().items():
        logger.info("  %-20s %9d", name, value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete the chess labels before loading")
    parser.add_argument("--dry-run", action="store_true", help="read PostgreSQL and transform; write nothing")
    parser.add_argument("--batch-size", type=int, default=5_000)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    owner = get_chess_username()
    if not owner:
        logger.error("CHESS_USERNAME is not set in .env; it decides which moves are yours.")
        return 1

    db = create_engine(postgres_url())
    try:
        rows = fetch_rows(db)
    finally:
        db.dispose()
    logger.info("Read %d games and %d moves from PostgreSQL", len(rows["games"]), len(rows["moves"]))
    payload = build_graph(owner=owner, **rows)
    del rows
    logger.info("Graph v2 rows:")
    log_counts(payload)
    if args.dry_run:
        return 0

    settings = get_neo4j_settings()
    driver = GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password))
    try:
        driver.verify_connectivity()
        before = label_counts(driver)
        if args.reset:
            reset_chess_graph(driver)
        ensure_schema(driver)
        write_graph(
            driver,
            payload,
            batch_size=args.batch_size,
            progress=lambda name, n: logger.info("Wrote %-20s %9d", name, n),
        )
        after = label_counts(driver)
    finally:
        driver.close()

    for label in CHESS_LABELS:
        logger.info("%-16s %9d -> %9d", label, before.get(label, 0), after.get(label, 0))
    changed = other_label_changes(before, after)
    if changed:
        logger.error("Non-chess labels changed: %s", changed)
        return 2
    logger.info("Non-chess labels unchanged (%d labels checked)", len(set(before) - set(CHESS_LABELS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
