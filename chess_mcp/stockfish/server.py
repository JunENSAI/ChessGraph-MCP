"""MCPServer exposing the curated Stockfish analysis tools over stdio."""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from chess_mcp.errors import tool_failure
from chess_mcp.stockfish.engine import StockfishService
from chess_mcp.stockfish.models import (
    LimitType,
    MoveComparison,
    PositionAnalysis,
    ValidatedLine,
)


logger = logging.getLogger(__name__)

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

CAPABILITIES = """# ChessGraph Stockfish capabilities

This server provides bounded, read-only engine analysis.

- Scores are normalized to the player at the root position.
- Centipawn and mate scores remain distinct; mates are never flattened.
- Centipawns are an engine scale, not a universal win probability.
- WDL permille values are returned only when Stockfish supplies them.
- Principal variations are legally replayed into matching UCI and SAN.
- `compare_move` searches the unrestricted best move and the restricted played
  move from the same root with the same search budget.
- Engine calls share one lazy process and are serialized.
- Depth, node, time, and MultiPV requests are bounded by server configuration.
- Results include available engine identity, configured options, depth, nodes,
  selective depth, and engine-reported time. Critical positions should be
  rerun with a larger budget before making a confident coaching claim.
"""


def create_server(service: StockfishService | None = None) -> MCPServer[object]:
    """Create a Stockfish MCP server around an injectable service."""
    stockfish = service or StockfishService()

    @asynccontextmanager
    async def lifespan(_: MCPServer[object]) -> AsyncIterator[None]:
        try:
            yield
        finally:
            try:
                stockfish.close()
            except Exception:
                logger.exception("Failed to quit the Stockfish engine cleanly")

    app: MCPServer[object] = MCPServer(
        name="chessgraph-stockfish",
        title="ChessGraph Stockfish",
        description="Bounded Stockfish position and move analysis.",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.tool(annotations=READ_ONLY, structured_output=True)
    def analyze_position(
        fen: str,
        limit_type: LimitType = "depth",
        limit_value: int | None = None,
        multipv: int = 1,
    ) -> PositionAnalysis:
        """Analyze a FEN with a bounded depth, node, or millisecond budget."""
        try:
            return stockfish.analyze_position(
                fen,
                limit_type=limit_type,
                limit_value=limit_value,
                multipv=multipv,
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        except Exception as exc:
            raise tool_failure(logger, "Stockfish analysis failed", exc) from exc

    @app.tool(annotations=READ_ONLY, structured_output=True)
    def compare_move(
        fen: str,
        played_move_uci: str,
        limit_type: LimitType = "depth",
        limit_value: int | None = None,
    ) -> MoveComparison:
        """Compare the best line with one legal played move at the same budget."""
        try:
            return stockfish.compare_move(
                fen,
                played_move_uci,
                limit_type=limit_type,
                limit_value=limit_value,
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        except Exception as exc:
            raise tool_failure(logger, "Stockfish move comparison failed", exc) from exc

    @app.tool(annotations=READ_ONLY, structured_output=True)
    def validate_line(fen: str, moves_uci: list[str]) -> ValidatedLine:
        """Legally replay a UCI move sequence and return UCI, SAN, and FEN data."""
        try:
            return stockfish.validate_line(fen, moves_uci)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        except Exception as exc:
            raise tool_failure(logger, "Chess line validation failed", exc) from exc

    @app.resource(
        "chessgraph-stockfish://capabilities",
        name="stockfish_capabilities",
        title="ChessGraph Stockfish capabilities",
        description="Score semantics, search guarantees, and engine behavior.",
        mime_type="text/markdown",
    )
    def capabilities() -> str:
        return CAPABILITIES

    return app


mcp = create_server()
server = mcp


def main() -> None:
    """Run the Stockfish MCP server over standard input/output."""
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    mcp.run("stdio")


if __name__ == "__main__":
    main()
