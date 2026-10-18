import logging
from typing import Any

import chess
from neo4j import Driver
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

PIECE_NAMES = {
    chess.PAWN: "Pawn",
    chess.KNIGHT: "Knight",
    chess.BISHOP: "Bishop",
    chess.ROOK: "Rook",
    chess.QUEEN: "Queen",
    chess.KING: "King",
}

MERGE_OPENING_NODES_CYPHER = """
UNWIND $batch AS row
MERGE (o:Opening {epd_norm: row.epd_norm})
SET o.opening_id = row.opening_id,
    o.eco_volume = row.eco_volume,
    o.eco_code = row.eco_code,
    o.opening_name = row.opening_name,
    o.pgn_line = row.pgn_line,
    o.uci_line = row.uci_line
MERGE (p:Position {fen_norm: row.epd_norm})
ON CREATE SET p.turn_color = row.turn_color,
              p.piece_count = row.piece_count,
              p.visit_count = 0
MERGE (p)-[:CLASSIFIED_AS]->(o)
"""

MERGE_THEORY_MOVES_CYPHER = """
UNWIND $batch AS row
MERGE (p1:Position {fen_norm: row.fen_before})
ON CREATE SET p1.turn_color = row.turn_before,
              p1.piece_count = row.pieces_before,
              p1.visit_count = 0
MERGE (p2:Position {fen_norm: row.fen_after})
ON CREATE SET p2.turn_color = row.turn_after,
              p2.piece_count = row.pieces_after,
              p2.visit_count = 0
SET p2.last_moved_piece = row.moved_piece,
    p2.last_move_san = row.san_move
MERGE (p1)-[r:THEORY_MOVE {uci_move: row.uci_move}]->(p2)
SET r.san_move = row.san_move,
    r.moved_piece = row.moved_piece,
    r.from_square = row.from_square,
    r.to_square = row.to_square,
    r.is_capture = row.is_capture,
    r.eco_code = row.eco_code
"""


def normalize_fen(fen_str: str) -> str:
    """Return the first four fields of a FEN string."""
    return " ".join(str(fen_str).strip().split(" ")[:4])


def count_pieces_from_fen(fen_norm: str) -> int:
    """Count total pieces on the board from the piece-placement section of a FEN string."""
    board_part = fen_norm.split(" ")[0]
    return sum(1 for char in board_part if char.isalpha())


def load_opening_graph(
    pg_engine: Engine,
    neo4j_driver: Driver,
    batch_size: int = 1000,
) -> tuple[int, int]:
    """
    Sync opening_theory from PostgreSQL into Neo4j as (:Opening) nodes,
    (:Position) nodes, [:CLASSIFIED_AS] edges, and step-by-step [:THEORY_MOVE] edges
    annotated with moved_piece, from_square, to_square, and is_capture.
    """
    fetch_sql = text(
        """
        SELECT opening_id, eco_volume, eco_code, opening_name, pgn_line, uci_line, epd_norm
        FROM opening_theory
        ORDER BY opening_id;
        """
    )

    with pg_engine.connect() as conn:
        rows = conn.execute(fetch_sql).fetchall()

    if not rows:
        logger.warning("No rows found in PostgreSQL opening_theory table")
        return 0, 0

    opening_records: list[dict[str, Any]] = []
    theory_edge_map: dict[tuple[str, str], dict[str, Any]] = {}

    for row in rows:
        epd_norm = normalize_fen(row.epd_norm)
        parts = epd_norm.split(" ")
        turn_color = parts[1] if len(parts) >= 2 else "w"

        opening_records.append(
            {
                "opening_id": row.opening_id,
                "eco_volume": row.eco_volume,
                "eco_code": row.eco_code,
                "opening_name": row.opening_name,
                "pgn_line": row.pgn_line,
                "uci_line": row.uci_line,
                "epd_norm": epd_norm,
                "turn_color": turn_color,
                "piece_count": count_pieces_from_fen(epd_norm),
            }
        )

        if row.uci_line:
            board = chess.Board()
            for uci_token in str(row.uci_line).split():
                try:
                    move = chess.Move.from_uci(uci_token)
                    if move not in board.legal_moves:
                        break
                    fen_before = normalize_fen(board.fen())
                    turn_before = "w" if board.turn == chess.WHITE else "b"
                    pieces_before = count_pieces_from_fen(fen_before)

                    piece_obj = board.piece_at(move.from_square)
                    moved_piece = PIECE_NAMES.get(piece_obj.piece_type, "Unknown") if piece_obj else "Unknown"
                    from_square = chess.square_name(move.from_square)
                    to_square = chess.square_name(move.to_square)
                    is_capture = board.is_capture(move)
                    san_move = board.san(move)

                    board.push(move)
                    fen_after = normalize_fen(board.fen())
                    turn_after = "w" if board.turn == chess.WHITE else "b"
                    pieces_after = count_pieces_from_fen(fen_after)

                    edge_key = (fen_before, uci_token)
                    theory_edge_map[edge_key] = {
                        "fen_before": fen_before,
                        "turn_before": turn_before,
                        "pieces_before": pieces_before,
                        "fen_after": fen_after,
                        "turn_after": turn_after,
                        "pieces_after": pieces_after,
                        "uci_move": uci_token,
                        "san_move": san_move,
                        "moved_piece": moved_piece,
                        "from_square": from_square,
                        "to_square": to_square,
                        "is_capture": is_capture,
                        "eco_code": row.eco_code,
                    }
                except ValueError:
                    break

    theory_edges = list(theory_edge_map.values())

    with neo4j_driver.session() as session:
        for idx in range(0, len(opening_records), batch_size):
            batch = opening_records[idx : idx + batch_size]
            session.run(MERGE_OPENING_NODES_CYPHER, batch=batch)

        for idx in range(0, len(theory_edges), batch_size):
            batch = theory_edges[idx : idx + batch_size]
            session.run(MERGE_THEORY_MOVES_CYPHER, batch=batch)

    logger.info(
        "Synced %d (:Opening) nodes and %d [:THEORY_MOVE] edges into Neo4j",
        len(opening_records),
        len(theory_edges),
    )
    return len(opening_records), len(theory_edges)