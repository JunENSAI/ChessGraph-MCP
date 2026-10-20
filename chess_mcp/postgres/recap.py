"""Rating-band recap counted from stored games.

The favorite line is the stored opening name with the most games in that band.
A line that was played still ranks below any line that was played more often.
Endgame types are not stored on games, so the recap does not invent them.
"""

from __future__ import annotations

import chess

from pydantic import BaseModel, ConfigDict, Field

from chess_mcp.chess import parse_board

from .models import CoachingBrief, CoachingLine, CoachingSplit, CoachingTarget, TrainingTask


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
MIN_FAMILY_GAMES = 8
MAX_STRENGTHS = 3
MAX_SPLITS = 3
MIN_SPLIT_TIMES = 3
OPENING_PLY = 20
MIN_CALCULATION_LOSS = 100
MIN_CALCULATION_TIMES = 2
MAX_CALCULATION = 3
MATE_SENTINEL = 9000
ENDGAME_NOTE = "Endgame type is not stored on games."
TASK_PLIES = 12
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
DEFENSE_FAMILIES = ("French Defense", "Sicilian Defense", "Caro-Kann Defense")
SCANDINAVIAN = "Scandinavian Defense"
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
    average_opponent_elo: int | None = Field(default=None, alias="averageOpponentElo")
    average_elo_when_win: int | None = Field(default=None, alias="averageEloWhenWin")
    average_elo_when_loss: int | None = Field(default=None, alias="averageEloWhenLoss")


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


def opening_family(name: str) -> str:
    """One display name for an opening and its stored variations.

    London lines stay London System even when the database prefixes Queen's
    Pawn Game. Other names use the text before the first colon, so
    Scandinavian Defense and Scandinavian Defense: Main Line are one opening.
    """
    text = " ".join(name.split())
    if "london" in text.lower():
        return "London System"
    head, separator, _tail = text.partition(":")
    if separator:
        return head.strip()
    return text


