"""Rank the drills worth doing, from the same stored rows the brief uses.

Pure functions: tuples in, a pydantic plan out. No SQL lives here, so the
ranking can be reasoned about and tested without a database.

The weights are published on purpose. Every number an item shows comes from a
stored column; nothing is inferred about a position the player has not played.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..chess import SEVERITY_MIN_CP
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


# One focus, seven days. The program reuses the plan's top drill and the brief's
# repeated-mistake positions; it adds no new evidence.

PROGRAM_DAYS = 7
MAX_PROGRAM_POSITIONS = 5

ProgramKind = Literal["learn", "drill", "mistakes", "play", "review"]


class ProgramPosition(BaseModel):
    """A position where the player repeated a costly move, with the stored engine move."""

    fen: str
    best_uci: str
    played_san: str
    times: int = Field(ge=1)
    average_cp_loss: int = Field(ge=0)


class ProgramDay(BaseModel):
    day: int = Field(ge=1, le=PROGRAM_DAYS)
    kind: ProgramKind
    title: str
    goal: str
    start_fen: str = START_FEN
    uci_line: str = ""
    user_color: Literal["white", "black"] = "white"
    positions: list[ProgramPosition] = Field(default_factory=list)
    opponent_elo: int | None = None


class TrainingProgram(BaseModel):
    focus: str | None = None
    title: str = ""
    reason: str = ""
    user_color: Literal["white", "black"] = "white"
    check_after_games: int = Field(default=20, ge=1)
    days: list[ProgramDay] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def _focus(plan: TrainingPlan, lines: list[tuple]) -> tuple[PlanItem, str, str] | None:
    """The highest-ranked opening or defense that has a line long enough to drill.

    The line is the player's most played variant of that family with a stored
    theory line of at least ``MIN_DRILL_PLIES``; the plan item's own line is the
    fallback. Returns the item, the stored opening name and the UCI line.
    """
    for item in plan.items:
        if item.kind not in ("opening", "defense"):
            continue
        family = opening_family(item.title)
        own = sorted(
            (
                (int(games), str(name), str(uci))
                for name, color, games, uci in lines
                if str(color) == item.user_color
                and opening_family(name) == family
                and uci
                and line_plies(str(uci)) >= MIN_DRILL_PLIES
            ),
            key=lambda row: (-row[0], row[1]),
        )
        if own:
            return item, own[0][1], own[0][2]
        if item.ready and item.uci_line:
            return item, item.title, item.uci_line
    return None


def _cost(position: ProgramPosition) -> int:
    return position.times * position.average_cp_loss


def _mistake_positions(family: str, color: str, split_rows: list[tuple]) -> list[ProgramPosition]:
    """The family's repeated moves that lose at least an inaccuracy, with the player to move.

    Costliest first: times played multiplied by the average centipawn loss.
    """
    side = "w" if color == "white" else "b"
    best: dict[str, ProgramPosition] = {}
    for name, fen, _ply, san, _played, uci_best, times, cp_loss in split_rows:
        fen = str(fen)
        if opening_family(name) != family or not uci_best or fen.split()[1:2] != [side]:
            continue
        if int(cp_loss or 0) < SEVERITY_MIN_CP["inaccuracy"]:
            continue
        position = ProgramPosition(
            fen=fen,
            best_uci=str(uci_best),
            played_san=str(san),
            times=max(int(times or 1), 1),
            average_cp_loss=max(int(cp_loss or 0), 0),
        )
        kept = best.get(fen)
        if kept is None or _cost(position) > _cost(kept):
            best[fen] = position
    ranked = sorted(best.values(), key=lambda item: (-_cost(item), item.fen))
    return ranked[:MAX_PROGRAM_POSITIONS]


def build_program(
    plan: TrainingPlan,
    *,
    lines: list[tuple] | None = None,
    split_rows: list[tuple] | None = None,
    average_rating: float | None = None,
) -> TrainingProgram:
    """Seven days on the plan's top opening: learn, drill, fix the stored mistakes, play, review.

    ``lines`` are ``(opening_name, user_color, games, uci_line)``: the player's
    opening lessons for both colours. ``split_rows`` are the brief's split
    tuples, as ``rank_plan`` takes them. The opponent strength is the player's
    average rating, rounded.
    """
    found = _focus(plan, lines or [])
    if found is None:
        return TrainingProgram(notes=["No opening has a stored line long enough to drill yet, so there is no weekly focus."])

    item, title, line = found
    family = opening_family(item.title)
    color = item.user_color
    elo = int(round(average_rating)) if average_rating is not None else None
    positions = _mistake_positions(family, color, split_rows or [])
    record = item.reason.split(". ")[0].rstrip(".") + "."

    def day(number: int, kind: ProgramKind, title: str, goal: str, **extra: object) -> ProgramDay:
        return ProgramDay(day=number, kind=kind, title=title, goal=goal, uci_line=line, user_color=color, **extra)

    def mistakes_or_drill(number: int, title: str, goal: str) -> ProgramDay:
        if positions:
            return day(number, "mistakes", title, goal, positions=positions)
        return day(
            number,
            "drill",
            "Play the line again",
            f"No repeated mistake is stored in the {family}, so play your side of the line again.",
        )

    strength = f"at {elo}, your average rating" if elo is not None else "at the default strength"
    days = [
        day(1, "learn", "Learn the line", f"Watch the stored line of {title} once, then name each of your moves before it is played."),
        day(2, "drill", "Play the line", "Play your side of the line twice in a row without a wrong move."),
        mistakes_or_drill(
            3,
            "Your repeated mistakes",
            f"Find the stored engine move in the {len(positions)} {family} positions where your repeated moves cost the most.",
        ),
        day(4, "play", "Play it against Stockfish", f"Play the line, then finish the game against Stockfish {strength}.", opponent_elo=elo),
        mistakes_or_drill(5, "Second pass", "Find each stored engine move again, this time without a hint."),
        day(6, "play", "Play it again", f"Another game from the line against Stockfish {strength}.", opponent_elo=elo),
        day(7, "review", "Review", f"{record} {item.goal}"),
    ]
    notes = [f"Focus chosen by the plan ranking: {family} has the highest weight among openings with a line to drill."]
    if not positions:
        notes.append(f"No repeated move losing {SEVERITY_MIN_CP['inaccuracy']} cp or more is stored for the {family} with you to move.")
    return TrainingProgram(
        focus=family,
        title=title,
        reason=item.reason,
        user_color=color,
        check_after_games=item.check_after_games,
        days=days,
        notes=notes,
    )
