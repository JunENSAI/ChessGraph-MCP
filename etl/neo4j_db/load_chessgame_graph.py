import logging
from typing import Any

from neo4j import Driver
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

PIECE_ORDER = ["Q", "R", "B", "N", "P"]

SAN_PREFIX_TO_PIECE = {
    "N": "Knight",
    "B": "Bishop",
    "R": "Rook",
    "Q": "Queen",
    "K": "King",
    "O": "King",
}

MERGE_GAMES_CYPHER = """
UNWIND $batch AS row
MERGE (g:Game {game_id: row.game_id})
SET g.game_type = row.game_type,
    g.played_date = toString(row.played_date),
    g.user_color = row.user_color,
    g.user_elo = row.user_elo,
    g.opponent_elo = row.opponent_elo,
    g.user_outcome = row.user_outcome,
    g.result = row.result,
    g.eco_code = row.eco_code,
    g.opening_name = row.opening_name,
    g.total_plies = row.total_plies
"""

MERGE_PLAYED_MOVES_CYPHER = """
UNWIND $batch AS row
MERGE (p1:Position {fen_norm: row.fen_before_norm})
SET p1.turn_color = row.turn_before,
    p1.piece_count = row.pieces_before,
    p1.material_sig = row.material_before,
    p1.eval_cp = coalesce(row.avg_eval_before, p1.eval_cp),
    p1.best_move_uci = coalesce(row.best_move_uci, p1.best_move_uci),
    p1.visit_count = row.total_games

MERGE (p2:Position {fen_norm: row.fen_after_norm})
SET p2.turn_color = row.turn_after,
    p2.piece_count = row.pieces_after,
    p2.material_sig = row.material_after,
    p2.last_moved_piece = row.moved_piece,
    p2.last_move_san = row.san_move,
    p2.eval_cp = coalesce(row.avg_eval_after, p2.eval_cp),
    p2.visit_count = coalesce(p2.visit_count, 0) + row.total_games

MERGE (p1)-[r:PLAYED_MOVE {uci_move: row.uci_move}]->(p2)
SET r.san_move = row.san_move,
    r.moved_piece = row.moved_piece,
    r.from_square = row.from_square,
    r.to_square = row.to_square,
    r.is_capture = row.is_capture,
    r.total_games = row.total_games,
    r.wins = row.wins,
    r.losses = row.losses,
    r.draws = row.draws,
    r.win_rate_pct = row.win_rate_pct,
    r.avg_cp_loss = row.avg_cp_loss,
    r.avg_clock_sec = row.avg_clock_sec,
    r.best_move_uci = row.best_move_uci
"""

LINK_ENDGAME_TRANSITIONS_CYPHER = """
UNWIND $batch AS row
MATCH (p:Position {fen_norm: row.fen_norm})
MERGE (e:EndgamePattern {endgame_type: row.material_sig})
MERGE (p)-[:HAS_ENDGAME_TYPE]->(e)
"""

LINK_BLUNDERS_TO_GAMES_CYPHER = """
UNWIND $batch AS row
MATCH (p:Position {fen_norm: row.fen_before_norm})
MATCH (g:Game {game_id: row.game_id})
MERGE (p)-[r:BLUNDERED_IN {ply_number: row.ply_number}]->(g)
SET r.played_san = row.san_move,
    r.played_uci = row.uci_move,
    r.moved_piece = row.moved_piece,
    r.best_move_uci = row.best_move_uci,
    r.cp_loss = row.cp_loss,
    r.clock_rem_sec = row.clock_rem_sec
"""


def extract_move_metadata(san_move: str, uci_move: str) -> tuple[str, str, str, bool]:
    """
    Extract the explicit piece name ('Pawn', 'Knight', 'Bishop', 'Rook', 'Queen', 'King'),
    from_square, to_square, and is_capture flag from SAN and UCI move strings.
    """
    clean_san = str(san_move).strip()
    clean_uci = str(uci_move).strip()

    first_char = clean_san[0] if clean_san else ""
    moved_piece = SAN_PREFIX_TO_PIECE.get(first_char, "Pawn")

    from_square = clean_uci[:2] if len(clean_uci) >= 4 else ""
    to_square = clean_uci[2:4] if len(clean_uci) >= 4 else ""
    is_capture = "x" in clean_san

    return moved_piece, from_square, to_square, is_capture


def extract_board_signature(fen_norm: str) -> tuple[str, int, str]:
    """
    Extract active turn color, total piece count, and canonical material signature
    (such as KRvKP) directly from a 4-field normalized FEN string.
    """
    parts = fen_norm.split(" ")
    board_part = parts[0]
    turn_color = parts[1] if len(parts) >= 2 else "w"

    white_counts = {p: 0 for p in PIECE_ORDER}
    black_counts = {p: 0 for p in PIECE_ORDER}
    total_pieces = 0

    for char in board_part:
        if char.isalpha():
            total_pieces += 1
            upper = char.upper()
            if upper in white_counts:
                if char.isupper():
                    white_counts[upper] += 1
                else:
                    black_counts[upper] += 1

    def format_side(counts: dict[str, int]) -> str:
        tokens = ["K"]
        for piece in PIECE_ORDER:
            cnt = counts[piece]
            if cnt == 1:
                tokens.append(piece)
            elif cnt > 1:
                tokens.append(f"{cnt}{piece}")
        return "".join(tokens)

    white_sig = format_side(white_counts)
    black_sig = format_side(black_counts)

    if len(white_sig) >= len(black_sig):
        material_sig = f"{white_sig}v{black_sig}"
    else:
        material_sig = f"{black_sig}v{white_sig}"

    return turn_color, total_pieces, material_sig


