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
    GamesThroughPosition,
    PositionContext,
    PositionMoves,
    RecurringBlunders,
    StyleContext,
    TheoryExits,
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
    return {"fen_norm": fen, "visit_games": 3, "phase": "opening"}


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


def test_position_moves_caps_limit_and_flattens_v2_rows() -> None:
    target = position("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -")
    driver = FakeDriver(
        [
            [
                {
                    "position": position(),
                    "engine_best": {"uci": "e2e4", "san": "e4", "target": target},
                    "moves": [
                        {
                            "relationship": "PLAYED_MOVE",
                            "move": {"uci_move": "e2e4", "san_move": "e4", "by": "owner", "games": 12, "score_pct": 62.5, "eco_codes": None},
                            "target": target,
                        },
                        {
                            "relationship": "THEORY_MOVE",
                            "move": {"uci_move": "e2e4", "san_move": "e4", "eco_codes": ["B00", "C20"]},
                            "target": target,
                        },
                    ],
                }
            ]
        ]
    )
    repository = Neo4jRepository(driver, settings())  # type: ignore[arg-type]

    result = repository.get_position_moves(START_FEN, limit=999, by="owner")

    assert isinstance(result, PositionMoves)
    assert result.moves[0].by == "owner"
    assert result.moves[0].score_pct == 62.5
    assert result.moves[0].eco_codes == []  # played edges project eco_codes as null
    assert result.moves[1].eco_codes == ["B00", "C20"]
    assert result.engine_best is not None and result.engine_best.san == "e4"
    assert driver.calls[0][1] == {"fen_norm": START_FEN, "limit": 100, "by": "owner"}


def test_position_moves_of_an_unknown_position_is_empty() -> None:
    repository = Neo4jRepository(FakeDriver([[]]), settings())  # type: ignore[arg-type]
    result = repository.get_position_moves(START_FEN)
    assert result.moves == [] and result.position is None


def test_position_moves_rejects_an_unknown_mover_filter() -> None:
    repository = Neo4jRepository(FakeDriver([]), settings())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="by must be one of"):
        repository.get_position_moves(START_FEN, by="everyone")


def test_lookup_key_drops_an_en_passant_square_with_no_legal_capture() -> None:
    driver = FakeDriver([[]])
    repository = Neo4jRepository(driver, settings())  # type: ignore[arg-type]
    repository.get_position_moves("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1")
    assert driver.calls[0][1]["fen_norm"] == "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -"


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


def test_game_blunders_filter_by_severity_and_return_typed_events() -> None:
    driver = FakeDriver(
        [
            [
                {
                    "position": position(),
                    "game": {"game_id": 7, "result": "0-1", "played_date": "2025-03-01"},
                    "mistake": {
                        "ply": 14,
                        "severity": "blunder",
                        "cp_loss": 9600,
                        "mate_swing": True,
                        "played_uci": "f2f3",
                        "best_uci": "g1f3",
                    },
                }
            ]
        ]
    )
    repository = Neo4jRepository(driver, settings())  # type: ignore[arg-type]

    result = repository.get_game_blunders(7, min_severity="blunder")

    assert isinstance(result, GameBlunders)
    assert result.game is not None and result.game.played_date == "2025-03-01"
    assert result.blunders[0].severity == "blunder"
    assert result.blunders[0].mate_swing is True
    assert driver.calls[0][1] == {"game_id": 7, "limit": 100, "min_cp": 300}


def test_game_blunders_rejects_an_unknown_severity() -> None:
    repository = Neo4jRepository(FakeDriver([]), settings())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="min_severity"):
        repository.get_game_blunders(7, min_severity="catastrophe")


def test_games_through_position_summarises_the_owner_score() -> None:
    driver = FakeDriver(
        [
            [
                {
                    "total_games": 3,
                    "owner_wins": 2,
                    "owner_draws": 0,
                    "owner_losses": 1,
                    "games": [{"game": {"game_id": 9, "user_outcome": "win"}, "ply": 6, "owner_to_move": True}],
                }
            ]
        ]
    )
    repository = Neo4jRepository(driver, settings())  # type: ignore[arg-type]

    result = repository.get_games_through_position(START_FEN, limit=1)

    assert isinstance(result, GamesThroughPosition)
    assert (result.total_games, result.owner_wins, result.owner_losses) == (3, 2, 1)
    assert result.games[0].game.game_id == 9
    assert driver.calls[0][1] == {"fen_norm": START_FEN, "limit": 1}


