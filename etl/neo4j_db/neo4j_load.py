import logging
import sys
from pathlib import Path

from neo4j import GraphDatabase
from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_chessgame_graph import load_chessgame_graph
from load_endgame_graph import load_endgame_graph
from load_opening_graph import load_opening_graph

from chess_mcp.config import get_neo4j_settings, postgres_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("neo4j_load")


SCHEMA_CONSTRAINTS = [
    "CREATE CONSTRAINT position_fen_unique IF NOT EXISTS FOR (p:Position) REQUIRE p.fen_norm IS UNIQUE",
    "CREATE CONSTRAINT opening_epd_unique IF NOT EXISTS FOR (o:Opening) REQUIRE o.epd_norm IS UNIQUE",
    "CREATE CONSTRAINT endgame_type_unique IF NOT EXISTS FOR (e:EndgamePattern) REQUIRE e.endgame_type IS UNIQUE",
    "CREATE CONSTRAINT game_id_unique IF NOT EXISTS FOR (g:Game) REQUIRE g.game_id IS UNIQUE",
    "CREATE INDEX position_piece_count_idx IF NOT EXISTS FOR (p:Position) ON (p.piece_count)",
    "CREATE INDEX position_material_idx IF NOT EXISTS FOR (p:Position) ON (p.material_sig)",
    "CREATE INDEX opening_eco_idx IF NOT EXISTS FOR (o:Opening) ON (o.eco_code)",
    "CREATE INDEX game_type_idx IF NOT EXISTS FOR (g:Game) ON (g.game_type)",
]


def ensure_neo4j_schema(neo4j_driver) -> None:
    """Create Neo4j uniqueness constraints and indexes if they do not already exist."""
    with neo4j_driver.session() as session:
        for statement in SCHEMA_CONSTRAINTS:
            session.run(statement)
    logger.info("Verified Neo4j constraints and indexes")


def run_neo4j_etl() -> None:
    """Orchestrate the PostgreSQL-to-Neo4j Knowledge Graph synchronization pipeline."""
    pg_url = postgres_url()
    neo4j = get_neo4j_settings()
    logger.info("Connecting to PostgreSQL (%s) and Neo4j (%s)", pg_url.database, neo4j.uri)
    pg_engine = create_engine(pg_url)
    neo4j_driver = GraphDatabase.driver(neo4j.uri, auth=(neo4j.user, neo4j.password))

    try:
        neo4j_driver.verify_connectivity()
        ensure_neo4j_schema(neo4j_driver)

        openings_count, theory_edges_count = load_opening_graph(
            pg_engine=pg_engine,
            neo4j_driver=neo4j_driver,
        )

        endgame_hubs_count, endgame_samples_count = load_endgame_graph(
            pg_engine=pg_engine,
            neo4j_driver=neo4j_driver,
        )

        chessgame_summary = load_chessgame_graph(
            pg_engine=pg_engine,
            neo4j_driver=neo4j_driver,
        )

        logger.info(
            "Neo4j Sync Complete | Openings: %d | Theory Edges: %d | Endgame Hubs: %d | "
            "Endgame Samples: %d | Games: %d | Played Edges: %d | Blunder Links: %d",
            openings_count,
            theory_edges_count,
            endgame_hubs_count,
            endgame_samples_count,
            chessgame_summary["games"],
            chessgame_summary["played_move_edges"],
            chessgame_summary["blunder_links"],
        )
    finally:
        neo4j_driver.close()
        pg_engine.dispose()


if __name__ == "__main__":
    run_neo4j_etl()