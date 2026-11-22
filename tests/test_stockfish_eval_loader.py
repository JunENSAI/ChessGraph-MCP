"""Stockfish backfill (etl/postgres_db/load_stockfish_eval.py) with a fake searcher."""

from __future__ import annotations

import chess
import pytest

from etl.postgres_db.load_stockfish_eval import (
    MATE_SCORE,
    ReplayError,
    evaluate_moves,
    stockfish_searcher,
)


def scripted(scores: list[int | None], best: list[str | None] | None = None):
    """A searcher that returns White-POV scores in call order."""
    calls: list[str] = []

    def search(board: chess.Board) -> tuple[int | None, str | None]:
        index = len(calls)
        calls.append(board.fen())
        return scores[index], (best[index] if best else None)

    search.calls = calls  # type: ignore[attr-defined]
    return search


def test_scores_are_stored_from_the_movers_side_with_n_plus_one_searches() -> None:
    # White-POV scores at plies 0..3.
    search = scripted([30, 20, 250, 260], best=["e2e4", "d7d5", "g1f3", None])
    evals = evaluate_moves(["e2e4", "e7e5", "g1f3"], search)

    assert len(search.calls) == 4  # type: ignore[attr-defined]
    white_1, black_2, white_3 = evals
    assert (white_1.eval_before, white_1.eval_after, white_1.cp_loss) == (30, 20, 10)
    # Black's move: signs flip; -20 -> -250 is a 230 cp loss for Black.
    assert (black_2.eval_before, black_2.eval_after, black_2.cp_loss) == (-20, -250, 230)
    # A gain is never a negative loss.
    assert (white_3.eval_before, white_3.eval_after, white_3.cp_loss) == (250, 260, 0)
    assert [e.best_move for e in evals] == ["e2e4", "d7d5", "g1f3"]
    assert [e.ply_number for e in evals] == [1, 2, 3]


def test_a_missing_score_leaves_the_loss_unknown() -> None:
    evals = evaluate_moves(["e2e4"], scripted([None, 20]))
    assert evals[0].eval_before is None and evals[0].cp_loss is None


@pytest.mark.parametrize("line", [["e2e5"], ["e2e4", "zz"]])
def test_illegal_or_malformed_moves_raise_replay_error(line: list[str]) -> None:
    with pytest.raises(ReplayError, match="ply"):
        evaluate_moves(line, scripted([0, 0, 0]))


class NoEngine:
    def analyse(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("game-over positions must not be searched")


def test_game_over_positions_are_scored_without_a_search() -> None:
    search = stockfish_searcher(NoEngine(), depth=1)  # type: ignore[arg-type]
    mated = chess.Board()
    for move in ["f2f3", "e7e5", "g2g4", "d8h4"]:
        mated.push_uci(move)
    assert search(mated) == (-MATE_SCORE, None)
    stalemate = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert search(stalemate) == (0, None)


def test_unreplayable_games_are_skipped_once_and_the_loop_ends() -> None:
    from sqlalchemy import create_engine, text

    from etl.postgres_db.load_stockfish_eval import evaluate_all_games

    db = create_engine("sqlite://")
    with db.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE game_moves (game_id INTEGER, ply_number INTEGER, uci_move TEXT, "
                "eval_cp_before INTEGER, eval_cp_after INTEGER, cp_loss INTEGER, best_move_uci TEXT)"
            )
        )
        rows = [
            (1, 1, "e2e4"), (1, 2, "e7e5"),  # legal
            (2, 1, "e2e5"),                  # illegal: must be skipped, not re-selected forever
            (3, 1, "e2e4"), (3, 3, "g1f3"),  # gap in ply numbers
        ]
        conn.execute(
            text("INSERT INTO game_moves (game_id, ply_number, uci_move) VALUES (:g, :p, :u)"),
            [{"g": g, "p": p, "u": u} for g, p, u in rows],
        )

    written, skipped = evaluate_all_games(db, lambda board: (10, "a2a3"), batch_size=1)

    assert written == 2
    assert skipped == [2, 3]
    with db.connect() as conn:
        stored = conn.execute(text("SELECT ply_number, eval_cp_before, eval_cp_after, cp_loss FROM game_moves WHERE game_id = 1 ORDER BY ply_number")).all()
    assert [tuple(row) for row in stored] == [(1, 10, 10, 0), (2, -10, -10, 0)]
