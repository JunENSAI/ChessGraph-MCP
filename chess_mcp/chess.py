"""Shared chess notation and position validation helpers."""

from __future__ import annotations

import chess


def full_fen(fen: str) -> str:
    """Return a six-field FEN, accepting the project's four-field position key."""
    fields = str(fen).strip().split()
    if len(fields) == 4:
        fields.extend(("0", "1"))
    if len(fields) != 6:
        raise ValueError("FEN must contain either four or six fields")
    candidate = " ".join(fields)
    board = chess.Board(candidate)
    if not board.is_valid():
        raise ValueError("FEN does not describe a valid chess position")
    return candidate


def parse_board(fen: str) -> chess.Board:
    """Parse and validate a four- or six-field FEN."""
    return chess.Board(full_fen(fen))


def normalize_fen(fen: str) -> str:
    """Return the four-field FEN key used by the PostgreSQL and Neo4j ETL.

    The ETL writes keys with python-chess, which keeps an en-passant square
    only when a capture there is legal, so the key is rebuilt the same way:
    ``... b KQkq e3`` after 1.e4 becomes ``... b KQkq -``.
    """
    board = parse_board(fen)
    return " ".join(board.fen(en_passant="legal").split()[:4])


def clamp_limit(value: int, maximum: int, *, minimum: int = 1) -> int:
    """Validate a caller-provided result or search limit."""
    if value < minimum:
        raise ValueError(f"limit must be at least {minimum}")
    return min(value, maximum)


# Move severity by stored centipawn loss (mover's side). The graph ETL labels
# MISTAKE_IN edges with these thresholds and the Neo4j tools filter by them.
SEVERITY_MIN_CP = {"inaccuracy": 50, "mistake": 100, "blunder": 300}


def severity_for(cp_loss: int | None) -> str | None:
    """The severity label of a centipawn loss, or None below an inaccuracy."""
    if cp_loss is None:
        return None
    label = None
    for name, threshold in SEVERITY_MIN_CP.items():
        if cp_loss >= threshold:
            label = name
    return label
