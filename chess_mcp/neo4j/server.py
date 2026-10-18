"""Neo4j MCP server exposing bounded, read-only chess graph tools."""

from __future__ import annotations

from collections.abc import AsyncIterator
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import TypeVar

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from neo4j.exceptions import Neo4jError

from chess_mcp.config import get_neo4j_settings

from .models import (
    EndgameContext,
    GameBlunders,
    PositionContext,
    PositionMoves,
    RecurringBlunders,
    TranspositionResult,
)
from .repository import Neo4jRepository


GRAPH_SCHEMA_RESOURCE = """# ChessGraph Neo4j schema and semantics

This server is read-only. It queries the graph produced by `etl/neo4j_db`.

## Nodes

- `Position`: `fen_norm` (unique four-field FEN), `turn_color`, `piece_count`,
  `material_sig`, `last_moved_piece`, `last_move_san`, `eval_cp`,
  `best_move_uci`, `visit_count`.
- `Opening`: `epd_norm`, `opening_id`, `eco_volume`, `eco_code`,
  `opening_name`, `pgn_line`, `uci_line`.
- `EndgamePattern`: `endgame_type`, `piece_count`, `benchmark_positions`,
  `avg_player_elo`, `sample_fen`, `sample_human_move`.
- `Game`: `game_id`, `game_type`, `played_date`, `user_color`, `user_elo`,
  `opponent_elo`, `user_outcome`, `result`, `eco_code`, `opening_name`,
  `total_plies`.

## Relationships

- `Position-[:PLAYED_MOVE]->Position`: `uci_move`, `san_move`,
  `moved_piece`, `from_square`, `to_square`, `is_capture`, `total_games`,
  `wins`, `losses`, `draws`, `win_rate_pct`, `avg_cp_loss`,
  `avg_clock_sec`, `best_move_uci`.
- `Position-[:THEORY_MOVE]->Position`: `uci_move`, `san_move`,
  `moved_piece`, `from_square`, `to_square`, `is_capture`, `eco_code`.
- `Position-[:CLASSIFIED_AS]->Opening`.
- `Position-[:HAS_ENDGAME_TYPE]->EndgamePattern`: optional
  `benchmark_move_uci`, `elo_tier`, `player_elo`.
- `Position-[:BLUNDERED_IN]->Game`: `ply_number`, `played_san`,
  `played_uci`, `moved_piece`, `best_move_uci`, `cp_loss`, `clock_rem_sec`.

## Important semantics and caveats

- `visit_count` is ETL-derived rather than a transactional graph counter.
  Loaded source positions receive an aggregate game count, while destination
  positions are incremented during loading. Treat it as approximate popularity,
  not a count that is guaranteed to be idempotent across repeated ETL runs.
- `Position.material_sig` and `EndgamePattern.endgame_type` come from different
  pipelines and can differ in orientation or naming. Use `HAS_ENDGAME_TYPE` as
  the authoritative classification; do not assume string equality.
- `BLUNDERED_IN` is merged by its position endpoint, game endpoint, and
  `ply_number`. Different games do not collide; a repeated ETL sync updates the
  same event's relationship properties.
"""

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

ResultT = TypeVar("ResultT")
_default_repository: Neo4jRepository | None = None


def _get_default_repository() -> Neo4jRepository:
    global _default_repository
    if _default_repository is None:
        _default_repository = Neo4jRepository.from_settings(get_neo4j_settings())
    return _default_repository


def _invoke(operation: Callable[[], ResultT]) -> ResultT:
    try:
        return operation()
    except (ValueError, LookupError) as exc:
        raise ToolError(str(exc)) from exc
    except Neo4jError as exc:
        raise ToolError("Neo4j could not complete the read request") from exc


def create_server(repository: Neo4jRepository | None = None) -> MCPServer:
    """Build the server, optionally injecting a repository for tests."""

    @asynccontextmanager
    async def lifespan(_: MCPServer) -> AsyncIterator[None]:
        try:
            yield
        finally:
            global _default_repository
            if repository is None and _default_repository is not None:
                _default_repository.close()
                _default_repository = None

    app = MCPServer(
        name="chessgraph-neo4j",
        title="ChessGraph Neo4j",
        description="Read-only position, move, transposition, blunder, and endgame graph tools.",
        version="0.1.0",
        lifespan=lifespan,
    )

    def repo() -> Neo4jRepository:
        return repository if repository is not None else _get_default_repository()

    @app.tool(annotations=READ_ONLY, structured_output=True)
    def get_position_context(fen: str) -> PositionContext:
        """Get a normalized position with its opening and endgame classifications."""
        return _invoke(lambda: repo().get_position_context(fen))

    @app.tool(annotations=READ_ONLY, structured_output=True)
    def get_position_moves(fen: str, limit: int = 20) -> PositionMoves:
        """List bounded played and theory moves leaving a normalized position."""
        return _invoke(lambda: repo().get_position_moves(fen, limit))

    @app.tool(annotations=READ_ONLY, structured_output=True)
    def find_transpositions(
        fen: str,
        max_depth: int = 3,
        limit: int = 20,
    ) -> TranspositionResult:
        """Find bounded move paths from a position to convergent graph nodes."""
        return _invoke(lambda: repo().find_transpositions(fen, max_depth, limit))

    @app.tool(annotations=READ_ONLY, structured_output=True)
    def get_game_blunders(game_id: int, limit: int = 100) -> GameBlunders:
        """List recorded user blunders for one game in ply order."""
        return _invoke(lambda: repo().get_game_blunders(game_id, limit))

    @app.tool(annotations=READ_ONLY, structured_output=True)
    def get_recurring_blunder_positions(
        min_occurrences: int = 2,
        limit: int = 20,
    ) -> RecurringBlunders:
        """Rank positions linked to blunders in multiple recorded events."""
        return _invoke(
            lambda: repo().get_recurring_blunder_positions(min_occurrences, limit)
        )

    @app.tool(annotations=READ_ONLY, structured_output=True)
    def get_endgame_context(fen: str, limit: int = 20) -> EndgameContext:
        """Get endgame classifications and bounded benchmark positions for a FEN."""
        return _invoke(lambda: repo().get_endgame_context(fen, limit))

    @app.resource(
        "chessgraph-neo4j://schema",
        name="neo4j_graph_schema",
        title="ChessGraph Neo4j schema and semantics",
        description="Static labels, relationships, properties, and ETL caveats.",
        mime_type="text/markdown",
    )
    def graph_schema() -> str:
        return GRAPH_SCHEMA_RESOURCE

    return app


mcp = create_server()


def main() -> None:
    """Run the Neo4j MCP server over standard input/output."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
