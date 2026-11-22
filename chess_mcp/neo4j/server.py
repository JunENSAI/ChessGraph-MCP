"""Neo4j MCP server exposing bounded, read-only chess graph tools."""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Literal, TypeVar

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from neo4j.exceptions import Neo4jError

from chess_mcp.config import get_neo4j_settings
from chess_mcp.errors import tool_failure

from .models import (
    EndgameContext,
    GameBlunders,
    GamesThroughPosition,
    MoveFilter,
    PositionContext,
    PositionMoves,
    RecurringBlunders,
    Severity,
    TheoryExits,
    TranspositionResult,
)
from .repository import Neo4jRepository


GRAPH_SCHEMA_RESOURCE = """# ChessGraph Neo4j schema v2

This server is read-only. It queries the graph that `etl/neo4j_db/neo4j_load.py`
builds from PostgreSQL. `(:ChessGraphMeta {name: 'chessgraph'})` records
`schema_version: 2`, `loaded_at` and `count_<step>` row counts.

## Nodes

- `Position`: `fen_norm` (unique four-field FEN: placement, side to move,
  castling, en passant), `turn_color`, `piece_count` (kings included),
  `material_sig`, `phase`, `is_theory`, `visit_games`, `eval_cp`,
  `eval_samples`, `best_move_uci`, `best_move_san`.
- `Game`: `game_id`, `game_type`, `played_date` (date), `user_color`,
  `user_elo`, `opponent_elo`, `rating_band`, `user_outcome`, `result`,
  `termination`, `time_control`, `base_time_sec`, `increment_sec`,
  `eco_code`, `opening_name`, `total_plies`.
- `Player`: `username`, `is_owner`. The tools never return usernames.
- `Opening`: `epd_norm`, `opening_id`, `eco_volume`, `eco_code`,
  `opening_name`, `family`, `pgn_line`, `uci_line`.
- `OpeningFamily`: `name` (text before the first colon of the opening name;
  London lines are London System).
- `EndgamePattern`: `endgame_type`, `piece_count`, `benchmark_positions`,
  `avg_player_elo`, `sample_fen`, `sample_human_move`.

## Relationships

- `Position-[:PLAYED_MOVE {uci_move, by}]->Position`: one edge per move and
  mover, `by` is `owner` or `opponent`. `games` (distinct), `times`,
  `wins`/`draws`/`losses` and `score_pct` from the **mover's** side,
  `avg_cp_loss`, `avg_eval_after` (mover's side), `inaccuracies`,
  `mistakes`, `blunders`, `is_engine_best`, plus `san_move`,
  `moved_piece`, `from_square`, `to_square`, `promotion`, `is_capture`,
  `is_check`.
- `Position-[:THEORY_MOVE {uci_move}]->Position`: book move, `eco_codes`
  lists every ECO line that plays it.
- `Position-[:ENGINE_BEST {uci, san}]->Position`: the most frequent stored
  Stockfish best move, when its target position is in the graph.
- `Position-[:CLASSIFIED_AS]->Opening`: the position is that opening's EPD.
- `Position-[:IN_OPENING {ply}]->Opening`: the position lies on the line.
- `Opening-[:IN_FAMILY]->OpeningFamily`.
- `Position-[:HAS_ENDGAME_TYPE]->EndgamePattern`: `benchmark: true` with
  `benchmark_move_uci`, `elo_tier`, `player_elo` on Endgame Atlas samples;
  `from_games: true` on positions of six pieces or fewer reached in games.
- `Player-[:PLAYED_AS {color, elo}]->Game`.
- `Game-[:REACHED {ply, owner_to_move}]->Position`: every position of the
  game, ply 0 is the start.
- `Game-[:OPENED_WITH {ply}]->Opening`: the deepest named opening reached.
- `Game-[:LEFT_THEORY_AT {ply, played_uci, played_san, by}]->Position`: the
  first move that is not a book move from that position.
- `Game-[:ENTERED_ENDGAME {ply, material_sig}]->Position`: the first
  endgame-phase position.
- `Position-[:MISTAKE_IN {ply}]->Game`: an owner move with `cp_loss` of 50 or
  more; `severity`, `cp_loss`, `mate_swing`, `played_uci`, `played_san`,
  `best_uci`.

## Semantics and caveats

- `eval_cp` is from the **side to move** at that position: the average stored
  `eval_cp_before` of moves played from it, or of the negated `eval_cp_after`
  of moves that reached it. `eval_samples` is the number of values averaged.
  Stored evals are Stockfish depth-limited searches; mate is flattened to
  +/-10000, so `mate_swing` marks a loss of 5000 cp or more.
- Severity thresholds on `cp_loss`: inaccuracy 50, mistake 100, blunder 300.
- `visit_games` counts distinct games that reached the position.
- `material_sig` uses the Endgame Atlas notation, White first: `KRPvKR`.
  `EndgamePattern.endgame_type` uses the same notation, so equal strings
  describe the same material. Atlas hubs exist only for material the dataset
  covers.
- `phase` follows a simplified Lichess divider: endgame when queens, rooks,
  bishops and knights number 6 or fewer; opening when they number more than 10
  and each side keeps at least 4 pieces on its back rank; middlegame otherwise.
- PostgreSQL has no clock data for these games, so the graph has no clock
  fields.
"""

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

