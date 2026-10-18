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
    """Return the four-field FEN key used by the PostgreSQL and Neo4j ETL."""
    return " ".join(full_fen(fen).split()[:4])


def clamp_limit(value: int, maximum: int, *, minimum: int = 1) -> int:
    """Validate a caller-provided result or search limit."""
    if value < minimum:
        raise ValueError(f"limit must be at least {minimum}")
    return min(value, maximum)


def replay_uci_line(
    fen: str, moves_uci: list[str]
) -> tuple[list[str], list[str], str]:
    """Replay a UCI line and return UCI, SAN, and the final full FEN."""
    board = parse_board(fen)
    normalized_uci: list[str] = []
    san_moves: list[str] = []
    for ply, token in enumerate(moves_uci, start=1):
        try:
            move = chess.Move.from_uci(token)
        except ValueError as exc:
            raise ValueError(f"Invalid UCI move at ply {ply}: {token}") from exc
        if move not in board.legal_moves:
            raise ValueError(f"Illegal UCI move at ply {ply}: {token}")
        normalized_uci.append(move.uci())
        san_moves.append(board.san(move))
        board.push(move)
    return normalized_uci, san_moves, board.fen(en_passant="fen")
