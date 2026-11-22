"""Backfill Stockfish evaluations for stored moves that have none.

For every game with at least one unevaluated move, the stored UCI moves are
replayed from the start position. Each position is searched once at
``STOCKFISH_DEPTH``. The score of position *n + 1* is the "after" score of
move *n*, so a game of N plies costs N + 1 searches, not 2N.

Stored values keep the original convention:

- ``eval_cp_before`` and ``eval_cp_after`` are from the **mover's** point of
  view, so ``eval_cp_before`` is from the side to move at ``fen_before_norm``;
- mate scores are flattened to +/-10000;
- ``cp_loss = max(0, eval_cp_before - eval_cp_after)``;
- ``best_move_uci`` is the first move of the principal variation before the move.

A game whose stored moves cannot be replayed is logged and skipped for the
rest of the run, so it can never be selected again in an endless loop. Each
game is written in one transaction.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.engine
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import Engine

from chess_mcp.config import get_int_setting, get_setting, postgres_url

logger = logging.getLogger("load_stockfish_eval")

STOCKFISH_PATH = get_setting("STOCKFISH_PATH", "/usr/games/stockfish")
SEARCH_DEPTH = get_int_setting("STOCKFISH_DEPTH", 10)
BATCH_SIZE = 50
MATE_SCORE = 10_000

# (score from White's point of view, best move in UCI or None) for one position.
Searcher = Callable[[chess.Board], tuple[int | None, str | None]]


@dataclass(frozen=True)
class MoveEval:
    ply_number: int
    eval_before: int | None
    eval_after: int | None
    cp_loss: int | None
    best_move: str | None


class ReplayError(ValueError):
    """The stored moves of a game are not legal from the start position."""


def evaluate_moves(moves_uci: Sequence[str], search: Searcher) -> list[MoveEval]:
    """Evaluate one game's moves in order. Raises ReplayError on an illegal move."""
    board = chess.Board()
    positions: list[tuple[int | None, str | None]] = [search(board)]
    for ply, token in enumerate(moves_uci, start=1):
        try:
            move = chess.Move.from_uci(token)
        except ValueError as exc:
            raise ReplayError(f"ply {ply}: invalid UCI {token!r}") from exc
        if move not in board.legal_moves:
            raise ReplayError(f"ply {ply}: illegal move {token}")
        board.push(move)
        positions.append(search(board))

    results: list[MoveEval] = []
    for ply in range(1, len(moves_uci) + 1):
        white_before, best = positions[ply - 1]
        white_after, _ = positions[ply]
        # Odd plies are White's moves, even plies Black's.
        sign = 1 if ply % 2 == 1 else -1
        before = None if white_before is None else sign * white_before
        after = None if white_after is None else sign * white_after
        loss = None if before is None or after is None else max(0, before - after)
        results.append(MoveEval(ply, before, after, loss, best))
    return results


def stockfish_searcher(engine: chess.engine.SimpleEngine, depth: int) -> Searcher:
    def search(board: chess.Board) -> tuple[int | None, str | None]:
        if board.is_game_over():
            outcome = board.outcome()
            if outcome is not None and outcome.winner is not None:
                return (MATE_SCORE if outcome.winner == chess.WHITE else -MATE_SCORE), None
            return 0, None
        info = engine.analyse(board, chess.engine.Limit(depth=depth))
        score = info["score"].white().score(mate_score=MATE_SCORE)
        pv = info.get("pv")
        return score, (pv[0].uci() if pv else None)

    return search


FETCH_GAMES = text(
    """
    SELECT DISTINCT game_id
    FROM game_moves
    WHERE eval_cp_before IS NULL
      AND game_id NOT IN :skipped
    ORDER BY game_id
    LIMIT :batch_size
    """
).bindparams(bindparam("skipped", expanding=True))

FETCH_MOVES = text(
    "SELECT ply_number, uci_move FROM game_moves WHERE game_id = :game_id ORDER BY ply_number"
)

UPDATE_MOVE = text(
    """
    UPDATE game_moves
    SET eval_cp_before = :eval_before,
        eval_cp_after = :eval_after,
        cp_loss = :cp_loss,
        best_move_uci = :best_move
    WHERE game_id = :game_id AND ply_number = :ply_number
    """
)


def evaluate_all_games(db: Engine, search: Searcher, batch_size: int = BATCH_SIZE) -> tuple[int, list[int]]:
    """Evaluate every game that has unevaluated moves. Returns (moves written, skipped game ids)."""
    skipped: list[int] = []
    written = 0
    while True:
        with db.connect() as conn:
            # An empty expanding list renders invalid SQL, so pad with an impossible id.
            game_ids = [
                row[0]
                for row in conn.execute(FETCH_GAMES, {"skipped": skipped or [-1], "batch_size": batch_size})
            ]
        if not game_ids:
            return written, skipped
        for game_id in game_ids:
            with db.connect() as conn:
                rows = conn.execute(FETCH_MOVES, {"game_id": game_id}).all()
            plies = [row[0] for row in rows]
            if plies != list(range(1, len(plies) + 1)):
                logger.warning("game %s: ply numbers are not contiguous; skipped", game_id)
                skipped.append(game_id)
                continue
            try:
                evals = evaluate_moves([row[1] for row in rows], search)
            except ReplayError as exc:
                logger.warning("game %s: %s; skipped", game_id, exc)
                skipped.append(game_id)
                continue
            with db.begin() as conn:
                conn.execute(
                    UPDATE_MOVE,
                    [
                        {
                            "game_id": game_id,
                            "ply_number": item.ply_number,
                            "eval_before": item.eval_before,
                            "eval_after": item.eval_after,
                            "cp_loss": item.cp_loss,
                            "best_move": item.best_move,
                        }
                        for item in evals
                    ],
                )
            written += len(evals)
            logger.info("game %s: %d moves evaluated", game_id, len(evals))


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    if not Path(STOCKFISH_PATH).exists():
        logger.error("Stockfish binary not found at %s", STOCKFISH_PATH)
        return 1
    db = create_engine(postgres_url())
    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
    try:
        written, skipped = evaluate_all_games(db, stockfish_searcher(engine, SEARCH_DEPTH))
    finally:
        engine.quit()
        db.dispose()
    logger.info("Done: %d moves evaluated, %d games skipped %s", written, len(skipped), skipped[:20])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
