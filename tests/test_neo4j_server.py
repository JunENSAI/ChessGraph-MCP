from __future__ import annotations

from unittest.mock import Mock

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from chess_mcp.neo4j.models import Position, PositionContext
from chess_mcp.neo4j.server import GRAPH_SCHEMA_RESOURCE, create_server


FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"


def _tools(app: object) -> dict[str, object]:
    manager = getattr(app, "_tool_manager")
    return {tool.name: tool for tool in manager.list_tools()}


def test_server_registers_only_curated_read_only_tools() -> None:
    app = create_server(Mock())
    tools = _tools(app)

    assert set(tools) == {
        "get_position_context",
        "get_position_moves",
        "find_transpositions",
        "get_game_blunders",
        "get_recurring_blunder_positions",
        "get_endgame_context",
        "get_games_through_position",
        "get_theory_exits",
    }
    assert all(tool.annotations.read_only_hint for tool in tools.values())  # type: ignore[union-attr]
    assert all(not tool.annotations.destructive_hint for tool in tools.values())  # type: ignore[union-attr]
    assert all(tool.fn_metadata.output_schema for tool in tools.values())  # type: ignore[union-attr]


def test_tool_delegates_to_injected_repository() -> None:
    repository = Mock()
    expected = PositionContext(position=Position(fen_norm=FEN))
    repository.get_position_context.return_value = expected
    tool = _tools(create_server(repository))["get_position_context"]

    result = tool.fn(FEN)  # type: ignore[union-attr]

    assert result == expected
    repository.get_position_context.assert_called_once_with(FEN)


def test_validation_errors_are_exposed_as_tool_errors() -> None:
    repository = Mock()
    repository.get_position_moves.side_effect = ValueError("limit must be at least 1")
    tool = _tools(create_server(repository))["get_position_moves"]

    with pytest.raises(ToolError, match="limit must be at least 1"):
        tool.fn(FEN, 0)  # type: ignore[union-attr]


def test_schema_resource_documents_v2_semantics() -> None:
    for text in (
        "schema v2",
        "PLAYED_MOVE {uci_move, by}",
        "mover's",
        "side to move",
        "MISTAKE_IN",
        "REACHED",
        "LEFT_THEORY_AT",
        "White first",
        "no clock",
    ):
        assert text in GRAPH_SCHEMA_RESOURCE, text
    assert "BLUNDERED_IN" not in GRAPH_SCHEMA_RESOURCE
    assert "visit_count" not in GRAPH_SCHEMA_RESOURCE


def test_new_tools_delegate_with_their_filters() -> None:
    repository = Mock()
    tools = _tools(create_server(repository))
    tools["get_theory_exits"].fn(5, "all")  # type: ignore[union-attr]
    tools["get_game_blunders"].fn(3, 10, "blunder")  # type: ignore[union-attr]
    repository.get_theory_exits.assert_called_once_with(5, "all")
    repository.get_game_blunders.assert_called_once_with(3, 10, "blunder")