logger = logging.getLogger(__name__)
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
        raise tool_failure(logger, "Neo4j could not complete the read request", exc) from exc


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
        description="Read-only position, move, game-path, theory-exit, mistake, and endgame graph tools.",
        version="0.1.0",
        lifespan=lifespan,
    )

    def repo() -> Neo4jRepository:
        return repository if repository is not None else _get_default_repository()

    @app.tool(annotations=READ_ONLY, structured_output=True)
    def get_position_context(fen: str) -> PositionContext:
        """Get a position with its phase, average stored eval (side to move), openings, endgame type and engine best move."""
        return _invoke(lambda: repo().get_position_context(fen))

    @app.tool(annotations=READ_ONLY, structured_output=True)
    def get_position_moves(fen: str, limit: int = 20, by: MoveFilter = "all") -> PositionMoves:
        """List played moves and theory moves leaving a position, most-played first. Played moves are split by mover (owner or opponent) with the mover's results, average centipawn loss and severity counts. Use by to list only theory, owner or opponent moves."""
        return _invoke(lambda: repo().get_position_moves(fen, limit, by))

    @app.tool(annotations=READ_ONLY, structured_output=True)
    def find_transpositions(
        fen: str,
        max_depth: int = 3,
        limit: int = 20,
    ) -> TranspositionResult:
        """Find bounded move paths from a position to positions that other move orders also reach."""
        return _invoke(lambda: repo().find_transpositions(fen, max_depth, limit))

    @app.tool(annotations=READ_ONLY, structured_output=True)
    def get_game_blunders(game_id: int, limit: int = 100, min_severity: Severity = "mistake") -> GameBlunders:
        """List the owner's inaccuracies, mistakes or blunders in one game, in ply order, at or above min_severity."""
        return _invoke(lambda: repo().get_game_blunders(game_id, limit, min_severity))

    @app.tool(annotations=READ_ONLY, structured_output=True)
    def get_recurring_blunder_positions(
        min_occurrences: int = 2,
        limit: int = 20,
        min_severity: Severity = "mistake",
    ) -> RecurringBlunders:
        """Rank positions where the owner went wrong in at least min_occurrences different games."""
        return _invoke(lambda: repo().get_recurring_blunder_positions(min_occurrences, limit, min_severity))

    @app.tool(annotations=READ_ONLY, structured_output=True)
    def get_endgame_context(fen: str, limit: int = 20) -> EndgameContext:
        """Get endgame classifications and bounded Endgame Atlas benchmark positions for a FEN."""
        return _invoke(lambda: repo().get_endgame_context(fen, limit))

    @app.tool(annotations=READ_ONLY, structured_output=True)
    def get_games_through_position(fen: str, limit: int = 20) -> GamesThroughPosition:
        """List the owner's games that reached a position, newest first, with the owner's score from it."""
        return _invoke(lambda: repo().get_games_through_position(fen, limit))

    @app.tool(annotations=READ_ONLY, structured_output=True)
    def get_theory_exits(limit: int = 20, by: Literal["all", "owner", "opponent"] = "owner") -> TheoryExits:
        """Rank where games leave opening theory: the position, the first non-book move, who played it, and the owner's score. book_ended means the opening data stops at that position."""
        return _invoke(lambda: repo().get_theory_exits(limit, by))

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
server = mcp


def main() -> None:
    """Run the Neo4j MCP server over standard input/output."""
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
