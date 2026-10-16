import sys
import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_opening import normalize_fen

logger = logging.getLogger(__name__)


def load_endgame_theory(
    engine: Engine,
    csv_path: Path,
    chunk_size: int = 10000,
    insert_batch_size: int = 2000,
) -> int:
    """
    Stream the Endgame Atlas CSV file in chunks, compute fen_norm,
    and load all rows into the endgame_theory table.
    """
    if not csv_path.exists():
        logger.warning("Endgame CSV file not found at %s", csv_path)
        return 0

    logger.info("Streaming endgame dataset from %s", csv_path)
    total_inserted = 0

    ordered_columns = [
        "fen_full",
        "fen_norm",
        "human_move_uci",
        "endgame_type",
        "piece_count",
        "time_control",
        "player_elo",
        "opp_elo",
        "elo_tier",
    ]

    with engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE endgame_theory RESTART IDENTITY;"))

        for chunk in pd.read_csv(csv_path, chunksize=chunk_size):
            chunk = chunk.rename(
                columns={
                    "fen": "fen_full",
                    "human_move": "human_move_uci",
                }
            )
            chunk["fen_norm"] = chunk["fen_full"].apply(normalize_fen)
            chunk = chunk[ordered_columns]

            chunk.to_sql(
                name="endgame_theory",
                con=connection,
                if_exists="append",
                index=False,
                method="multi",
                chunksize=insert_batch_size,
            )
            total_inserted += len(chunk)
            logger.info("Loaded %d cumulative rows into endgame_theory", total_inserted)

    return total_inserted