def load_chessgame_graph(
    pg_engine: Engine,
    neo4j_driver: Driver,
    blunder_threshold_cp: int = 100,
    endgame_max_pieces: int = 7,
    batch_size: int = 1000,
) -> dict[str, int]:
    """
    Read games and Stockfish-evaluated game_moves from PostgreSQL and sync them
    into Neo4j with explicit moved_piece properties on nodes and relationships.
    """
    games_sql = text(
        """
        SELECT
            game_id, game_type::TEXT AS game_type, played_date,
            user_color, user_elo, opponent_elo, user_outcome,
            result::TEXT AS result, eco_code, opening_name, total_plies
        FROM games
        ORDER BY game_id;
        """
    )

    aggregated_moves_sql = text(
        """
        SELECT
            gm.fen_before_norm,
            gm.fen_after_norm,
            gm.uci_move,
            MIN(gm.san_move) AS san_move,
            COUNT(*) AS total_games,
            SUM(CASE WHEN g.user_outcome = 'win' THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN g.user_outcome = 'loss' THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN g.user_outcome = 'draw' THEN 1 ELSE 0 END) AS draws,
            ROUND(
                100.0 * SUM(CASE WHEN g.user_outcome = 'win' THEN 1 ELSE 0 END) / COUNT(*),
                1
            )::FLOAT AS win_rate_pct,
            ROUND(AVG(gm.cp_loss))::INTEGER AS avg_cp_loss,
            ROUND(AVG(gm.clock_rem_sec), 1)::FLOAT AS avg_clock_sec,
            ROUND(AVG(gm.eval_cp_before))::INTEGER AS avg_eval_before,
            ROUND(AVG(gm.eval_cp_after))::INTEGER AS avg_eval_after,
            MAX(gm.best_move_uci) AS best_move_uci
        FROM game_moves gm
        JOIN games g ON gm.game_id = g.game_id
        GROUP BY gm.fen_before_norm, gm.fen_after_norm, gm.uci_move;
        """
    )

    blunders_sql = text(
        """
        SELECT
            gm.game_id,
            gm.ply_number,
            gm.fen_before_norm,
            gm.san_move,
            gm.uci_move,
            gm.best_move_uci,
            gm.cp_loss,
            gm.clock_rem_sec::FLOAT AS clock_rem_sec
        FROM game_moves gm
        JOIN games g ON gm.game_id = g.game_id
        WHERE gm.cp_loss >= :blunder_threshold
          AND (
              (g.user_color = 'white' AND gm.turn_color = 'w')
              OR (g.user_color = 'black' AND gm.turn_color = 'b')
          );
        """
    )

    with pg_engine.connect() as conn:
        game_rows = [dict(r) for r in conn.execute(games_sql).mappings().all()]
        move_rows = [dict(r) for r in conn.execute(aggregated_moves_sql).mappings().all()]
        blunder_rows = [
            dict(r)
            for r in conn.execute(
                blunders_sql, {"blunder_threshold": blunder_threshold_cp}
            ).mappings().all()
        ]

    endgame_links: dict[str, dict[str, str]] = {}

    for row in move_rows:
        turn_b, pieces_b, mat_b = extract_board_signature(row["fen_before_norm"])
        turn_a, pieces_a, mat_a = extract_board_signature(row["fen_after_norm"])
        moved_piece, from_sq, to_sq, is_cap = extract_move_metadata(
            row["san_move"], row["uci_move"]
        )

        row["turn_before"] = turn_b
        row["pieces_before"] = pieces_b
        row["material_before"] = mat_b
        row["turn_after"] = turn_a
        row["pieces_after"] = pieces_a
        row["material_after"] = mat_a
        row["moved_piece"] = moved_piece
        row["from_square"] = from_sq
        row["to_square"] = to_sq
        row["is_capture"] = is_cap

        if pieces_a <= endgame_max_pieces:
            endgame_links[row["fen_after_norm"]] = {
                "fen_norm": row["fen_after_norm"],
                "material_sig": mat_a,
            }

    for b_row in blunder_rows:
        moved_piece, _, _, _ = extract_move_metadata(
            b_row["san_move"], b_row["uci_move"]
        )
        b_row["moved_piece"] = moved_piece

    endgame_link_records = list(endgame_links.values())

    with neo4j_driver.session() as session:
        for idx in range(0, len(game_rows), batch_size):
            session.run(MERGE_GAMES_CYPHER, batch=game_rows[idx : idx + batch_size])

        for idx in range(0, len(move_rows), batch_size):
            session.run(MERGE_PLAYED_MOVES_CYPHER, batch=move_rows[idx : idx + batch_size])

        for idx in range(0, len(endgame_link_records), batch_size):
            session.run(
                LINK_ENDGAME_TRANSITIONS_CYPHER,
                batch=endgame_link_records[idx : idx + batch_size],
            )

        for idx in range(0, len(blunder_rows), batch_size):
            session.run(
                LINK_BLUNDERS_TO_GAMES_CYPHER,
                batch=blunder_rows[idx : idx + batch_size],
            )

    summary = {
        "games": len(game_rows),
        "played_move_edges": len(move_rows),
        "endgame_links": len(endgame_link_records),
        "blunder_links": len(blunder_rows),
    }
    logger.info("Synced PostgreSQL games & moves into Neo4j: %s", summary)
    return summary