"""Print a rating-band recap as JSON, counted from the local games table.

The favorite opening is the stored opening_name with the most games in that
band. A line that was played still ranks below any line that was played more
often. Endgame types are not stored on games, so this recap does not invent them.
"""

from __future__ import annotations

import json
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from chess_mcp.config import get_postgres_settings


BANDS = (
    ("under-1700", "Under 1700"),
    ("1700-1799", "1700–1799"),
    ("1800-1899", "1800–1899"),
    ("1900-1999", "1900–1999"),
    ("2000-plus", "2000+"),
)
BAND_CASE = """
CASE
    WHEN user_elo < 1700 THEN 'under-1700'
    WHEN user_elo < 1800 THEN '1700-1799'
    WHEN user_elo < 1900 THEN '1800-1899'
    WHEN user_elo < 2000 THEN '1900-1999'
    ELSE '2000-plus'
END
"""
TOP_LINES = 6
TIME_LABELS = {
    "rapid": "Rapid",
    "blitz": "Blitz",
    "bullet": "Bullet",
    "daily": "Daily",
    "bot": "Bot",
}


def _empty_counts() -> dict[str, int]:
    return {"wins": 0, "draws": 0, "losses": 0}


def _add(counts: dict[str, int], outcome: str, amount: int) -> None:
    key = {"win": "wins", "draw": "draws", "loss": "losses"}.get(outcome)
    if key is not None:
        counts[key] += amount


def build_recap(rows: list[tuple], time_rows: list[tuple]) -> dict:
    totals: dict[tuple[str, str], dict[str, int]] = {}
    lines: dict[tuple[str, str, str, str], dict[str, int]] = {}
    clocks: dict[tuple[str, str], dict[str, int]] = {}

    for band, color, name, eco, outcome, amount in rows:
        _add(totals.setdefault((band, color), _empty_counts()), outcome, amount)
        _add(lines.setdefault((band, color, name, eco), _empty_counts()), outcome, amount)
    for band, game_type, outcome, amount in time_rows:
        _add(clocks.setdefault((band, game_type), _empty_counts()), outcome, amount)

    def top_lines(band: str, color: str) -> list[dict]:
        matching = [
            (name, eco, counts)
            for (row_band, row_color, name, eco), counts in lines.items()
            if row_band == band and row_color == color
        ]
        matching.sort(key=lambda item: (-sum(item[2].values()), item[0], item[1]))
        return [
            {"name": name, "eco": eco, "results": counts}
            for name, eco, counts in matching[:TOP_LINES]
        ]

    def time_controls(band: str) -> list[dict]:
        matching = [
            (game_type, counts)
            for (row_band, game_type), counts in clocks.items()
            if row_band == band and sum(counts.values()) > 0
        ]
        matching.sort(key=lambda item: (-sum(item[1].values()), item[0]))
        return [
            {
                "id": game_type,
                "label": TIME_LABELS.get(game_type, game_type),
                "results": counts,
            }
            for game_type, counts in matching
        ]

    bands = []
    for band_id, label in BANDS:
        bands.append(
            {
                "id": band_id,
                "label": label,
                "white": totals.get((band_id, "white"), _empty_counts()),
                "black": totals.get((band_id, "black"), _empty_counts()),
                "openingsWhite": top_lines(band_id, "white"),
                "defensesBlack": top_lines(band_id, "black"),
                "timeControls": time_controls(band_id),
            }
        )
    game_count = sum(sum(counts.values()) for counts in totals.values())
    return {"gameCount": game_count, "bands": bands}


def main() -> int:
    opening_sql = text(
        f"""
        SELECT
            {BAND_CASE} AS band,
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
    )
    time_sql = text(
        f"""
        SELECT
            {BAND_CASE} AS band,
            game_type::text AS game_type,
            user_outcome,
            count(*) AS amount
        FROM games
        WHERE user_color IN ('white', 'black')
          AND user_outcome IN ('win', 'loss', 'draw')
        GROUP BY 1, 2, 3
        """
    )
    try:
        engine = create_engine(get_postgres_settings().database_url)
        with engine.connect().execution_options(postgresql_readonly=True) as connection:
            opening_rows = [tuple(row) for row in connection.execute(opening_sql)]
            time_rows = [tuple(row) for row in connection.execute(time_sql)]
    except SQLAlchemyError:
        print("PostgreSQL is not accepting connections. Start it, then reload the recap.", file=sys.stderr)
        return 1

    json.dump(build_recap(opening_rows, time_rows), sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
