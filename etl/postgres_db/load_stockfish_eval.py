import logging
import os
import sys
from pathlib import Path

import chess
import chess.engine
from dotenv import find_dotenv, load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))

load_dotenv(find_dotenv(usecwd=True) or find_dotenv())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("load_stockfish_eval")

DB_USER = os.getenv("POSTGRES_USER", "user_name")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "user_password")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "db_name")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "/usr/games/stockfish")
SEARCH_DEPTH = int(os.getenv("STOCKFISH_DEPTH", "15"))
BATCH_SIZE = 50


def evaluate_all_games(engine_conn, stockfish_binary: str, depth: int) -> int:
    """Iterate through all unevaluated games in batches until complete."""
    if not Path(stockfish_binary).exists():
        logger.error("Stockfish binary not found at %s", stockfish_binary)
        return 0

    logger.info("Initializing Stockfish from %s (Depth: %d)", stockfish_binary, depth)

    try:
        sf_engine = chess.engine.SimpleEngine.popen_uci(stockfish_binary)
    except Exception as e:
        logger.error("Failed to start Stockfish process: %s", e)
        return 0

    fetch_query = text(
        """
        SELECT DISTINCT g.game_id, g.pgn_moves_raw
        FROM games g
        JOIN game_moves m ON g.game_id = m.game_id
        WHERE m.eval_cp_before IS NULL
        LIMIT :batch_size;
    """
    )

    update_move_sql = text(
        """
        UPDATE game_moves
        SET eval_cp_before = :eval_before,
            eval_cp_after = :eval_after,
            cp_loss = :cp_loss,
            best_move_uci = :best_move
        WHERE game_id = :game_id AND ply_number = :ply_number;
    """
    )

    total_evaluated_moves = 0
    batch_count = 0

    while True:
        with engine_conn.begin() as conn:
            games_batch = conn.execute(
                fetch_query, {"batch_size": BATCH_SIZE}
            ).fetchall()

        if not games_batch:
            break

        batch_count += 1
        logger.info("Processing batch %d (%d games)...", batch_count, len(games_batch))

        for game_id, pgn_moves_raw in games_batch:
            board = chess.Board()
            move_tokens = [
                token
                for token in pgn_moves_raw.split()
                if not token.endswith(".")
                and token not in ("1-0", "0-1", "1/2-1/2", "*")
            ]

            ply = 0
            game_moves_updated = 0

            for san_token in move_tokens:
                try:
                    move = board.parse_san(san_token)
                except ValueError:
                    break

                ply += 1

                info_before = sf_engine.analyse(board, chess.engine.Limit(depth=depth))
                score_before = info_before["score"].white().score(mate_score=10000)
                best_move = info_before.get("pv")
                best_move_uci = best_move[0].uci() if best_move else None

                board.push(move)
                info_after = sf_engine.analyse(board, chess.engine.Limit(depth=depth))
                score_after = info_after["score"].white().score(mate_score=10000)

                if board.turn == chess.BLACK:
                    cp_loss = max(0, score_before - score_after)
                    eval_cp_b = score_before
                    eval_cp_a = score_after
                else:
                    cp_loss = max(0, score_after - score_before)
                    eval_cp_b = -score_before if score_before is not None else None
                    eval_cp_a = -score_after if score_after is not None else None

                with engine_conn.begin() as conn:
                    conn.execute(
                        update_move_sql,
                        {
                            "game_id": game_id,
                            "ply_number": ply,
                            "eval_before": eval_cp_b,
                            "eval_after": eval_cp_a,
                            "cp_loss": cp_loss,
                            "best_move": best_move_uci,
                        },
                    )
                game_moves_updated += 1

            total_evaluated_moves += game_moves_updated
            logger.info("Evaluated game_id %s (%d moves)", game_id, game_moves_updated)

    sf_engine.quit()
    logger.info("Evaluation complete! Total moves evaluated: %d", total_evaluated_moves)
    return total_evaluated_moves


if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)
    evaluate_all_games(
        engine_conn=engine, stockfish_binary=STOCKFISH_PATH, depth=SEARCH_DEPTH
    )