def test_theory_exits_are_typed_and_the_mover_filter_is_checked() -> None:
    driver = FakeDriver(
        [
            [
                {
                    "position": position(),
                    "by": "owner",
                    "played_uci": "g2g3",
                    "played_san": "g3",
                    "ply": 1,
                    "games": 40,
                    "owner_wins": 20,
                    "owner_draws": 5,
                    "owner_losses": 15,
                    "opening": None,
                    "opening_families": ["King's Fianchetto Opening"],
                    "theory_moves": ["e4", "d4"],
                    "book_ended": False,
                }
            ]
        ]
    )
    repository = Neo4jRepository(driver, settings())  # type: ignore[arg-type]

    result = repository.get_theory_exits(limit=5)

    assert isinstance(result, TheoryExits)
    assert result.exits[0].played_san == "g3"
    assert result.exits[0].theory_moves == ["e4", "d4"]
    assert result.exits[0].book_ended is False
    assert "size(theory_moves) = 0 AS book_ended" in driver.calls[0][0]
    assert driver.calls[0][1] == {"limit": 5, "by": "owner"}
    with pytest.raises(ValueError, match="by must be one of"):
        repository.get_theory_exits(by="theory")


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
    assert recurring.min_severity == "mistake"
    assert driver.calls[0][1] == {"min_occurrences": 2, "limit": 20, "min_cp": 100}
    assert isinstance(endgame, EndgameContext)
    assert endgame.patterns[0].endgame_type == "KRvK"


def test_missing_position_is_reported() -> None:
    repository = Neo4jRepository(FakeDriver([[]]), settings())  # type: ignore[arg-type]

    with pytest.raises(LookupError, match="not present"):
        repository.get_position_context(START_FEN)


def test_position_moves_sort_by_games_before_book_moves() -> None:
    from chess_mcp.neo4j.repository import POSITION_MOVES_CYPHER

    order = POSITION_MOVES_CYPHER[POSITION_MOVES_CYPHER.index("ORDER BY") :]
    assert order.index("coalesce(r.games, 0) DESC") < order.index("THEORY_MOVE")
    assert order.index("THEORY_MOVE") < order.index("size(coalesce(r.eco_codes, [])) DESC") < order.index("r.san_move")


def test_style_context_is_one_bounded_read_and_flattens_moves() -> None:
    target = position("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -")
    owner_move = {"uci_move": "e2e4", "san_move": "e4", "by": "owner", "games": 9, "wins": 5, "draws": 2, "losses": 2}
    driver = FakeDriver(
        [
            [
                {
                    "position": position(),
                    "opening": None,
                    "opening_families": [],
                    "owner_moves": [{"relationship": "PLAYED_MOVE", "move": owner_move, "target": target}],
                    "opponent_moves": [],
                    "theory_moves": [
                        {"relationship": "THEORY_MOVE", "move": {"uci_move": "d2d4", "san_move": "d4", "eco_codes": None}, "target": target}
                    ],
                    "total_games": 9,
                    "owner_wins": 5,
                    "owner_draws": 2,
                    "owner_losses": 2,
                    "recent_games": [{"game": {"game_id": 7, "user_outcome": "win"}, "ply": 0, "owner_to_move": True}],
                    "nearby_mistakes": [
                        {"position": target, "distance": 1, "games": 3, "average_cp_loss": 140.5, "max_cp_loss": 300,
                         "played_moves": ["c5"], "best_moves": ["e7e5"]}
                    ],
                }
            ]
        ]
    )
    repository = Neo4jRepository(driver, settings())  # type: ignore[arg-type]

    result = repository.get_style_context(START_FEN_FULL, depth=9, limit=500)

    assert isinstance(result, StyleContext)
    assert result.fen_norm == START_FEN
    assert result.depth == 4  # clamped to MAX_PATH_DEPTH
    assert result.owner_moves[0].san_move == "e4" and result.owner_moves[0].target.fen_norm == target["fen_norm"]
    assert result.theory_moves[0].eco_codes == []
    assert result.recent_games[0].game.game_id == 7
    assert result.nearby_mistakes[0].distance == 1
    query, parameters = driver.calls[0]
    assert parameters == {"fen_norm": START_FEN, "limit": 100}
    assert "PLAYED_MOVE*0..4" in query
    assert not any(word in query.upper() for word in ("MERGE", "CREATE", "SET ", "DELETE"))
    assert driver.session_kwargs == [{"database": "chess", "default_access_mode": READ_ACCESS}]
    assert driver.sessions[0].execute_read_called


def test_style_context_of_an_unknown_position_is_empty() -> None:
    repository = Neo4jRepository(FakeDriver([[]]), settings())  # type: ignore[arg-type]
    result = repository.get_style_context(START_FEN)
    assert result == StyleContext(fen_norm=START_FEN, depth=2)


def test_style_context_rejects_a_depth_below_one() -> None:
    repository = Neo4jRepository(FakeDriver([]), settings())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        repository.get_style_context(START_FEN, depth=0)
