from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager
from typing import Any

import pytest
from neo4j import READ_ACCESS

from chess_mcp.config import Neo4jSettings
from chess_mcp.neo4j.models import (
    EndgameContext,
    GameBlunders,
    PositionContext,
    PositionMoves,
    RecurringBlunders,
    TranspositionResult,
)
from chess_mcp.neo4j.repository import Neo4jRepository


START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"
START_FEN_FULL = f"{START_FEN} 0 1"


class FakeRecord(dict[str, Any]):
    def data(self) -> dict[str, Any]:
        return dict(self)


class FakeTransaction:
    def __init__(
        self,
        rows: list[dict[str, Any]],
        calls: list[tuple[str, dict[str, Any]]],
    ) -> None:
        self._rows = rows
        self._calls = calls

    def run(
        self,
        query: str,
        parameters: dict[str, Any],
    ) -> Iterator[FakeRecord]:
        self._calls.append((query, parameters))
        return iter(FakeRecord(row) for row in self._rows)


class FakeSession(AbstractContextManager["FakeSession"]):
    def __init__(
        self,
        rows: list[dict[str, Any]],
        calls: list[tuple[str, dict[str, Any]]],
    ) -> None:
        self._rows = rows
        self._calls = calls
        self.execute_read_called = False

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute_read(self, work: Any) -> list[dict[str, Any]]:
        self.execute_read_called = True
        return work(FakeTransaction(self._rows, self._calls))


class FakeDriver:
    def __init__(self, responses: list[list[dict[str, Any]]]) -> None:
        self._responses = iter(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.session_kwargs: list[dict[str, Any]] = []
        self.sessions: list[FakeSession] = []
        self.closed = False

    def session(self, **kwargs: Any) -> FakeSession:
        self.session_kwargs.append(kwargs)
        session = FakeSession(next(self._responses), self.calls)
        self.sessions.append(session)
        return session

    def close(self) -> None:
        self.closed = True


def settings() -> Neo4jSettings:
    return Neo4jSettings(
        uri="bolt://unused",
        user="neo4j",
        password="secret",
        database="chess",
        max_results=500,
        max_path_depth=20,
    )


def position(fen: str = START_FEN) -> dict[str, Any]:
    return {"fen_norm": fen, "visit_count": 3}


def test_position_context_normalizes_fen_and_uses_read_transaction() -> None:
    driver = FakeDriver(
        [
            [
                {
                    "position": position(),
                    "openings": [
                        {
                            "epd_norm": START_FEN,
                            "eco_code": "A00",
                            "opening_name": "Start",
                        }
                    ],
                    "endgame_patterns": [],
                }
            ]
        ]
    )
    repository = Neo4jRepository(driver, settings())  # type: ignore[arg-type]

    result = repository.get_position_context(START_FEN_FULL)

    assert isinstance(result, PositionContext)
    assert result.position.fen_norm == START_FEN
    assert result.openings[0].eco_code == "A00"
    assert driver.calls[0][1] == {"fen_norm": START_FEN}
    assert driver.session_kwargs == [
        {"database": "chess", "default_access_mode": READ_ACCESS}
    ]
    assert driver.sessions[0].execute_read_called


def test_position_moves_caps_limit_at_one_hundred() -> None:
    driver = FakeDriver(
        [
            [
                {
                    "relationship": "PLAYED_MOVE",
                    "move": {"uci_move": "e2e4", "san_move": "e4"},
                    "target": position(
                        "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -"
                    ),
                }
            ]
        ]
    )
    repository = Neo4jRepository(driver, settings())  # type: ignore[arg-type]

    result = repository.get_position_moves(START_FEN, limit=999)

    assert isinstance(result, PositionMoves)
    assert result.moves[0].uci_move == "e2e4"
    assert driver.calls[0][1]["limit"] == 100


def test_transposition_depth_is_whitelisted_before_interpolation() -> None:
    driver = FakeDriver(
        [
            [
                {
                    "source_fen": START_FEN,
                    "target_fen": START_FEN,
                    "depth": 2,
                    "moves": [
                        {
                            "relationship": "THEORY_MOVE",
                            "uci_move": "g1f3",
                            "san_move": "Nf3",
                        }
                    ],
                }
            ]
        ]
    )
    repository = Neo4jRepository(driver, settings())  # type: ignore[arg-type]

    result = repository.find_transpositions(START_FEN, max_depth=99, limit=999)

    query, parameters = driver.calls[0]
    assert isinstance(result, TranspositionResult)
    assert result.max_depth == 4
    assert "*1..4" in query
    assert "99" not in query
    assert parameters == {"fen_norm": START_FEN, "limit": 100}


def test_game_blunders_returns_typed_events() -> None:
    driver = FakeDriver(
        [
            [
                {
                    "position": position(),
                    "game": {"game_id": 7, "result": "0-1"},
                    "blunder": {
                        "ply_number": 14,
                        "played_uci": "f2f3",
                        "cp_loss": 250,
                    },
                }
            ]
        ]
    )
    repository = Neo4jRepository(driver, settings())  # type: ignore[arg-type]

    result = repository.get_game_blunders(7)

    assert isinstance(result, GameBlunders)
    assert result.blunders[0].cp_loss == 250
    assert driver.calls[0][1]["game_id"] == 7


def test_recurring_blunders_rejects_non_recurring_threshold() -> None:
    repository = Neo4jRepository(FakeDriver([]), settings())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="at least 2"):
        repository.get_recurring_blunder_positions(min_occurrences=1)


def test_recurring_blunders_and_endgame_context_are_typed() -> None:
    driver = FakeDriver(
        [
            [
                {
                    "position": position(),
                    "occurrences": 4,
                    "games": 3,
                    "average_cp_loss": 180.5,
                    "max_cp_loss": 300,
                    "game_ids": [1, 2, 3],
                }
            ],
            [
                {
                    "position": position(),
                    "patterns": [
                        {
                            "endgame_type": "KRvK",
                            "benchmark_positions": 8,
                        }
                    ],
                    "benchmarks": [
                        {
                            "position": position(),
                            "benchmark_move_uci": "a1a8",
                        }
                    ],
                }
            ],
        ]
    )
    repository = Neo4jRepository(driver, settings())  # type: ignore[arg-type]

    recurring = repository.get_recurring_blunder_positions()
    endgame = repository.get_endgame_context(START_FEN)

    assert isinstance(recurring, RecurringBlunders)
    assert recurring.positions[0].occurrences == 4
    assert isinstance(endgame, EndgameContext)
    assert endgame.patterns[0].endgame_type == "KRvK"


def test_missing_position_is_reported() -> None:
    repository = Neo4jRepository(FakeDriver([[]]), settings())  # type: ignore[arg-type]

    with pytest.raises(LookupError, match="not present"):
        repository.get_position_context(START_FEN)
