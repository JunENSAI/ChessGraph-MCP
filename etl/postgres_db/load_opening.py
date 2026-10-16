import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def normalize_fen(fen_str: str) -> str:
    """Return the first four fields of a FEN string so transpositions share a key."""
    return " ".join(str(fen_str).strip().split(" ")[:4])


def load_opening_theory(
    engine: Engine,
    parquet_path: Path,
    batch_size: int = 1000,
) -> dict[str, tuple[str, str]]:
    """
    Load the Hugging Face opening Parquet dataset into the opening_theory table
    and return a lookup dictionary mapping epd_norm to (eco_code, opening_name).
    """
    if not parquet_path.exists():
        logger.warning("Opening Parquet file not found at %s", parquet_path)
        return {}

    logger.info("Reading opening dataset from %s", parquet_path)
    selected_columns = ["eco-volume", "eco", "name", "pgn", "uci", "epd"]
    df = pd.read_parquet(parquet_path, columns=selected_columns)

    df = df.rename(
        columns={
            "eco-volume": "eco_volume",
            "eco": "eco_code",
            "name": "opening_name",
            "pgn": "pgn_line",
            "uci": "uci_line",
            "epd": "epd_norm",
        }
    )

    for column_name in df.columns:
        df[column_name] = df[column_name].astype(str).str.strip()

    df["epd_norm"] = df["epd_norm"].apply(normalize_fen)
    df = df.dropna(subset=["eco_code", "opening_name", "epd_norm"])

    with engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE opening_theory RESTART IDENTITY;"))
        df.to_sql(
            name="opening_theory",
            con=connection,
            if_exists="append",
            index=False,
            method="multi",
            chunksize=batch_size,
        )

    logger.info("Inserted %d rows into opening_theory", len(df))

    return {
        row.epd_norm: (row.eco_code, row.opening_name)
        for row in df.itertuples(index=False)
    }