def build_recap(
    rows: list[tuple],
    time_rows: list[tuple],
    clock_elo_rows: list[tuple] | None = None,
) -> RecapPayload:
    """Fold aggregated game rows into the rating-band payload the UI renders.

    ``clock_elo_rows`` are ``(band, game_type, average_opponent, average_when_win,
    average_when_loss)``. Missing rows leave those averages empty.
    """
    totals: dict[tuple[str, str], dict[str, int]] = {}
    lines: dict[tuple[str, str, str, str], dict[str, int]] = {}
    clocks: dict[tuple[str, str], dict[str, int]] = {}
    elo: dict[tuple[str, str], tuple[int | None, int | None, int | None]] = {}

    for band, color, name, eco, outcome, amount in rows:
        _add(totals.setdefault((band, color), _empty()), outcome, amount)
        _add(lines.setdefault((band, color, name, eco), _empty()), outcome, amount)
    for band, game_type, outcome, amount in time_rows:
        _add(clocks.setdefault((band, game_type), _empty()), outcome, amount)
    for band, game_type, average_opponent, average_win, average_loss in clock_elo_rows or []:
        elo[(band, game_type)] = (average_opponent, average_win, average_loss)

    def top_lines(band: str, color: str) -> list[OpeningLineStat]:
        grouped: dict[str, dict[str, int]] = {}
        eco_games: dict[tuple[str, str], int] = {}
        for (row_band, row_color, name, eco), counts in lines.items():
            if row_band != band or row_color != color:
                continue
            family = opening_family(name)
            bucket = grouped.setdefault(family, _empty())
            for key in ("wins", "draws", "losses"):
                bucket[key] += counts[key]
            eco_games[(family, eco)] = eco_games.get((family, eco), 0) + sum(counts.values())

        def primary_eco(family: str) -> str:
            choices = [
                (eco, games)
                for (row_family, eco), games in eco_games.items()
                if row_family == family
            ]
            choices.sort(key=lambda item: (-item[1], item[0]))
            return choices[0][0] if choices else "—"

        matching = list(grouped.items())
        matching.sort(key=lambda item: (-sum(item[1].values()), item[0]))
        return [
            OpeningLineStat(
                name=family,
                eco=primary_eco(family),
                results=OutcomeCounts.model_validate(counts),
            )
            for family, counts in matching[:TOP_LINES]
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
                average_opponent_elo=elo.get((band, game_type), (None, None, None))[0],
                average_elo_when_win=elo.get((band, game_type), (None, None, None))[1],
                average_elo_when_loss=elo.get((band, game_type), (None, None, None))[2],
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


def _score(counts: dict[str, int]) -> float:
    games = sum(counts.values())
    if games == 0:
        return 0.0
    return (counts["wins"] + counts["draws"] / 2) / games


def _best_san(fen: str, uci: str) -> str:
    try:
        board = parse_board(fen)
        move = chess.Move.from_uci(uci)
    except ValueError:
        return uci
    if move not in board.legal_moves:
        return uci
    return board.san(move)


def _splits(rows: list[tuple], *, minimum_times: int, limit: int) -> list[CoachingSplit]:
    """Merge repeated moves that share a position and both UCI moves."""
    buckets: dict[tuple[str, str, str], list] = {}
    for fen, ply, san, played_uci, best_uci, times, average in rows:
        if not best_uci or played_uci == best_uci or int(times) < 1:
            continue
        key = (str(fen), str(played_uci), str(best_uci))
        loss = float(average or 0) * int(times)
        slot = buckets.get(key)
        if slot is None:
            buckets[key] = [int(ply), str(san), int(times), loss]
        else:
            slot[0] = min(slot[0], int(ply))
            slot[2] += int(times)
            slot[3] += loss
    ranked = [
        (fen, ply, san, played_uci, best_uci, times, total_loss / times)
        for (fen, played_uci, best_uci), (ply, san, times, total_loss) in buckets.items()
        if times >= minimum_times
    ]
    ranked.sort(key=lambda item: (-item[5], -item[6], item[0]))
    splits: list[CoachingSplit] = []
    for fen, ply, san, played_uci, best_uci, times, average in ranked[:limit]:
        rounded = int(round(average))
        splits.append(
            CoachingSplit(
                fen=fen,
                ply=ply,
                played_san=san,
                played_uci=played_uci,
                best_uci=best_uci,
                best_san=_best_san(fen, best_uci),
                times=times,
                average_cp_loss=rounded,
                mate=rounded >= MATE_SENTINEL,
            )
        )
    return splits


def build_coaching_brief(
    family_rows: list[tuple],
    split_rows: list[tuple],
    calculation_rows: list[tuple],
    theory_rows: list[tuple] | None = None,
    endgame_rows: list[tuple] | None = None,
    puzzle_fens: list[str] | None = None,
) -> CoachingBrief:
    """Fold stored results into strengths, one weak opening, and four drills.

    ``family_rows`` are ``(opening_name, user_color, outcome, amount)``.
    ``split_rows`` are ``(opening_name, fen, ply, san, uci, best_uci, times,
    average_cp_loss)`` from the first 20 plies. ``calculation_rows`` drop the
    opening name and come from later plies. ``theory_rows`` are
    ``(opening_name, uci_line, pgn_line)``. ``endgame_rows`` are
    ``(endgame_type, fen_full, human_move_uci, elo_tier)``.
    """
    families: dict[str, dict[str, int]] = {}
    for name, _color, outcome, amount in family_rows:
        _add(families.setdefault(opening_family(str(name)), _empty()), str(outcome), int(amount))
    qualified = [
        (family, counts)
        for family, counts in families.items()
        if sum(counts.values()) >= MIN_FAMILY_GAMES
    ]

    def line(family: str, counts: dict[str, int]) -> CoachingLine:
        return CoachingLine(
            family=family,
            games=sum(counts.values()),
            wins=counts["wins"],
            draws=counts["draws"],
            losses=counts["losses"],
        )

    target_pair = min(qualified, key=lambda item: (_score(item[1]), -sum(item[1].values()), item[0]), default=None)
    target_name = target_pair[0] if target_pair else None
    strengths = [
        line(family, counts)
        for family, counts in sorted(
            ((family, counts) for family, counts in qualified if family != target_name),
            key=lambda item: (-_score(item[1]), -sum(item[1].values()), item[0]),
        )[:MAX_STRENGTHS]
    ]
    target_splits = [
        row[1:]
        for row in split_rows
        if target_name is not None and opening_family(str(row[0])) == target_name
    ]
    target = None
    if target_pair is not None:
        family, counts = target_pair
        target = CoachingTarget(
            family=family,
            games=sum(counts.values()),
            wins=counts["wins"],
            draws=counts["draws"],
            losses=counts["losses"],
            splits=_splits(target_splits, minimum_times=MIN_SPLIT_TIMES, limit=MAX_SPLITS),
        )
    return CoachingBrief(
        strengths=strengths,
        target=target,
        calculation=_splits(calculation_rows, minimum_times=MIN_CALCULATION_TIMES, limit=MAX_CALCULATION),
        endgames=ENDGAME_NOTE,
        tasks=_training_tasks(family_rows, theory_rows or [], endgame_rows or [], puzzle_fens or []),
    )


def _cap_line(line: str | None) -> str:
    if not line:
        return ""
    tokens = [token for token in str(line).replace(",", " ").split() if token]
    return " ".join(tokens[:TASK_PLIES])


def _record(counts: dict[str, int]) -> str:
    games = sum(counts.values())
    return f"{counts['wins']} wins, {counts['draws']} draws, and {counts['losses']} losses in {games} games"


def _by_color(family_rows: list[tuple]) -> dict[tuple[str, str], dict[str, int]]:
    grouped: dict[tuple[str, str], dict[str, int]] = {}
    for name, color, outcome, amount in family_rows:
        if color not in ("white", "black"):
            continue
        _add(grouped.setdefault((opening_family(str(name)), str(color)), _empty()), str(outcome), int(amount))
    return grouped


def _theory_index(theory_rows: list[tuple]) -> dict[str, tuple[str, str, str]]:
    found: dict[str, tuple[str, str, str]] = {}
    for name, uci, pgn in theory_rows:
        family = opening_family(str(name))
        if family in found:
            continue
        if not uci and not pgn:
            continue
        found[family] = (str(name), _cap_line(uci), _cap_line(pgn) if not uci else str(pgn or ""))
    return found


def _side(fen: str) -> str:
    fields = str(fen).split()
    return "black" if len(fields) > 1 and fields[1] == "b" else "white"


def _queen_pawn_rank(endgame_type: str) -> tuple[int, int]:
    code = endgame_type.upper()
    return (0 if "Q" in code and "P" in code else 1, len(code))


def _training_tasks(
    family_rows: list[tuple],
    theory_rows: list[tuple],
    endgame_rows: list[tuple],
    puzzle_fens: list[str],
) -> list[TrainingTask]:
    """Four drills. A missing stored line stays in the list with ready false."""
    colors = _by_color(family_rows)
    theory = _theory_index(theory_rows)

    def games_of(family: str, color: str) -> int:
        return sum(colors.get((family, color), _empty()).values())

    white = [
        (family, counts)
        for (family, color), counts in colors.items()
        if color == "white" and sum(counts.values()) >= MIN_FAMILY_GAMES
    ]
    weak = min(white, key=lambda item: (_score(item[1]), -sum(item[1].values()), item[0]), default=None)
    weak_name = weak[0] if weak else None
    excluded = {weak_name, SCANDINAVIAN, *DEFENSE_FAMILIES}
    candidates = [
        (family, games_of(family, "white"), stored)
        for family, stored in theory.items()
        if family not in excluded and "defense" not in family.lower() and "defence" not in family.lower()
    ]
    candidates.sort(key=lambda item: (item[1] == 0, item[1], -len(item[2][1].split()), item[0]))
    if weak is None:
        opening_reason = "No white opening has 8 finished games yet."
    else:
        opening_reason = f"{weak[0]} scores {_record(weak[1])}."
    if candidates:
        family, played, (stored_name, uci, pgn) = candidates[0]
        games = "game" if played == 1 else "games"
        opening_reason = f"{opening_reason} {stored_name} is stored in theory and you have {played} {games} in it."
        opening = TrainingTask(
            kind="opening",
            title=stored_name,
            reason=opening_reason,
            start_fen=START_FEN,
            uci_line=uci,
            pgn_line="" if uci else pgn,
            user_color="white",
            ready=bool(uci or pgn),
        )
    else:
        opening = TrainingTask(
            kind="opening",
            title="New opening",
            reason=f"{opening_reason} No other stored theory line is available.",
            start_fen=START_FEN,
            user_color="white",
            ready=False,
        )

    scandi = colors.get((SCANDINAVIAN, "black"), _empty())
    if sum(scandi.values()):
        defense_reason = f"{SCANDINAVIAN}: {_record(scandi)}."
    else:
        defense_reason = f"{SCANDINAVIAN} has no stored games."
    defense_choice = min(
        (
            (family, games_of(family, "black"), theory[family])
            for family in DEFENSE_FAMILIES
            if family in theory
        ),
        key=lambda item: (item[1], item[0]),
        default=None,
    )
    if defense_choice is None:
        defense = TrainingTask(
            kind="defense",
            title="Black defense",
            reason=f"{defense_reason} The theory line is missing.",
            start_fen=START_FEN,
            user_color="black",
            ready=False,
        )
    else:
        family, played, (stored_name, uci, pgn) = defense_choice
        defense = TrainingTask(
            kind="defense",
            title=stored_name,
            reason=f"{defense_reason} The drill is {stored_name}, which you have played {played} times.",
            start_fen=START_FEN,
            uci_line=uci,
            pgn_line="" if uci else pgn,
            user_color="black",
            ready=bool(uci or pgn),
        )

    chosen = min(
        endgame_rows,
        key=lambda row: (_queen_pawn_rank(str(row[0])), str(row[0])),
        default=None,
    )
    if chosen is None:
        endgame = TrainingTask(
            kind="endgame",
            title="Endgame technique",
            reason=f"No technique position is stored for the rating tier. {ENDGAME_NOTE}",
            start_fen=START_FEN,
            user_color="white",
            ready=False,
        )
    else:
        endgame_type, fen, human_move, tier = chosen
        endgame = TrainingTask(
            kind="endgame",
            title=str(endgame_type),
            reason=f"Technique position in the {tier or 'stored'} tier. {ENDGAME_NOTE}",
            start_fen=str(fen),
            uci_line=_cap_line(str(human_move)),
            user_color=_side(str(fen)),
            ready=bool(human_move),
        )

    fens = [str(fen) for fen in puzzle_fens if fen][:4]
    puzzle = TrainingTask(
        kind="puzzle",
        title="Calculation",
        reason=(
            "Candidate positions from your largest stored centipawn losses."
            if fens
            else "No stored centipawn loss is available for a mate search."
        ),
        start_fen=fens[0] if fens else START_FEN,
        user_color=_side(fens[0]) if fens else "white",
        ready=bool(fens),
        puzzle_fens=fens,
    )
    return [opening, defense, endgame, puzzle]
