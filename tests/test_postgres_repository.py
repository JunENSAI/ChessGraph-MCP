from __future__ import annotations

from contextlib import nullcontext
from typing import Any

from chess_mcp.postgres.repository import PostgresRepository


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> FakeMappings:
        return FakeMappings(self._rows)


class FakeConnection:
    def __init__(self, query_rows: list[dict[str, Any]]) -> None:
        self.query_rows = query_rows
        self.executions: list[tuple[str, dict[str, Any]]] = []
        self.execution_options_used: dict[str, Any] = {}

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execution_options(self, **options: Any) -> FakeConnection:
        self.execution_options_used.update(options)
        return self

    def begin(self) -> nullcontext[None]:
        return nullcontext()

    def execute(self, statement: object, parameters: dict[str, Any]) -> FakeResult:
        sql = str(statement)
        self.executions.append((sql, parameters))
        if "set_config" in sql:
            return FakeResult([])
        return FakeResult(self.query_rows)


class FakeEngine:
    def __init__(self, query_rows: list[dict[str, Any]]) -> None:
        self.connection = FakeConnection(query_rows)
        self.disposed = False

    def connect(self) -> FakeConnection:
        return self.connection

    def dispose(self) -> None:
        self.disposed = True


def test_list_games_is_parameterized_readonly_and_capped() -> None:
    engine = FakeEngine([])
    repository = PostgresRepository(
        engine,  # type: ignore[arg-type]
        statement_timeout_ms=4321,
        max_results=250,
    )
    hostile_player = "x' OR true --"

    assert repository.list_games(player=hostile_player, limit=999) == []

    timeout_sql, timeout_params = engine.connection.executions[0]
    query_sql, query_params = engine.connection.executions[1]
    assert timeout_sql.lstrip().upper().startswith("SELECT")
    assert timeout_params == {"statement_timeout_ms": "4321"}
    assert engine.connection.execution_options_used == {
        "postgresql_readonly": True
    }
    assert hostile_player not in query_sql
    assert ":player" in query_sql
    assert query_params["player"] == hostile_player
    assert query_params["limit"] == 100
    assert "INSERT " not in query_sql.upper()
    assert "UPDATE " not in query_sql.upper()
    assert "DELETE " not in query_sql.upper()


def test_position_lookup_normalizes_fen_and_binds_it() -> None:
    engine = FakeEngine([])
    repository = PostgresRepository(
        engine,  # type: ignore[arg-type]
        statement_timeout_ms=1000,
        max_results=5,
    )
    full_fen = "8/8/8/8/8/2k5/8/K7 w - - 12 40"

    normalized, occurrences = repository.find_position_occurrences(
        full_fen,
        limit=30,
    )

    assert normalized == "8/8/8/8/8/2k5/8/K7 w - -"
    assert occurrences == []
    query_sql, query_params = engine.connection.executions[1]
    assert normalized not in query_sql
    assert query_params == {"fen": normalized, "limit": 5}


def test_game_moves_support_pagination_by_starting_ply() -> None:
    engine = FakeEngine([])
    repository = PostgresRepository(
        engine,  # type: ignore[arg-type]
        statement_timeout_ms=1000,
        max_results=100,
    )

    repository.get_game_moves(7, start_ply=101, limit=50)

    query_sql, query_params = engine.connection.executions[1]
    assert "m.ply_number >= :start_ply" in query_sql
    assert query_params == {"game_id": 7, "start_ply": 101, "limit": 50}


def test_player_summary_maps_aggregate_result() -> None:
    engine = FakeEngine(
        [
            {
                "username": "Junior",
                "games_played": 3,
                "wins": 2,
                "losses": 1,
                "draws": 0,
                "unfinished": 0,
                "average_rating": 1512.5,
                "average_opponent_rating": 1499,
                "earliest_game": None,
                "latest_game": None,
            }
        ]
    )
    repository = PostgresRepository(
        engine,  # type: ignore[arg-type]
        statement_timeout_ms=1000,
        max_results=20,
    )

    summary = repository.get_player_summary("Junior", game_type="rapid")

    assert summary.games_played == 3
    assert summary.wins == 2
    query_sql, query_params = engine.connection.executions[1]
    assert query_sql.lstrip().upper().startswith("WITH")
    assert query_params == {"username": "Junior", "game_type": "rapid"}


def test_default_blunder_query_is_limited_to_data_owner_moves() -> None:
    engine = FakeEngine([])
    repository = PostgresRepository(
        engine,  # type: ignore[arg-type]
        statement_timeout_ms=1000,
        max_results=20,
    )

    repository.get_blunders()

    query_sql, query_params = engine.connection.executions[1]
    assert "g.user_color = 'white' AND m.turn_color = 'w'" in query_sql
    assert "g.user_color = 'black' AND m.turn_color = 'b'" in query_sql
    assert query_params["player"] is None


def test_close_disposes_engine() -> None:
    engine = FakeEngine([])
    repository = PostgresRepository(
        engine,  # type: ignore[arg-type]
        statement_timeout_ms=1000,
        max_results=20,
    )

    repository.close()

    assert engine.disposed is True
