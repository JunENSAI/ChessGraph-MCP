from __future__ import annotations

from unittest.mock import Mock

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from chess_mcp.stockfish.server import create_server


def _tools(app: object) -> dict[str, object]:
    manager = getattr(app, "_tool_manager")
    return {tool.name: tool for tool in manager.list_tools()}


def test_server_registers_only_curated_read_only_structured_tools() -> None:
    app = create_server(Mock())
    tools = _tools(app)

    assert set(tools) == {"analyze_position", "compare_move", "validate_line"}
    assert all(tool.annotations.read_only_hint for tool in tools.values())  # type: ignore[union-attr]
    assert all(not tool.annotations.destructive_hint for tool in tools.values())  # type: ignore[union-attr]
    assert all(tool.output_schema is not None for tool in tools.values())  # type: ignore[union-attr]


def test_tool_delegates_to_injected_service() -> None:
    service = Mock()
    expected = Mock()
    service.compare_move.return_value = expected
    tool = _tools(create_server(service))["compare_move"]

    result = tool.fn(  # type: ignore[union-attr]
        "some-fen",
        "e2e4",
        limit_type="nodes",
        limit_value=100,
    )

    assert result is expected
    service.compare_move.assert_called_once_with(
        "some-fen",
        "e2e4",
        limit_type="nodes",
        limit_value=100,
    )


def test_validation_errors_are_exposed_as_tool_errors() -> None:
    service = Mock()
    service.validate_line.side_effect = ValueError("illegal move")
    tool = _tools(create_server(service))["validate_line"]

    with pytest.raises(ToolError, match="illegal move"):
        tool.fn("some-fen", ["e2e5"])  # type: ignore[union-attr]
