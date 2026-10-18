from __future__ import annotations

import chess
import chess.engine
import pytest

from chess_mcp.stockfish.models import EvaluationScore
from chess_mcp.stockfish.scoring import (
    analysis_line_from_info,
    centipawn_loss,
    normalize_score,
    normalize_wdl,
    replay_pv,
)


def test_score_is_normalized_to_root_player_without_mate_conversion() -> None:
    cp = chess.engine.PovScore(chess.engine.Cp(42), chess.WHITE)
    mate = chess.engine.PovScore(chess.engine.Mate(3), chess.BLACK)

    assert normalize_score(cp, chess.BLACK) == EvaluationScore(type="cp", value=-42)
    assert normalize_score(mate, chess.BLACK) == EvaluationScore(
        type="mate",
        value=3,
    )
    assert normalize_score(mate, chess.WHITE) == EvaluationScore(
        type="mate",
        value=-3,
    )


def test_wdl_is_normalized_to_root_player() -> None:
    wdl = chess.engine.PovWdl(
        chess.engine.Wdl(wins=600, draws=300, losses=100),
        chess.WHITE,
    )

    normalized = normalize_wdl(wdl, chess.BLACK)

    assert normalized is not None
    assert normalized.model_dump() == {"wins": 100, "draws": 300, "losses": 600}


def test_pv_replay_returns_matching_uci_and_san() -> None:
    board = chess.Board()
    moves = [
        chess.Move.from_uci("e2e4"),
        chess.Move.from_uci("e7e5"),
        chess.Move.from_uci("g1f3"),
    ]

    pv = replay_pv(board, moves)

    assert pv.uci == ["e2e4", "e7e5", "g1f3"]
    assert pv.san == ["e4", "e5", "Nf3"]


def test_pv_replay_rejects_illegal_engine_line() -> None:
    board = chess.Board()

    with pytest.raises(ValueError, match="illegal PV move at ply 2"):
        replay_pv(
            board,
            [
                chess.Move.from_uci("e2e4"),
                chess.Move.from_uci("e2e3"),
            ],
        )


def test_analysis_line_preserves_engine_score_wdl_and_provenance() -> None:
    board = chess.Board()
    info = {
        "score": chess.engine.PovScore(chess.engine.Cp(31), chess.WHITE),
        "wdl": chess.engine.PovWdl(
            chess.engine.Wdl(wins=200, draws=700, losses=100),
            chess.WHITE,
        ),
        "pv": [chess.Move.from_uci("e2e4"), chess.Move.from_uci("e7e5")],
        "depth": 14,
        "seldepth": 21,
        "nodes": 12_345,
        "time": 0.125,
    }

    line = analysis_line_from_info(
        board,
        info,
        engine_id={"name": "Stockfish 18", "author": "the Stockfish developers"},
    )

    assert line.move_uci == "e2e4"
    assert line.move_san == "e4"
    assert line.score == EvaluationScore(type="cp", value=31)
    assert line.wdl is not None and line.wdl.draws == 700
    assert line.engine.name == "Stockfish 18"
    assert line.engine.depth == 14
    assert line.engine.seldepth == 21
    assert line.engine.nodes == 12_345
    assert line.engine.time_ms == 125


def test_centipawn_loss_exists_only_for_two_cp_scores() -> None:
    best = EvaluationScore(type="cp", value=80)
    played = EvaluationScore(type="cp", value=15)
    mate = EvaluationScore(type="mate", value=4)

    assert centipawn_loss(best, played) == 65
    assert centipawn_loss(played, best) == 0
    assert centipawn_loss(mate, played) is None
