"""MCP server exposing curated, read-only PostgreSQL chess queries."""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import date
from typing import TypeVar

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from chess_mcp.config import get_chess_username, get_postgres_settings
from chess_mcp.errors import tool_failure

from .models import (
    BlundersResult,
    CoachingBrief,
    EndgamePositionsResult,
    GameMovesResult,
    GameResultDetail,
    GamesResult,
    GameType,
    OpeningsResult,
    PlayerSummary,
    PositionOccurrencesResult,
    UserOutcome,
)
from .repository import PostgresRepository


logger = logging.getLogger(__name__)
_T = TypeVar("_T")

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

POSTGRES_SCHEMA_RESOURCE = """# ChessGraph PostgreSQL schema and semantics

This server exposes fixed, parameterized SELECT queries only. Every query runs
in a read-only PostgreSQL transaction with a local statement timeout. Results
are capped at 100 rows (and may be capped lower by server configuration).

## games
- `game_id` is the stable numeric game key; `game_hash` is unique.
- `game_type`: rapid, blitz, bullet, daily, or bot.
- `result` is from White's perspective: 1-0, 0-1, 1/2-1/2, or *.
- Player names are `white_username` and `black_username`.
- `user_color`, `user_elo`, `opponent_elo`, and `user_outcome` describe the
  configured ETL user's perspective when populated.
- The data owner's Chess.com account is the `CHESS_USERNAME` environment
  variable. `get_player_summary` uses it when `username` is omitted and
  returns the resolved account in `username`.
- `pgn_moves_raw` stores the movetext; `total_plies` counts half-moves.
- `get_coaching_brief` ranks opening families by result and lists repeated
  moves that differ from `best_move_uci`. Endgame type is not on `games`.

## game_moves
- `(game_id, ply_number)` is unique; ply numbers start at 1.
- `turn_color` is w or b and identifies the player who made the move.
- `san_move` and `uci_move` are the played move in SAN and UCI notation.
- `fen_before_norm` and `fen_after_norm` are normalized four-field FEN keys.
- Evaluations are centipawns. `cp_loss` is non-negative when populated, and
  `best_move_uci` is the engine's preferred move before the played move.

## opening_theory
- `epd_norm` is the normalized four-field position key used for exact lookup.
- ECO code/name and PGN/UCI lines describe theory reaching that position.

## endgame_theory
- `fen_norm` is the normalized four-field position key; `fen_full` preserves
  the source's full FEN.
- `human_move_uci` is the observed human move.
- Positions may be filtered by endgame type, piece count, and ELO tier.

Position lookup is exact after FEN normalization; it is not a similarity or
free-form SQL search.
"""


def _positive(value: int) -> int:
    if value < 1:
        raise ValueError("value must be positive")
    return value


def _required_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("text must not be empty")
    return normalized


def _run(operation: str, call: Callable[[], _T]) -> _T:
    try:
        return call()
    except ToolError:
        raise
    except ValueError as exc:
        logger.info(
            "Rejected invalid PostgreSQL tool arguments: %s",
            type(exc).__name__,
        )
        raise ToolError(str(exc)) from None
    except Exception as exc:
        raise tool_failure(logger, f"PostgreSQL {operation} failed.", exc) from None


