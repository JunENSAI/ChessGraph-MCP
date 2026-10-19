"""Rating-band recap counted from stored games.

The favorite line is the stored opening name with the most games in that band.
A line that was played still ranks below any line that was played more often.
Endgame types are not stored on games, so the recap does not invent them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


BANDS = (
    ("under-1700", "Under 1700"),
    ("1700-1799", "1700–1799"),
    ("1800-1899", "1800–1899"),
    ("1900-1999", "1900–1999"),
    ("2000-plus", "2000+"),
)
BAND_SQL = """
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


class RecapModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class OutcomeCounts(RecapModel):
    wins: int = 0
    draws: int = 0
    losses: int = 0


class OpeningLineStat(RecapModel):
    name: str
    eco: str
    results: OutcomeCounts


class TimeControlStat(RecapModel):
    id: str
    label: str
    results: OutcomeCounts


class RecapBand(RecapModel):
    id: str
    label: str
    white: OutcomeCounts
    black: OutcomeCounts
    openings_white: list[OpeningLineStat] = Field(alias="openingsWhite")
    defenses_black: list[OpeningLineStat] = Field(alias="defensesBlack")
    time_controls: list[TimeControlStat] = Field(alias="timeControls")


class RecapPayload(RecapModel):
    game_count: int = Field(alias="gameCount")
    bands: list[RecapBand]


def _empty() -> dict[str, int]:
    return {"wins": 0, "draws": 0, "losses": 0}


def _add(counts: dict[str, int], outcome: str, amount: int) -> None:
    key = {"win": "wins", "draw": "draws", "loss": "losses"}.get(outcome)
    if key is not None:
        counts[key] += amount


def build_recap(rows: list[tuple], time_rows: list[tuple]) -> RecapPayload:
    """Fold aggregated game rows into the rating-band payload the UI renders."""
    totals: dict[tuple[str, str], dict[str, int]] = {}
    lines: dict[tuple[str, str, str, str], dict[str, int]] = {}
    clocks: dict[tuple[str, str], dict[str, int]] = {}

    for band, color, name, eco, outcome, amount in rows:
        _add(totals.setdefault((band, color), _empty()), outcome, amount)
        _add(lines.setdefault((band, color, name, eco), _empty()), outcome, amount)
    for band, game_type, outcome, amount in time_rows:
        _add(clocks.setdefault((band, game_type), _empty()), outcome, amount)

    def top_lines(band: str, color: str) -> list[OpeningLineStat]:
        matching = [
            (name, eco, counts)
            for (row_band, row_color, name, eco), counts in lines.items()
            if row_band == band and row_color == color
        ]
        matching.sort(key=lambda item: (-sum(item[2].values()), item[0], item[1]))
        return [
            OpeningLineStat(name=name, eco=eco, results=OutcomeCounts.model_validate(counts))
            for name, eco, counts in matching[:TOP_LINES]
        ]

    def time_controls(band: str) -> list[TimeControlStat]:
        matching = [
            (game_type, counts)
            for (row_band, game_type), counts in clocks.items()
            if row_band == band and sum(counts.values()) > 0
        ]
        matching.sort(key=lambda item: (-sum(item[1].values()), item[0]))
        return [
            TimeControlStat(
                id=game_type,
                label=TIME_LABELS.get(game_type, game_type),
                results=OutcomeCounts.model_validate(counts),
            )
            for game_type, counts in matching
        ]

    bands = [
        RecapBand(
            id=band_id,
            label=label,
            white=OutcomeCounts.model_validate(totals.get((band_id, "white"), _empty())),
            black=OutcomeCounts.model_validate(totals.get((band_id, "black"), _empty())),
            openings_white=top_lines(band_id, "white"),
            defenses_black=top_lines(band_id, "black"),
            time_controls=time_controls(band_id),
        )
        for band_id, label in BANDS
    ]
    game_count = sum(sum(counts.values()) for counts in totals.values())
    return RecapPayload(game_count=game_count, bands=bands)
