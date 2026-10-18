from __future__ import annotations

import asyncio
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from chess_mcp.postgres.models import PlayerSummary
from chess_mcp.postgres.server import POSTGRES_SCHEMA_RESOURCE, create_server


class FakeRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def list_games(self, **arguments: Any) -> list[Any]:
        self.calls.append(("list_games", arguments))
        return []

    def get_game(self, game_id: int) -> None:
        self.calls.append(("get_game", {"game_id": game_id}))
        return None

    def get_game_moves(
        self,
        game_id: int,
        *,
        start_ply: int,
        limit: int,
    ) -> list[Any]:
        self.calls.append(
            (
                "get_game_moves",
                {"game_id": game_id, "start_ply": start_ply, "limit": limit},
            )
        )
        return []

    def get_player_summary(
        self,
        username: str,
        *,
        game_type: str | None,
    ) -> PlayerSummary:
        self.calls.append(
            (
                "get_player_summary",
                {"username": username, "game_type": game_type},
            )
        )
        return PlayerSummary(
            username=username,
            games_played=0,
            wins=0,
            losses=0,
            draws=0,
            unfinished=0,
        )

    def get_blunders(self, **arguments: Any) -> list[Any]:
        self.calls.append(("get_blunders", arguments))
        return []

    def find_position_occurrences(
        self,
        fen: str,
        *,
        limit: int,
    ) -> tuple[str, list[Any]]:
        self.calls.append(
            ("find_position_occurrences", {"fen": fen, "limit": limit})
        )
        return "8/8/8/8/8/2k5/8/K7 w - -", []

    def lookup_opening(
        self,
        fen: str,
        *,
        limit: int,
    ) -> tuple[str, list[Any]]:
        self.calls.append(("lookup_opening", {"fen": fen, "limit": limit}))
        return "8/8/8/8/8/2k5/8/K7 w - -", []

    def lookup_endgame_positions(
        self,
        **arguments: Any,
    ) -> tuple[str | None, list[Any]]:
        self.calls.append(("lookup_endgame_positions", arguments))
        return arguments["fen"], []


def test_server_registers_only_curated_structured_tools() -> None:
    server = create_server(FakeRepository())  # type: ignore[arg-type]

    tools = asyncio.run(server.list_tools())

    assert {tool.name for tool in tools} == {
        "list_games",
        "get_game",
        "get_game_moves",
        "get_player_summary",
        "get_blunders",
        "find_position_occurrences",
        "lookup_opening",
        "lookup_endgame_positions",
    }
    assert all(tool.output_schema is not None for tool in tools)
    assert all(tool.annotations.read_only_hint for tool in tools)
    assert all(not tool.annotations.destructive_hint for tool in tools)


def test_list_games_returns_structured_output_from_fake_repository() -> None:
    repository = FakeRepository()
    server = create_server(repository)  # type: ignore[arg-type]

    result = asyncio.run(
        server.call_tool(
            "list_games",
            {"player": " Junior ", "game_type": "rapid", "limit": 12},
        )
    )

    assert result.structured_content == {"games": []}
    assert repository.calls == [
        (
            "list_games",
            {
                "player": "Junior",
                "game_type": "rapid",
                "user_outcome": None,
                "eco_code": None,
                "played_from": None,
                "played_to": None,
                "limit": 12,
            },
        )
    ]


def test_invalid_arguments_are_actionable_tool_errors() -> None:
    server = create_server(FakeRepository())  # type: ignore[arg-type]

    with pytest.raises(ToolError, match="value must be positive"):
        asyncio.run(server.call_tool("get_game", {"game_id": 0}))


def test_repository_failures_do_not_leak_details() -> None:
    repository = FakeRepository()

    def fail(**arguments: Any) -> list[Any]:
        raise RuntimeError("postgresql://user:top-secret@database")

    repository.list_games = fail  # type: ignore[method-assign]
    server = create_server(repository)  # type: ignore[arg-type]

    with pytest.raises(ToolError) as captured:
        asyncio.run(server.call_tool("list_games", {}))

    assert str(captured.value).endswith("PostgreSQL list games failed.")
    assert "top-secret" not in str(captured.value)


def test_static_schema_resource_describes_exact_fen_semantics() -> None:
    server = create_server(FakeRepository())  # type: ignore[arg-type]

    resources = asyncio.run(server.list_resources())
    result = asyncio.run(server.read_resource("chessgraph://postgres/schema"))

    assert len(resources) == 1
    assert str(resources[0].uri) == "chessgraph://postgres/schema"
    assert len(result) == 1
    assert result[0].content == POSTGRES_SCHEMA_RESOURCE
    assert "normalized four-field FEN" in result[0].content
    assert "free-form SQL" in result[0].content
