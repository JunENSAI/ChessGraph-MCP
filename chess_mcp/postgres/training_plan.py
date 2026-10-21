"""Rank the drills worth doing, from the same stored rows the brief uses.

Pure functions: tuples in, a pydantic plan out. No SQL lives here, so the
ranking can be reasoned about and tested without a database.

The weights are published on purpose. Every number an item shows comes from a
stored column; nothing is inferred about a position the player has not played.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .coaching_common import (
    MIN_DRILL_PLIES,
    START_FEN,
    line_plies,
    opening_family,
    score_rate,
)

MAX_PLAN_ITEMS = 6

# Equal ranking weight per input. Change these together, never one silently.
_WEIGHTS = {
    "volume": 0.25,      # games played in the family
    "score": 0.40,       # distance below a 50% score
    "cp_loss": 0.25,     # stored centipawn loss on repeated moves
    "short_line": 0.10,  # a stored line too short to drill
}
_VOLUME_CEILING = 40
_CP_LOSS_CEILING = 600
MIN_FAMILY_GAMES = 2
MIN_STRENGTH_GAMES = 5


class PlanItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    kind: Literal["opening", "defense", "endgame", "puzzle"]
    title: str
    reason: str
    weight: float = Field(ge=0.0, le=1.0)
    ready: bool = False
    goal: str
    check_after_games: int = Field(default=20, ge=1)
    start_fen: str = ""
    uci_line: str = ""
    pgn_line: str = ""
    user_color: Literal["white", "black"] = "white"
    puzzle_fens: list[str] = Field(default_factory=list)


class TrainingPlan(BaseModel):
    items: list[PlanItem] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def plan_weights() -> dict[str, float]:
    """The ranking weights, for display and for tests."""
    return dict(_WEIGHTS)


def _weight(volume: int, score: float, cp_loss: int, short_line: bool) -> float:
    w = _WEIGHTS
    return (
        w["volume"] * min(volume / _VOLUME_CEILING, 1.0)
        + w["score"] * min(max(0.5 - score, 0.0) / 0.5, 1.0)
        + w["cp_loss"] * min(cp_loss / _CP_LOSS_CEILING, 1.0)
        + w["short_line"] * (1.0 if short_line else 0.0)
    )


def rank_plan(
    *,
    family_rows: list[tuple],
    split_rows: list[tuple] | None = None,
    calculation_rows: list[tuple] | None = None,
    theory_rows: list[tuple] | None = None,
    time_rows: list[tuple] | None = None,
) -> TrainingPlan:
    """Rank drills from stored results.

    ``family_rows`` are ``(opening_name, user_color, outcome, amount)``.

    ``split_rows`` and ``calculation_rows`` are the brief's split tuples, in
    the order ``repository.get_coaching_brief`` passes them:
    ``(opening_name, fen, ply, san, uci_played, uci_best, times, average_cp_loss)``.

    ``theory_rows`` are ``(opening_name, uci_line, pgn_line)``.
    ``time_rows`` are ``(game_type, outcome, amount)``, used for one note.
    """
    totals: dict[str, dict[str, int]] = {}
    colors: dict[str, str] = {}
    for name, color, outcome, amount in family_rows:
        family = opening_family(name)
        bucket = totals.setdefault(family, {"wins": 0, "draws": 0, "losses": 0})
        key = {"win": "wins", "draw": "draws", "loss": "losses"}.get(str(outcome))
        if key is not None:
            bucket[key] += int(amount)
        if str(color) in ("white", "black"):
            colors.setdefault(family, str(color))

    loss_by_family: dict[str, int] = {}
    for row in split_rows or []:
        family = opening_family(row[0])
        loss_by_family[family] = loss_by_family.get(family, 0) + int(row[7] or 0)

    theory: dict[str, tuple[str, str, str]] = {}
    for name, uci, pgn in theory_rows or []:
        family = opening_family(name)
        if family not in theory and (uci or pgn):
            theory[family] = (str(name), str(uci or ""), str(pgn or ""))

    ranked: list[PlanItem] = []
    for family, counts in totals.items():
        games = sum(counts.values())
        if games < MIN_FAMILY_GAMES:
            continue
        score = score_rate(counts["wins"], counts["draws"], counts["losses"])
        stored_name, uci, pgn = theory.get(family, ("", "", ""))
        plies = line_plies(uci or pgn)
        short = bool(uci or pgn) and plies < MIN_DRILL_PLIES
        color = colors.get(family, "white")
        reason = (
            f"{family}: {counts['wins']} wins, {counts['draws']} draws, "
            f"{counts['losses']} losses in {games} games ({round(score * 100)}% score)."
        )
        if short:
            reason += f" Stored line has {plies} plies, under the {MIN_DRILL_PLIES} needed."
        if not stored_name:
            reason += " No stored theory line for this family."
        ranked.append(
            PlanItem(
                kind="defense" if color == "black" else "opening",
                title=stored_name or family,
                reason=reason,
                weight=round(_weight(games, score, loss_by_family.get(family, 0), short), 4),
                ready=bool(uci or pgn) and not short,
                goal=f"Play 20 games in the {family} and raise its score above 50%.",
                check_after_games=20,
                start_fen=START_FEN,
                uci_line=uci,
                pgn_line="" if uci else pgn,
                user_color=color,
            )
        )

    for row in calculation_rows or []:
        family = opening_family(row[0])
        ranked.append(
            PlanItem(
                kind="puzzle",
                title=f"Calculation · {family}",
                reason=(
                    f"From ply {int(row[2])} of your {family} games you played {row[3]} "
                    f"{int(row[6])} times; the stored engine move was {row[5] or 'not recorded'}. "
                    f"Average loss {int(row[7])} cp."
                ),
                weight=round(_weight(0, 0.5, int(row[7]), False), 4),
                ready=True,
                goal="Find the engine move in this position before you move a piece.",
                check_after_games=10,
                start_fen=str(row[1]),
                puzzle_fens=[str(row[1])],
                user_color="black" if str(row[1]).split()[1:2] == ["b"] else "white",
            )
        )

    strengths = [
        family
        for family, counts in sorted(
            totals.items(),
            key=lambda item: (-score_rate(item[1]["wins"], item[1]["draws"], item[1]["losses"]), item[0]),
        )
        if sum(counts.values()) >= MIN_STRENGTH_GAMES
    ][:3]

    notes: list[str] = []
    by_type: dict[str, int] = {}
    for game_type, _outcome, amount in time_rows or []:
        by_type[str(game_type)] = by_type.get(str(game_type), 0) + int(amount)
    busiest = sorted(by_type.items(), key=lambda item: (-item[1], item[0]))[:1]
    if busiest:
        notes.append(f"Most stored games are {busiest[0][0]} ({busiest[0][1]} games).")
    notes.append("Endgame type is not stored on games, so no endgame weakness is claimed here.")

    ranked.sort(key=lambda item: (-item.weight, item.title))
    return TrainingPlan(items=ranked[:MAX_PLAN_ITEMS], strengths=strengths, notes=notes)
