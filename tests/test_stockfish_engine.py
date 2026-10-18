from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import chess
import chess.engine
import pytest

from chess_mcp.config import StockfishSettings
from chess_mcp.stockfish.engine import (
    StockfishEngine,
    StockfishService,
    build_limit,
)


@pytest.fixture
def settings() -> StockfishSettings:
    return StockfishSettings(
        path=Path("/unused/stockfish"),
        default_depth=12,
        max_depth=20,
        max_nodes=50_000,
        max_time_ms=2_000,
        max_multipv=3,
        threads=2,
        hash_mb=64,
    )


class FakeEngine:
    id = {"name": "Stockfish Test", "author": "Test"}
    options = {"Threads": object(), "Hash": object(), "UCI_ShowWDL": object()}

    def __init__(self) -> None:
        self.configured: dict[str, object] | None = None
        self.calls: list[tuple[chess.Board, chess.engine.Limit, dict[str, Any]]] = []
        self.quit_calls = 0

    def configure(self, options: dict[str, object]) -> None:
        self.configured = dict(options)

    def analyse(
        self,
        board: chess.Board,
        limit: chess.engine.Limit,
        **kwargs: Any,
    ) -> chess.engine.InfoDict | list[chess.engine.InfoDict]:
        self.calls.append((board.copy(stack=False), limit, kwargs))
        root_moves = kwargs.get("root_moves")
        if root_moves:
            move = root_moves[0]
            return _info(board, move, 10)
        if kwargs.get("multipv") is not None:
            candidates = [
                chess.Move.from_uci("e2e4"),
                chess.Move.from_uci("d2d4"),
                chess.Move.from_uci("g1f3"),
            ]
            return [
                _info(board, move, 50 - rank * 10, rank=rank)
                for rank, move in enumerate(
                    candidates[: kwargs["multipv"]],
                    start=1,
                )
            ]
        return _info(board, chess.Move.from_uci("e2e4"), 50)

    def quit(self) -> None:
        self.quit_calls += 1


def _info(
    board: chess.Board,
    move: chess.Move,
    cp: int,
    *,
    rank: int = 1,
) -> chess.engine.InfoDict:
    return {
        "score": chess.engine.PovScore(chess.engine.Cp(cp), board.turn),
        "pv": [move],
        "multipv": rank,
        "depth": 12,
        "seldepth": 18,
        "nodes": 1_000,
        "time": 0.05,
    }


def test_engine_is_lazy_persistent_configured_and_closed_once(
    settings: StockfishSettings,
) -> None:
    fake = FakeEngine()
    launches: list[str] = []

    def factory(command: str) -> FakeEngine:
        launches.append(command)
        return fake

    engine = StockfishEngine(
        settings_getter=lambda: settings,
        engine_factory=factory,
    )
    board = chess.Board()

    assert not engine.started
    engine.analyse(board, chess.engine.Limit(depth=1), multipv=1)
    engine.analyse(board, chess.engine.Limit(depth=2), multipv=1)

    assert launches == ["/unused/stockfish"]
    assert fake.configured == {
        "Threads": 2,
        "Hash": 64,
        "UCI_ShowWDL": True,
    }
    engine.close()
    engine.close()
    assert fake.quit_calls == 1


def test_service_analyze_returns_ranked_multipv_without_binary(
    settings: StockfishSettings,
) -> None:
    fake = FakeEngine()
    engine = StockfishEngine(
        settings_getter=lambda: settings,
        engine_factory=lambda _: fake,
    )
    service = StockfishService(engine, settings_getter=lambda: settings)

    result = service.analyze_position(
        chess.STARTING_FEN,
        limit_type="nodes",
        limit_value=2_500,
        multipv=20,
    )

    assert result.limit.model_dump() == {
        "type": "nodes",
        "value": 2_500,
        "unit": "nodes",
    }
    assert result.multipv == 3
    assert [line.move_uci for line in result.lines] == ["e2e4", "d2d4", "g1f3"]
    assert [line.rank for line in result.lines] == [1, 2, 3]
    assert result.lines[0].engine.threads == 2
    assert result.lines[0].engine.hash_mb == 64
    assert result.lines[0].engine.show_wdl is True
    assert fake.calls[0][1].nodes == 2_500


def test_compare_uses_same_root_and_limit_for_best_and_played_move(
    settings: StockfishSettings,
) -> None:
    fake = FakeEngine()
    engine = StockfishEngine(
        settings_getter=lambda: settings,
        engine_factory=lambda _: fake,
    )
    service = StockfishService(engine, settings_getter=lambda: settings)

    result = service.compare_move(
        chess.STARTING_FEN,
        "d2d4",
        limit_type="depth",
        limit_value=15,
    )

    assert len(fake.calls) == 2
    best_call, played_call = fake.calls
    assert best_call[0].fen() == played_call[0].fen() == chess.Board().fen()
    assert best_call[1] is played_call[1]
    assert "root_moves" not in best_call[2]
    assert played_call[2]["root_moves"] == [chess.Move.from_uci("d2d4")]
    assert result.best.move_uci == "e2e4"
    assert result.played.move_uci == "d2d4"
    assert result.centipawn_loss == 40


def test_validate_line_replays_without_starting_engine(
    settings: StockfishSettings,
) -> None:
    fake = FakeEngine()
    engine = StockfishEngine(
        settings_getter=lambda: settings,
        engine_factory=lambda _: fake,
    )
    service = StockfishService(engine, settings_getter=lambda: settings)

    result = service.validate_line(
        chess.STARTING_FEN,
        ["e2e4", "e7e5", "g1f3"],
    )

    assert [move.san for move in result.moves] == ["e4", "e5", "Nf3"]
    assert result.final_fen == result.moves[-1].fen_after
    assert not engine.started


@pytest.mark.parametrize(
    ("limit_type", "limit_value", "bounded_value"),
    [
        ("depth", 21, 20),
        ("nodes", 50_001, 50_000),
        ("time", 2_001, 2_000),
    ],
)
def test_search_limits_clamp_to_configured_bounds(
    settings: StockfishSettings,
    limit_type: Any,
    limit_value: int,
    bounded_value: int,
) -> None:
    _, response_limit = build_limit(settings, limit_type, limit_value)

    assert response_limit.value == bounded_value


def test_nodes_and_time_require_an_explicit_value(
    settings: StockfishSettings,
) -> None:
    with pytest.raises(ValueError, match="limit_value is required"):
        build_limit(settings, "nodes", None)


def test_engine_lock_serializes_analysis(settings: StockfishSettings) -> None:
    class ConcurrentFake(FakeEngine):
        def __init__(self) -> None:
            super().__init__()
            self.active = 0
            self.max_active = 0

        def analyse(
            self,
            board: chess.Board,
            limit: chess.engine.Limit,
            **kwargs: Any,
        ) -> list[chess.engine.InfoDict]:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            time.sleep(0.02)
            self.active -= 1
            return [_info(board, chess.Move.from_uci("e2e4"), 20)]

    fake = ConcurrentFake()
    engine = StockfishEngine(
        settings_getter=lambda: settings,
        engine_factory=lambda _: fake,
    )
    barrier = threading.Barrier(3)

    def search() -> None:
        barrier.wait()
        engine.analyse(chess.Board(), chess.engine.Limit(depth=1), multipv=1)

    threads = [threading.Thread(target=search) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert fake.max_active == 1
