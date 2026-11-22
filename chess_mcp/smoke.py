"""Smoke test for the three MCP servers, exactly as an MCP host starts them.

Each server is spawned over stdio with the official MCP client, its tool list
is compared with the expected contract, and one cheap read-only tool is
called. No language model is involved, so this checks the host side of the
Claude Code plugin without an API key.

    uv run chessgraph-smoke            # all three servers
    uv run chessgraph-smoke stockfish  # one server
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from chess_mcp.config import PROJECT_ROOT

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"


@dataclass(frozen=True)
class ServerCheck:
    name: str
    module: str
    tools: frozenset[str]
    call: str
    arguments: dict[str, Any]
    # Summarise the structured result without echoing personal data.
    summarise: Callable[[dict[str, Any]], str]


@dataclass
class SmokeResult:
    server: str
    ok: bool
    tools: list[str] = field(default_factory=list)
    detail: str = ""


def _summary_postgres(data: dict[str, Any]) -> str:
    return f"get_player_summary: {data.get('games_played', '?')} games for the configured player"


def _summary_neo4j(data: dict[str, Any]) -> str:
    position = data.get("position") or {}
    return (
        "get_position_context: start position "
        f"{'found' if position else 'missing'}, "
        f"{len(data.get('openings') or [])} opening link(s)"
    )


def _summary_stockfish(data: dict[str, Any]) -> str:
    moves = data.get("moves") or []
    return "validate_line: " + " ".join(move.get("san", "?") for move in moves)


CHECKS: dict[str, ServerCheck] = {
    "postgres": ServerCheck(
        name="postgres",
        module="chess_mcp.postgres.server",
        tools=frozenset(
            {
                "list_games",
                "get_game",
                "get_game_moves",
                "get_player_summary",
                "get_coaching_brief",
                "get_blunders",
                "find_position_occurrences",
                "lookup_opening",
                "lookup_endgame_positions",
            }
        ),
        call="get_player_summary",
        arguments={},
        summarise=_summary_postgres,
    ),
    "neo4j": ServerCheck(
        name="neo4j",
        module="chess_mcp.neo4j.server",
        tools=frozenset(
            {
                "get_position_context",
                "get_position_moves",
                "find_transpositions",
                "get_game_blunders",
                "get_recurring_blunder_positions",
                "get_endgame_context",
                "get_games_through_position",
                "get_theory_exits",
            }
        ),
        call="get_position_context",
        arguments={"fen": START_FEN},
        summarise=_summary_neo4j,
    ),
    "stockfish": ServerCheck(
        name="stockfish",
        module="chess_mcp.stockfish.server",
        tools=frozenset({"analyze_position", "compare_move", "validate_line"}),
        call="validate_line",
        arguments={"fen": START_FEN, "moves_uci": ["e2e4", "e7e5", "g1f3"]},
        summarise=_summary_stockfish,
    ),
}


def _structured(result: Any) -> dict[str, Any]:
    data = getattr(result, "structured_content", None)
    if data is None:
        data = getattr(result, "structuredContent", None)
    if isinstance(data, dict):
        return data
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            try:
                parsed = json.loads(text)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return {}


async def check_server(check: ServerCheck) -> SmokeResult:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", f"from {check.module} import main; main()"],
        env=dict(os.environ),
        cwd=PROJECT_ROOT,
    )
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                names = sorted(tool.name for tool in listed.tools)
                missing = sorted(check.tools - set(names))
                extra = sorted(set(names) - check.tools)
                if missing or extra:
                    return SmokeResult(
                        check.name,
                        False,
                        names,
                        f"tool contract changed: missing={missing} extra={extra}",
                    )
                result = await session.call_tool(check.call, check.arguments)
                if getattr(result, "is_error", False) or getattr(result, "isError", False):
                    return SmokeResult(check.name, False, names, f"{check.call} returned an error")
                return SmokeResult(check.name, True, names, check.summarise(_structured(result)))
    except Exception as exc:  # noqa: BLE001 - report any startup failure as a failed check
        return SmokeResult(check.name, False, [], f"{type(exc).__name__}: {exc}")


async def run(names: list[str]) -> list[SmokeResult]:
    results = []
    for name in names:
        results.append(await check_server(CHECKS[name]))
    return results


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    unknown = [name for name in args if name not in CHECKS]
    if unknown:
        print(f"Unknown server(s): {', '.join(unknown)}. Choose from {', '.join(CHECKS)}.")
        return 2
    results = asyncio.run(run(args or list(CHECKS)))
    for result in results:
        mark = "PASS" if result.ok else "FAIL"
        print(f"[{mark}] {result.server}: {len(result.tools)} tools; {result.detail}")
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