def create_server(repository: PostgresRepository | None = None) -> MCPServer:
    """Create a PostgreSQL MCP server, optionally using an injected repository."""
    active_repository = repository

    @asynccontextmanager
    async def lifespan(_: MCPServer) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if repository is None and active_repository is not None:
                active_repository.close()

    server = MCPServer(
        name="chessgraph-postgres",
        title="ChessGraph PostgreSQL",
        description="Curated read-only access to games, moves, and chess theory.",
        version="0.1.0",
        lifespan=lifespan,
    )

    def get_repository() -> PostgresRepository:
        nonlocal active_repository
        if active_repository is None:
            active_repository = PostgresRepository.from_settings(
                get_postgres_settings()
            )
        return active_repository

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def list_games(
        player: str | None = None,
        game_type: GameType | None = None,
        user_outcome: UserOutcome | None = None,
        eco_code: str | None = None,
        played_from: date | None = None,
        played_to: date | None = None,
        limit: int = 20,
    ) -> GamesResult:
        """List games filtered by player, type, user outcome, ECO, or date."""

        def query() -> GamesResult:
            if player is not None:
                checked_player = _required_text(player)
            else:
                checked_player = None
            checked_eco = _required_text(eco_code) if eco_code is not None else None
            games = get_repository().list_games(
                player=checked_player,
                game_type=game_type,
                user_outcome=user_outcome,
                eco_code=checked_eco,
                played_from=played_from,
                played_to=played_to,
                limit=_positive(limit),
            )
            return GamesResult(games=games)

        return _run("list games", query)

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def get_game(game_id: int) -> GameResultDetail:
        """Get one game, including PGN movetext and metadata, by numeric ID."""
        return _run(
            "get game",
            lambda: GameResultDetail(
                game=get_repository().get_game(_positive(game_id))
            ),
        )

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def get_game_moves(
        game_id: int,
        start_ply: int = 1,
        limit: int = 100,
    ) -> GameMovesResult:
        """Get a page of ordered move, clock, position, and engine data."""

        def query() -> GameMovesResult:
            checked_game_id = _positive(game_id)
            checked_start_ply = _positive(start_ply)
            return GameMovesResult(
                game_id=checked_game_id,
                start_ply=checked_start_ply,
                moves=get_repository().get_game_moves(
                    checked_game_id,
                    start_ply=checked_start_ply,
                    limit=_positive(limit),
                ),
            )

        return _run("get game moves", query)

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def get_player_summary(
        username: str | None = None,
        game_type: GameType | None = None,
    ) -> PlayerSummary:
        """Summarize a player. Omit username to use CHESS_USERNAME from the environment.

        The returned username field is the account the server resolved. Do not
        hardcode that account name.
        """

        selected_username = username or get_chess_username()
        return _run(
            "get player summary",
            lambda: get_repository().get_player_summary(
                _required_text(selected_username),
                game_type=game_type,
            ),
        )

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def get_coaching_brief(player: str | None = None) -> CoachingBrief:
        """Rank strengths and the weakest opening, with the repeated leaving move.

        Omit player to use CHESS_USERNAME from the environment. The endgames
        field states that endgame type is not stored on games.
        """
        selected = _required_text(player) if player is not None else get_chess_username()
        return _run(
            "get coaching brief",
            lambda: get_repository().get_coaching_brief(_required_text(selected)),
        )

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def get_blunders(
        player: str | None = None,
        game_id: int | None = None,
        minimum_cp_loss: int = 100,
        limit: int = 20,
    ) -> BlundersResult:
        """Find the data owner's mistakes, or one named player's evaluated moves."""

        def query() -> BlundersResult:
            checked_player = _required_text(player) if player is not None else None
            checked_game_id = _positive(game_id) if game_id is not None else None
            if minimum_cp_loss < 0:
                raise ValueError("minimum_cp_loss must not be negative")
            return BlundersResult(
                blunders=get_repository().get_blunders(
                    player=checked_player,
                    game_id=checked_game_id,
                    minimum_cp_loss=minimum_cp_loss,
                    limit=_positive(limit),
                )
            )

        return _run("get blunders", query)

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def find_position_occurrences(
        fen: str,
        limit: int = 20,
    ) -> PositionOccurrencesResult:
        """Find games whose move records contain an exact normalized position."""

        def query() -> PositionOccurrencesResult:
            normalized_fen, occurrences = (
                get_repository().find_position_occurrences(
                    _required_text(fen),
                    limit=_positive(limit),
                )
            )
            return PositionOccurrencesResult(
                normalized_fen=normalized_fen,
                occurrences=occurrences,
            )

        return _run("find position occurrences", query)

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def lookup_opening(fen: str, limit: int = 20) -> OpeningsResult:
        """Look up opening theory by exact normalized position."""

        def query() -> OpeningsResult:
            normalized_fen, openings = get_repository().lookup_opening(
                _required_text(fen),
                limit=_positive(limit),
            )
            return OpeningsResult(
                normalized_fen=normalized_fen,
                openings=openings,
            )

        return _run("lookup opening", query)

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def lookup_endgame_positions(
        fen: str | None = None,
        endgame_type: str | None = None,
        piece_count: int | None = None,
        elo_tier: str | None = None,
        limit: int = 20,
    ) -> EndgamePositionsResult:
        """Look up endgame examples by position and curated metadata filters."""

        def query() -> EndgamePositionsResult:
            checked_fen = _required_text(fen) if fen is not None else None
            checked_type = (
                _required_text(endgame_type) if endgame_type is not None else None
            )
            checked_tier = _required_text(elo_tier) if elo_tier is not None else None
            normalized_fen, positions = (
                get_repository().lookup_endgame_positions(
                    fen=checked_fen,
                    endgame_type=checked_type,
                    piece_count=piece_count,
                    elo_tier=checked_tier,
                    limit=_positive(limit),
                )
            )
            return EndgamePositionsResult(
                normalized_fen=normalized_fen,
                positions=positions,
            )

        return _run("lookup endgame positions", query)

    @server.resource(
        "chessgraph://postgres/schema",
        name="postgres_schema",
        title="PostgreSQL schema and semantics",
        description="Static field and interpretation guide for PostgreSQL tools.",
        mime_type="text/markdown",
    )
    def postgres_schema() -> str:
        return POSTGRES_SCHEMA_RESOURCE

    return server


mcp = create_server()
server = mcp


def main() -> None:
    """Run the PostgreSQL MCP server over stdio."""
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
