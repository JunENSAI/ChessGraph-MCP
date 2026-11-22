import logging
import sys
from pathlib import Path

from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_chessgame import load_all_chess_games
from load_endgame import load_endgame_theory
from load_opening import load_opening_theory

from chess_mcp.config import base_data_dir, get_chess_username, postgres_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("postgres_load")

CHESS_USERNAME = get_chess_username()
BASE_DATA_DIR = base_data_dir()

MY_GAMES_DIR = BASE_DATA_DIR / "my_games"
OPENING_PARQUET_PATH = BASE_DATA_DIR / "opening_theory" / "chess_openings.parquet"
ENDGAME_CSV_PATH = BASE_DATA_DIR / "endgame_theory" / "endgame_atlas_bench.csv"
PGN_CATEGORIES = ["blitz", "rapid", "bullet", "daily", "bot"]


def run_postgres_etl() -> None:
    """Orchestrate the full PostgreSQL ingestion pipeline using root .env variables."""
    if not CHESS_USERNAME:
        raise SystemExit("Set CHESS_USERNAME in .env before loading games.")
    url = postgres_url()
    logger.info("Starting PostgreSQL ETL on database '%s'", url.database)
    engine = create_engine(url)

    opening_lookup = load_opening_theory(
        engine=engine,
        parquet_path=OPENING_PARQUET_PATH,
    )

    endgame_rows = load_endgame_theory(
        engine=engine,
        csv_path=ENDGAME_CSV_PATH,
    )

    game_summary = load_all_chess_games(
        engine=engine,
        games_dir=MY_GAMES_DIR,
        chess_username=CHESS_USERNAME,
        opening_lookup=opening_lookup,
        categories=PGN_CATEGORIES,
    )

    total_games = sum(counts[0] for counts in game_summary.values())
    total_moves = sum(counts[1] for counts in game_summary.values())

    logger.info(
        "ETL Complete | Openings: %d | Endgames: %d | Games: %d | Moves: %d",
        len(opening_lookup),
        endgame_rows,
        total_games,
        total_moves,
    )


if __name__ == "__main__":
    run_postgres_etl()