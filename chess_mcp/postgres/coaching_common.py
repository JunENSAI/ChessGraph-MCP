"""Small pure helpers shared by the recap and the training plan.

Kept in its own module so neither of the two callers imports the other.
"""

from __future__ import annotations

MIN_DRILL_PLIES = 6
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def opening_family(name: str) -> str:
    """One display name for an opening and its stored variations.

    London lines stay London System even when the database prefixes Queen's
    Pawn Game. Other names use the text before the first colon, so
    Scandinavian Defense and Scandinavian Defense: Main Line are one opening.
    """
    text = " ".join(str(name).split())
    if "london" in text.lower():
        return "London System"
    head, separator, _tail = text.partition(":")
    return head.strip() if separator else text


def score_rate(wins: int, draws: int, losses: int) -> float:
    """Points scored per game, 0.0-1.0. No games reads as an even 0.5."""
    games = wins + draws + losses
    if games == 0:
        return 0.5
    return (wins + draws / 2) / games


def line_plies(line: str | None) -> int:
    """Count plies in a stored UCI or PGN line, whatever separator it uses."""
    if not line:
        return 0
    cleaned = str(line).replace(",", " ").replace(";", " ")
    return len([token for token in cleaned.split() if token])
